import reversion
from django.contrib import messages
from heltour.tournament.models import *
from heltour.tournament import pairinggen, signals

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

        if alternates_only or not self.season.alternates_manager_enabled():
            members_by_board = [TeamMember.objects.filter(team__season=self.season, board_number=n + 1) for n in range(self.season.boards)]
            ratings_by_board = [sorted([float(m.player.rating) for m in m_list]) for m_list in members_by_board]
            alternates = Alternate.objects.filter(season_player__season=self.season).select_related('season_player__player').nocache()

            boundaries = self.calc_alternate_boundaries(ratings_by_board)
            self.smooth_alternate_boundaries(boundaries, alternates, ratings_by_board)
            self.update_alternate_buckets(boundaries)
            self.assign_alternates_to_buckets()

    def update_teammember_order(self):
        for team in self.season.team_set.all():
            with reversion.create_revision():
                change_descriptions = []
                members = list(team.teammember_set.all())
                members.sort(key=lambda m: m.player.rating, reverse=True)
                occupied_boards = [m.board_number for m in members]
                occupied_boards.sort()
                for i, board_number in enumerate(occupied_boards):
                    m = members[i]
                    if m.board_number != board_number:
                        old_member = TeamMember.objects.filter(team=team, board_number=board_number).first()
                        new_member, _ = TeamMember.objects.update_or_create(team=team, board_number=board_number, \
                                                               defaults={ 'player': m.player, 'is_captain': m.is_captain,
                                                                          'is_vice_captain': m.is_vice_captain })
                        change_descriptions.append('changed board %d from "%s" to "%s"' % (board_number, old_member, new_member))
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

    def smooth_alternate_boundaries(self, boundaries, alternates, ratings_by_board):
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
                higher_board_min = (ratings_by_board[i][0] + ratings_by_board[i][1]) / 2
                lower_board_max = (ratings_by_board[i + 1][-1] + ratings_by_board[i + 1][-2]) / 2
                if boundary < higher_board_min and boundary < lower_board_max:
                    delta_up = min(higher_board_min, lower_board_max) - boundary
                    delta_down = 0
                elif boundary > higher_board_min and boundary > lower_board_max:
                    delta_up = 0
                    delta_down = boundary - max(higher_board_min, lower_board_max)
                else:
                    delta_up = max(higher_board_min, lower_board_max) - boundary
                    delta_down = boundary - min(higher_board_min, lower_board_max)
                up_step_sizes.append(delta_up / float(iter_count))
                down_step_sizes.append(delta_down / float(iter_count))

            # Start iterating the smoothing algorithm
            for _ in range(iter_count):
                # Calculate the number of alternates in each bucket
                bucket_counts = [0] * self.season.boards
                for alt in alternates:
                    r = alt.season_player.player.rating
                    for i in range(self.season.boards):
                        if r > boundaries[i + 1] or boundaries[i + 1] == None:
                            bucket_counts[i] += 1
                            break

                # Move the boundaries of uneven buckets
                for i in range(self.season.boards - 1):
                    if bucket_counts[i] > bucket_counts[i + 1] + 1:
                        boundaries[i + 1] += up_step_sizes[i]
                    if bucket_counts[i] < bucket_counts[i + 1] - 1:
                        boundaries[i + 1] -= down_step_sizes[i]

    def update_alternate_buckets(self, boundaries):
        # Update the buckets
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
