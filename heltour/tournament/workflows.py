import reversion
from django.contrib import messages
from heltour.tournament.models import *
from heltour.tournament import pairinggen, signals, slackapi
from smtplib import SMTPException
from django.template.loader import render_to_string
from django.core.mail import send_mail
from heltour import settings
import alternates_manager

class RoundTransitionWorkflow():

    def __init__(self, season):
        self.season = season

    @property
    def round_to_close(self):
        return self.season.round_set.filter(publish_pairings=True, is_completed=False).order_by('number').first()

    @property
    def round_to_open(self):
        return self.season.round_set.filter(publish_pairings=False, is_completed=False).order_by('number').first()

    @property
    def season_to_close(self):
        round_to_close = self.round_to_close
        round_to_open = self.round_to_open
        return self.season if not self.season.is_completed and round_to_open is None and (round_to_close is None or round_to_close.number == self.season.rounds) else None

    def run(self, complete_round=False, complete_season=False, update_board_order=False, generate_pairings=False, background=False, user=None):
        msg_list = []
        round_to_close = self.round_to_close
        round_to_open = self.round_to_open
        season_to_close = self.season_to_close

        with transaction.atomic():
            if complete_round and round_to_close is not None:
                with reversion.create_revision():
                    reversion.set_user(user)
                    reversion.set_comment('Closed round.')
                    round_to_close.is_completed = True
                    round_to_close.save()
                msg_list.append(('Round %d set as completed.' % round_to_close.number, messages.INFO))
            if complete_season and season_to_close is not None and (round_to_close is None or round_to_close.is_completed):
                with reversion.create_revision():
                    reversion.set_user(user)
                    reversion.set_comment('Closed season.')
                    season_to_close.is_completed = True
                    season_to_close.save()
                msg_list.append(('%s set as completed.' % season_to_close.name, messages.INFO))
            if update_board_order and round_to_open is not None and self.season.league.competitor_type == 'team':
                try:
                    UpdateBoardOrderWorkflow(self.season).run(alternates_only=False)
                    msg_list.append(('Board order updated.', messages.INFO))
                except IndexError:
                    msg_list.append(('Error updating board order.', messages.ERROR))
                    return msg_list
            if generate_pairings and round_to_open is not None:
                if background:
                    signals.do_generate_pairings.send(sender=self.__class__, round_id=round_to_open.pk)
                    msg_list.append(('Generating pairings in background.', messages.INFO))
                else:
                    try:
                        pairinggen.generate_pairings(round_to_open, overwrite=False)
                        with reversion.create_revision():
                            reversion.set_user(user)
                            reversion.set_comment('Generated pairings.')
                            round_to_open.publish_pairings = False
                            round_to_open.save()
                        msg_list.append(('Pairings generated.', messages.INFO))
                    except pairinggen.PairingsExistException:
                        msg_list.append(('Unpublished pairings already exist.', messages.WARNING))
                    except pairinggen.PairingHasResultException:
                        msg_list.append(('Pairings with results can\'t be overwritten.', messages.ERROR))
                    except pairinggen.PairingGenerationException as e:
                        msg_list.append(('Error generating pairings. %s' % e.message, messages.ERROR))
        return msg_list

    @property
    def warnings(self):
        msg_list = []
        round_to_close = self.round_to_close
        round_to_open = self.round_to_open

        if round_to_close is not None and round_to_close.end_date is not None and round_to_close.end_date > timezone.now() + timedelta(hours=1):
            time_from_now = self._time_from_now(round_to_close.end_date - timezone.now())
            msg_list.append(('The round %d end date is %s from now.' % (round_to_close.number, time_from_now), messages.WARNING))
        elif round_to_open is not None and round_to_open.start_date is not None and round_to_open.start_date > timezone.now() + timedelta(hours=1):
            time_from_now = self._time_from_now(round_to_open.start_date - timezone.now())
            msg_list.append(('The round %d start date is %s from now.' % (round_to_open.number, time_from_now), messages.WARNING))

        if round_to_close is not None:
            incomplete_pairings = PlayerPairing.objects.filter(result='', teamplayerpairing__team_pairing__round=round_to_close).nocache() | \
                                  PlayerPairing.objects.filter(result='', loneplayerpairing__round=round_to_close).nocache()
            if len(incomplete_pairings) > 0:
                msg_list.append(('Round %d has %d pairing(s) without a result.' % (round_to_close.number, len(incomplete_pairings)), messages.WARNING))

        return msg_list

    def _time_from_now(self, delta):
        if delta.days > 0:
            if delta.days == 1:
                return '1 day'
            else:
                return '%d days' % delta.days
        else:
            hours = delta.seconds / 3600
            if hours == 1:
                return '1 hour'
            else:
                return '%d hours' % hours

class UpdateBoardOrderWorkflow():

    def __init__(self, season):
        self.season = season

    def run(self, alternates_only):
        if self.season.league.competitor_type != 'team':
            return

        if not alternates_only:
            self.update_teammember_order()

        if alternates_only or not self.season.alternates_manager_enabled() or self.season.round_set.filter(publish_pairings=True).count() == 0:
            members_by_board = [TeamMember.objects.filter(team__season=self.season, board_number=n + 1) for n in range(self.season.boards)]
            ratings_by_board = [sorted([float(m.player.rating_for(self.season.league)) for m in m_list]) for m_list in members_by_board]
            alternates = Alternate.objects.filter(season_player__season=self.season).select_related('season_player__player').nocache()

            boundaries = self.calc_alternate_boundaries(ratings_by_board)
            flex = self.season.alternates_manager_setting().rating_flex
            self.smooth_alternate_boundaries(boundaries, alternates, ratings_by_board, flex)
            self.update_alternate_buckets(boundaries)
            self.assign_alternates_to_buckets()

    def update_teammember_order(self):
        for team in self.season.team_set.all():
            with reversion.create_revision():
                change_descriptions = []
                members = list(team.teammember_set.order_by('board_number'))
                occupied_boards = [m.board_number for m in members]
                old_order = {m.board_number: m for m in members}
                new_order = {m.board_number: m for m in members}

                alternate_search_round = alternates_manager.current_round(self.season)

                def invariant(board_num):
                    search = AlternateSearch.objects.filter(round=alternate_search_round, team=team, board_number=board_num, is_active=True).first()
                    assignment = AlternateAssignment.objects.filter(round=alternate_search_round, team=team, board_number=board_num).first()
                    return assignment or (search and search.still_needs_alternate())

                # Do a modified bubble sort - this lets us restrict swaps in some cases
                min_delta_for_change = 0
                while True:
                    has_changes = False
                    for i in range(len(occupied_boards) - 1):
                        j = occupied_boards[i]
                        k = occupied_boards[i + 1]
                        higher_bd = new_order[j]
                        lower_bd = new_order[k]
                        higher_rtg = higher_bd.player.rating_for(self.season.league) or 0
                        lower_rtg = lower_bd.player.rating_for(self.season.league) or 0
                        if lower_rtg - higher_rtg > min_delta_for_change:
                            has_changes = True
                            # Remove boards from consideration if they are locked
                            # We could do this at the start but it would be too slow due to the DB queries
                            # The condition above is relatively rare so the performance impact is less this way
                            if invariant(j):
                                occupied_boards.remove(j)
                                break
                            if invariant(k):
                                occupied_boards.remove(k)
                                break
                            new_order[j] = lower_bd
                            new_order[k] = higher_bd
                    if not has_changes:
                        break

                # Commit the changes to the actual model
                for board_number in occupied_boards:
                    if old_order[board_number] != new_order[board_number]:
                        m = new_order[board_number]
                        TeamMember.objects.update_or_create(team=team, board_number=board_number, \
                                                  defaults={ 'player': m.player, 'is_captain': m.is_captain,
                                                             'is_vice_captain': m.is_vice_captain })
                        change_descriptions.append('changed board %d from "%s" to "%s"' % (board_number, old_order[board_number], m))
                reversion.set_comment('Update board order - %s.' % ', '.join(change_descriptions))

    def calc_alternate_boundaries(self, ratings_by_board):
        # Calculate the average of the upper/lower half of each board (minus the most extreme value to avoid outliers skewing the average)
        left_average_by_board = [sum(r_list[1:int(len(r_list) / 2)]) / (int(len(r_list) / 2) - 1) if len(r_list) > 2 else sum(r_list) / len(r_list) if len(r_list) > 0 else None for r_list in ratings_by_board]
        right_average_by_board = [sum(r_list[int((len(r_list) + 1) / 2):-1]) / (int(len(r_list) / 2) - 1) if len(r_list) > 2 else sum(r_list) / len(r_list) if len(r_list) > 0 else None for r_list in ratings_by_board]
        boundaries = []
        for i in range(self.season.boards + 1):
            # The logic here is a bit complicated in order to handle cases where there are no players for a board
            left_i = i - 1
            while left_i >= 0 and left_average_by_board[left_i] is None:
                left_i -= 1
            left = left_average_by_board[left_i] if left_i >= 0 else None
            right_i = i
            while right_i < self.season.boards and right_average_by_board[right_i] is None:
                right_i += 1
            right = right_average_by_board[right_i] if right_i < self.season.boards else None
            if left is None or right is None:
                boundaries.append(None)
            else:
                boundaries.append((left + right) / 2)
        return boundaries

    def smooth_alternate_boundaries(self, boundaries, alternates, ratings_by_board, flex):
        # If we have enough data, modify the boundaries to try and smooth out the number of players per board
        if all((len(r_list) >= 4 for r_list in ratings_by_board)):
            iter_count = 20

            # Calculate how much each boundary should be changed per iteration
            up_step_sizes = []
            down_step_sizes = []
            for i in range(self.season.boards - 1):
                boundary = boundaries[i + 1]
                # Split the difference between the highest/lowest 2 players on each board to determine
                # the absolute most we're willing the change the boundary
                higher_board_min = (ratings_by_board[i][0] + ratings_by_board[i][1]) / 2 - flex
                lower_board_max = (ratings_by_board[i + 1][-1] + ratings_by_board[i + 1][-2]) / 2 + flex
                if boundary < higher_board_min and boundary < lower_board_max:
                    delta_up = max(higher_board_min, lower_board_max) - boundary
                    delta_down = 0
                elif boundary > higher_board_min and boundary > lower_board_max:
                    delta_up = 0
                    delta_down = boundary - min(higher_board_min, lower_board_max)
                else:
                    delta_up = max(higher_board_min, lower_board_max) - boundary
                    delta_down = boundary - min(higher_board_min, lower_board_max)
                up_step_sizes.append(delta_up / float(iter_count))
                down_step_sizes.append(delta_down / float(iter_count))


            # Start iterating the smoothing algorithm
            total_alt_count = len(alternates)
            for _ in range(iter_count):
                # Calculate the number of alternates in each bucket
                bucket_counts = [0] * self.season.boards
                for alt in alternates:
                    r = alt.season_player.player.rating_for(self.season.league)
                    for i in range(self.season.boards):
                        if r > boundaries[i + 1] or boundaries[i + 1] == None:
                            bucket_counts[i] += 1
                            break

                # Move the boundaries of uneven buckets
                for i in range(self.season.boards - 1):
                    expected_on_left = total_alt_count * i / float(self.season.boards)
                    actual_on_left = sum(bucket_counts[0:i])
                    if bucket_counts[i] > bucket_counts[i + 1] + 1 or \
                            bucket_counts[i] == bucket_counts[i + 1] + 1 and actual_on_left > expected_on_left + 1:
                        boundaries[i + 1] += up_step_sizes[i]
                    if bucket_counts[i] < bucket_counts[i + 1] - 1 or \
                            bucket_counts[i] == bucket_counts[i + 1] - 1 and actual_on_left < expected_on_left - 1:
                        boundaries[i + 1] -= down_step_sizes[i]

    def update_alternate_buckets(self, boundaries):
        # Update the buckets
        with reversion.create_revision():
            reversion.set_comment('Updated alternate order')
            for board_num in range(1, self.season.boards + 1):
                min_rating = boundaries[board_num]
                max_rating = boundaries[board_num - 1]
                if min_rating is None and max_rating is None:
                    AlternateBucket.objects.filter(season=self.season, board_number=board_num).delete()
                else:
                    AlternateBucket.objects.update_or_create(season=self.season, board_number=board_num, defaults={ 'max_rating': max_rating, 'min_rating': min_rating })

    def assign_alternates_to_buckets(self):
        for alt in Alternate.objects.filter(season_player__season=self.season):
            alt.update_board_number()

class ApproveRegistrationWorkflow():

    def __init__(self, reg):
        self.reg = reg
        self.league = reg.season.league

    @property
    def default_send_confirm_email(self):
        return True

    @property
    def default_invite_to_slack(self):
        return not self.reg.already_in_slack_group

    @property
    def default_byes(self):
        # Give up to 2 byes by default, one for each round
        return min(self.active_round_count, 2)

    @property
    def default_section(self):
        if not hasattr(self.reg.season, 'section'):
            return self.reg.season
        player = Player.get_or_create(self.reg.lichess_username)
        if self.reg.section_preference is not None and self.reg.section_preference.is_eligible(player):
            return self.reg.section_preference.season
        section_list = self.reg.season.section_list()
        # Assume least restrictive sections are first, and that we should default to more restrictive
        for season in reversed(section_list):
            if hasattr(season, 'section') and season.section.is_eligible(player):
                return season
        return self.reg.season

    @property
    def default_ljp(self):
        # Try and calculate LjP below, but use 0 if we can't
        default_ljp = 0
        season = self.default_section
        active_round_count = self.active_round_count

        if self.default_byes < active_round_count:
            season_players = season.seasonplayer_set.filter(is_active=True).select_related('player', 'loneplayerscore').nocache()
            player = Player.objects.filter(lichess_username__iexact=self.reg.lichess_username).first()
            rating = self.reg.classical_rating if player is None else player.rating_for(self.league)

            # Get the scores of players +/- 100 rating points (or a wider range if not enough players are close)
            diff = 100
            while diff < 500:
                close_players = [sp for sp in season_players if abs(sp.player.rating_for(self.league) - rating) < diff]
                if len(close_players) >= 5:
                    break
                diff += 100
            close_player_scores = sorted([sp.get_loneplayerscore().points for sp in close_players])
            # Remove highest/lowest scores to help avoid outliers
            close_player_scores_adjusted = close_player_scores[1:-1]
            if len(close_player_scores_adjusted) > 0:
                # Calculate the average of the scores
                average_score = sum(close_player_scores_adjusted) / len(close_player_scores_adjusted)
                if active_round_count > 1 and season.round_set.filter(publish_pairings=True, is_completed=False).count():
                    expected_score = average_score * active_round_count / (active_round_count - 1)
                else:
                    expected_score = average_score
                expected_score_rounded = round(2.0 * expected_score) / 2.0
                # Subtract 0.5, and another 0.5 for each bye
                default_ljp = max(expected_score_rounded - 0.5 - self.default_byes * 0.5, 0)
                # Hopefully we now have a reasonable value for LjP
        return default_ljp

    @property
    def active_round_count(self):
        return self.default_section.round_set.filter(publish_pairings=True).count()

    @property
    def is_late(self):
        return self.league.competitor_type != 'team' and self.active_round_count > 0

    def approve_reg(self, request, modeladmin, send_confirm_email, invite_to_slack, season, retroactive_byes, late_join_points):
        reg = self.reg

        # Limit changes to moderators
        mod = LeagueModerator.objects.filter(player__lichess_username__iexact=reg.lichess_username).first()
        if mod is not None and mod.player.email and mod.player.email != reg.email:
            reg.email = mod.player.email

        # Add or update the player in the DB
        with reversion.create_revision():
            reversion.set_user(request.user)
            reversion.set_comment('Approved registration.')

            player, _ = Player.objects.update_or_create(
                lichess_username__iexact=reg.lichess_username,
                defaults={'lichess_username': reg.lichess_username, 'email': reg.email, 'is_active': True}
            )
            if player.rating is None:
                # This is automatically set, so don't change it if we already have a rating
                player.rating = reg.classical_rating
                player.save()

        if self.is_late:
            # Late registration
            next_round = Round.objects.filter(season=season, publish_pairings=False).order_by('number').first()
            if next_round is not None:
                with reversion.create_revision():
                    reversion.set_user(request.user)
                    reversion.set_comment('Approved registration.')
                    PlayerLateRegistration.objects.update_or_create(round=next_round, player=player,
                                                      defaults={'retroactive_byes': retroactive_byes,
                                                      'late_join_points': late_join_points})

        with reversion.create_revision():
            reversion.set_user(request.user)
            reversion.set_comment('Approved registration.')

            sp, created = SeasonPlayer.objects.update_or_create(
                player=player,
                season=season,
                defaults={'registration': reg, 'is_active': not self.is_late}
            )

            if created and self.league.competitor_type == 'team':
                # Add a yellow card for players that had a red card their previous season
                last_sp = player.seasonplayer_set.filter(season__league=self.league).exclude(season=season).order_by('-season__start_date').first()
                if last_sp is not None and last_sp.games_missed >= 2:
                    sp.games_missed = 1
                    sp.save()

        # Set availability
        for week_number in reg.weeks_unavailable.split(','):
            if week_number != '':
                round_ = Round.objects.filter(season=season, number=int(week_number)).first()
                if round_ is not None:
                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        reversion.set_comment('Approved registration.')
                        PlayerAvailability.objects.update_or_create(player=player, round=round_, defaults={'is_available': False})

        if season.league.competitor_type == 'team':
            subject = render_to_string('tournament/emails/team_registration_approved_subject.txt', {'reg': reg})
            msg_plain = render_to_string('tournament/emails/team_registration_approved.txt', {'reg': reg})
            msg_html = render_to_string('tournament/emails/team_registration_approved.html', {'reg': reg})
        elif season.league.rating_type == 'blitz':
            # TODO: Make the email template a league setting
            subject = render_to_string('tournament/emails/blitz_registration_approved_subject.txt', {'reg': reg})
            msg_plain = render_to_string('tournament/emails/blitz_registration_approved.txt', {'reg': reg})
            msg_html = render_to_string('tournament/emails/blitz_registration_approved.html', {'reg': reg})
        else:
            subject = render_to_string('tournament/emails/lone_registration_approved_subject.txt', {'reg': reg})
            msg_plain = render_to_string('tournament/emails/lone_registration_approved.txt', {'reg': reg})
            msg_html = render_to_string('tournament/emails/lone_registration_approved.html', {'reg': reg})

        if send_confirm_email:
            try:
                send_mail(
                    subject,
                    msg_plain,
                    settings.DEFAULT_FROM_EMAIL,
                    [reg.email],
                    html_message=msg_html,
                )
                if modeladmin:
                    modeladmin.message_user(request, 'Confirmation email sent to "%s".' % reg.email, messages.INFO)
            except SMTPException:
                logger.exception('A confirmation email could not be sent.')
                if modeladmin:
                    modeladmin.message_user(request, 'A confirmation email could not be sent.', messages.ERROR)

        if invite_to_slack:
            try:
                if request.user.has_perm('tournament.invite_to_slack'):
                    slackapi.invite_user(reg.email)
                    if modeladmin:
                        modeladmin.message_user(request, 'Slack invitation sent to "%s".' % reg.email, messages.INFO)
                elif modeladmin:
                    modeladmin.message_user(request, 'You don\'t have permission to invite players to slack.', messages.ERROR)
            except slackapi.AlreadyInTeam:
                if modeladmin:
                    modeladmin.message_user(request, 'The player is already in the slack group.', messages.WARNING)
            except slackapi.AlreadyInvited:
                if modeladmin:
                    modeladmin.message_user(request, 'The player has already been invited to the slack group.', messages.WARNING)

        with reversion.create_revision():
            reversion.set_user(request.user)
            reversion.set_comment('Approved registration.')
            reg.status = 'approved'
            reg.status_changed_by = request.user.username
            reg.status_changed_date = timezone.now()
            reg.save()

        if modeladmin:
            modeladmin.message_user(request, 'Registration for "%s" approved.' % reg.lichess_username, messages.INFO)
