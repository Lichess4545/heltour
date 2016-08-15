from __future__ import unicode_literals

from django.db import models
from django.utils.crypto import get_random_string
from ckeditor.fields import RichTextField
from django.core.validators import RegexValidator
from datetime import timedelta
from django.utils import timezone

# Helper function to find an item in a list by its properties
def find(lst, **prop_values):
    for k, v in prop_values.items():
        lst = [obj for obj in lst if getattr(obj, k) == v]
    return next(iter(lst), None)

#-------------------------------------------------------------------------------
class _BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)
    class Meta:
        abstract = True

THEME_OPTIONS = (
    ('blue', 'Blue'),
    ('green', 'Green'),
)
COMPETITOR_TYPE_OPTIONS = (
    ('team', 'Team'),
    ('individual', 'Individual'),
)
PAIRING_TYPE_OPTIONS = (
    ('swiss-dutch', 'Swiss Tournament: Dutch Algorithm'),
)

#-------------------------------------------------------------------------------
class League(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    tag = models.SlugField(unique=True, help_text='The league will be accessible at /{league_tag}/')
    theme = models.CharField(max_length=32, choices=THEME_OPTIONS)
    display_order = models.PositiveIntegerField(default=0)
    competitor_type = models.CharField(max_length=32, choices=COMPETITOR_TYPE_OPTIONS)
    pairing_type = models.CharField(max_length=32, choices=PAIRING_TYPE_OPTIONS)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Season(_BaseModel):
    league = models.ForeignKey(League)
    name = models.CharField(max_length=255)
    tag = models.SlugField(help_text='The season will be accessible at /{league_tag}/season/{season_tag}/')
    start_date = models.DateTimeField(blank=True, null=True)
    rounds = models.PositiveIntegerField()
    boards = models.PositiveIntegerField(blank=True, null=True)

    is_active = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    registration_open = models.BooleanField(default=False)

    class Meta:
        unique_together = (('league', 'name'), ('league', 'tag'))
        permissions = (
            ('edit_rosters', 'Can edit rosters'),
        )

    def __init__(self, *args, **kwargs):
        super(Season, self).__init__(*args, **kwargs)
        self.initial_rounds = self.rounds
        self.initial_start_date = self.start_date

    def save(self, *args, **kwargs):
        # TODO: Add validation to prevent changes after a certain point
        rounds_changed = self.pk is None or self.rounds != self.initial_rounds
        start_date_changed = self.pk is None or self.start_date != self.initial_start_date

        if self.is_completed and self.registration_open:
            self.registration_open = False
        super(Season, self).save(*args, **kwargs)

        if rounds_changed or start_date_changed:
            date = self.start_date
            for round_num in range(1, self.rounds + 1):
                # TODO: Allow round duration to be customized
                next_date = date + timedelta(days=7) if date is not None else None
                Round.objects.update_or_create(season=self, number=round_num, defaults={'start_date': date, 'end_date': next_date})
                date = next_date

    def calculate_scores(self):
        if self.league.competitor_type == 'team':
            self._calculate_team_scores()
        else:
            self._calculate_lone_scores()

    def _calculate_team_scores(self):
        # Note: The scores are calculated in a particular way to allow easy adding of new tiebreaks
        score_dict = {}

        last_round = None
        for round_ in self.round_set.filter(is_completed=True).order_by('number'):
            round_pairings = round_.teampairing_set.all()
            for team in Team.objects.filter(season=self):
                white_pairing = find(round_pairings, white_team_id=team.id)
                black_pairing = find(round_pairings, black_team_id=team.id)
                if white_pairing is not None:
                    self._increment_team_score(score_dict, round_, last_round, team, white_pairing.black_team, white_pairing.white_points, white_pairing.black_points)
                elif black_pairing is not None:
                    self._increment_team_score(score_dict, round_, last_round, team, black_pairing.white_team, black_pairing.black_points, black_pairing.white_points)
                else:
                    score_dict[(team, round_)] = score_dict[(team, last_round)][:3] + (0,) if last_round is not None else (0, 0, 0, 0)
            last_round = round_

        team_scores = TeamScore.objects.filter(team__season=self)
        for score in team_scores:
            if last_round is None:
                score.match_count = 0
                score.match_points = 0
                score.game_points = 0
            else:
                score.match_count, score.match_points, score.game_points, _ = score_dict[(score.team, last_round)]
            score.save()

    def _increment_team_score(self, score_dict, round_, last_round, team, opponent, points, opponent_points):
        match_count, match_points, game_points, _ = score_dict[(team, last_round)] if last_round is not None else (0, 0, 0, 0)
        match_count += 1
        game_points += points
        if points > opponent_points:
            match_points += 2
        elif points == opponent_points:
            match_points += 1
        score_dict[(team, round_)] = (match_count, match_points, game_points, points)

    def _calculate_lone_scores(self):
        score_dict = {}
        last_round = None
        for round_ in self.round_set.filter(is_completed=True).order_by('number'):
            pairings = round_.loneplayerpairing_set.all().nocache()
            changes = RoundChange.objects.filter(round=round_)
            for sp in SeasonPlayer.objects.filter(season=self):
                white_pairing = find(pairings, white_id=sp.player_id)
                black_pairing = find(pairings, black_id=sp.player_id)
                bye = find(changes, player_id=sp.player_id, action='half-point-bye')
                if white_pairing is not None:
                    self._increment_lone_score(score_dict, round_, last_round, sp.player_id, white_pairing.black_id, int(white_pairing.white_score() * 2), white_pairing.game_played())
                elif black_pairing is not None:
                    self._increment_lone_score(score_dict, round_, last_round, sp.player_id, black_pairing.white_id, int(black_pairing.black_score() * 2), black_pairing.game_played())
                elif bye is not None:
                    self._increment_lone_score(score_dict, round_, last_round, sp.player_id, None, 1, False)
                else:
                    self._increment_lone_score(score_dict, round_, last_round, sp.player_id, None, 0, False)
            last_round = round_

        player_scores = LonePlayerScore.objects.filter(season_player__season=self)
        for score in player_scores:
            player_id = score.season_player.player_id
            if last_round is None:
                score.points = 0
                score.tiebreak1 = 0
                score.tiebreak2 = 0
                score.tiebreak3 = 0
                score.tiebreak4 = 0
            else:
                total, _, cumul, _, _ = score_dict[(score.season_player.player_id, last_round.number)]
                score.points = total

                # Tiebreak calculations

                opponent_scores = []
                opponent_cumuls = []
                for round_number in range(1, last_round.number + 1):
                    _, _, _, round_opponent, played = score_dict[(player_id, round_number)]
                    if played and round_opponent is not None:
                        opponent_scores.append(score_dict[(round_opponent, last_round.number)][1])
                        opponent_cumuls.append(score_dict[(round_opponent, last_round.number)][2])
                    else:
                        opponent_scores.append(0)
                opponent_scores.sort()

                # TB1: Modified Median
                median_scores = opponent_scores
                skip = 2 if last_round.number >= 9 else 1
                if score.points <= last_round.number:
                    median_scores = median_scores[:-skip]
                if score.points >= last_round.number:
                    median_scores = median_scores[skip:]
                score.tiebreak1 = sum(median_scores)

                # TB2: Solkoff
                score.tiebreak2 = sum(opponent_scores)

                # TB3: Cumulative
                score.tiebreak3 = cumul

                # TB4: Cumulative opponent
                score.tiebreak4 = sum(opponent_cumuls)

            score.save()

    def _increment_lone_score(self, score_dict, round_, last_round, player_id, opponent, score, played):
        total, mm_total, cumul, _, _ = score_dict[(player_id, last_round.number)] if last_round is not None else (0, 0, 0, None, False)
        total += score
        cumul += total
        if played:
            mm_total += score
        else:
            # Special cases for unplayed games
            mm_total += 1
            cumul -= score
        score_dict[(player_id, round_.number)] = (total, mm_total, cumul, opponent, played)

    def is_started(self):
        return self.start_date is not None and self.start_date < timezone.now()

    def end_date(self):
        last_round = self.round_set.filter(number=self.rounds).first()
        if last_round is not None:
            return last_round.end_date
        return None

    def board_number_list(self):
        return [n for n in range(1, self.boards + 1)]

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Round(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField(verbose_name='round number')
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    publish_pairings = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('generate_pairings', 'Can generate and review pairings'),
        )

    def __init__(self, *args, **kwargs):
        super(Round, self).__init__(*args, **kwargs)
        self.initial_is_completed = self.is_completed

    def save(self, *args, **kwargs):
        is_completed_changed = self.pk is None and self.is_completed or self.is_completed != self.initial_is_completed
        super(Round, self).save(*args, **kwargs)
        if is_completed_changed:
            self.season.calculate_scores()

    def __unicode__(self):
        return "%s - Round %d" % (self.season, self.number)

#-------------------------------------------------------------------------------
class Player(_BaseModel):
    # TODO: we should find out the real restrictions on a lichess username and
    #       duplicate them here.
    # Note: a case-insensitive unique index for lichess_username is added via migration to the DB
    lichess_username = models.CharField(max_length=255)
    rating = models.PositiveIntegerField(blank=True, null=True)
    games_played = models.PositiveIntegerField(blank=True, null=True)
    email = models.CharField(max_length=255, blank=True)
    is_moderator = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    def __unicode__(self):
        if self.rating is None:
            return self.lichess_username
        else:
            return "%s (%d)" % (self.lichess_username, self.rating)

ROUND_CHANGE_OPTIONS = (
    ('register', 'Register'),
    ('withdraw', 'Withdraw'),
    ('half-point-bye', 'Half-Point Bye'),
)

#-------------------------------------------------------------------------------
class RoundChange(_BaseModel):
    round = models.ForeignKey(Round)
    player = models.ForeignKey(Player)
    action = models.CharField(max_length=255, choices=ROUND_CHANGE_OPTIONS)

    def __unicode__(self):
        return "%s - %s - %s" % (self.round, self.player, self.action)

#-------------------------------------------------------------------------------
class Team(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField(verbose_name='team number')
    name = models.CharField(max_length=255, verbose_name='team name')
    is_active = models.BooleanField(default=True)

    seed_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = (('season', 'number'), ('season', 'name'))

    def boards(self):
        team_members = self.teammember_set.all()
        return [(n, find(team_members, board_number=n)) for n in Season.objects.get(pk=self.season_id).board_number_list()]

    def average_rating(self):
        n = 0
        total = 0.0
        for _, board in self.boards():
            if board is not None and board.player.rating is not None:
                n += 1
                total += board.player.rating
        return total / n if n > 0 else None

    def __unicode__(self):
        return "%s - %s" % (self.season, self.name)

BOARD_NUMBER_OPTIONS = (
    (1, '1'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5'),
    (6, '6'),
)

#-------------------------------------------------------------------------------
class TeamMember(_BaseModel):
    team = models.ForeignKey(Team)
    player = models.ForeignKey(Player)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    is_captain = models.BooleanField(default=False)
    is_vice_captain = models.BooleanField(default=False)

    class Meta:
        unique_together = ('team', 'board_number')

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class TeamScore(_BaseModel):
    team = models.OneToOneField(Team)
    match_count = models.PositiveIntegerField(default=0)
    match_points = models.PositiveIntegerField(default=0)
    game_points = models.PositiveIntegerField(default=0)

    def match_points_display(self):
        return str(self.match_points)

    def game_points_display(self):
        return "%g" % (self.game_points / 2.0)

    def round_scores(self):
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for round_ in Round.objects.filter(season_id=self.team.season_id).order_by('number'):
            if round_ is None or not round_.is_completed:
                yield None
                continue
            points = None
            white_pairing = find(white_pairings, round_id=round_.id)
            black_pairing = find(black_pairings, round_id=round_.id)
            if white_pairing is not None:
                points = white_pairing.white_points / 2.0
            if black_pairing is not None:
                points = black_pairing.black_points / 2.0
            yield points

    def cross_scores(self):
        other_teams = Team.objects.filter(season_id=self.team.season_id).order_by('number')
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for other_team in other_teams:
            white_pairing = find(white_pairings, black_team_id=other_team.pk)
            black_pairing = find(black_pairings, white_team_id=other_team.pk)
            points = None
            id = None
            if white_pairing is not None and white_pairing.round.is_completed:
                points = white_pairing.white_points / 2.0
                id = white_pairing.pk
            if black_pairing is not None and black_pairing.round.is_completed:
                points = black_pairing.black_points / 2.0
                id = black_pairing.pk
            yield other_team.number, points, id

    def __unicode__(self):
        return "%s" % (self.team)

    def __cmp__(self, other):
        result = self.match_points - other.match_points
        if result != 0:
            return result
        result = self.game_points - other.game_points
        return result

#-------------------------------------------------------------------------------
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(Team, related_name="pairings_as_white")
    black_team = models.ForeignKey(Team, related_name="pairings_as_black")
    round = models.ForeignKey(Round)
    pairing_order = models.PositiveIntegerField()

    white_points = models.PositiveIntegerField(default=0)
    black_points = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = ('white_team', 'black_team', 'round')

    def __init__(self, *args, **kwargs):
        super(TeamPairing, self).__init__(*args, **kwargs)
        self.initial_white_points = self.white_points
        self.initial_black_points = self.black_points

    def save(self, *args, **kwargs):
        points_changed = self.pk is None or self.white_points != self.initial_white_points or self.black_points != self.initial_black_points
        super(TeamPairing, self).save(*args, **kwargs)
        if points_changed and self.round.is_completed:
            self.round.season.calculate_scores()

    def refresh_points(self):
        self.white_points = 0
        self.black_points = 0
        for pairing in self.teamplayerpairing_set.all().nocache():
            if pairing.board_number % 2 == 1:
                self.white_points += (pairing.white_score() or 0) * 2
                self.black_points += (pairing.black_score() or 0) * 2
            else:
                self.white_points += (pairing.black_score() or 0) * 2
                self.black_points += (pairing.white_score() or 0) * 2

    def white_points_display(self):
        return "%g" % (self.white_points / 2.0)

    def black_points_display(self):
        return "%g" % (self.black_points / 2.0)

    def season_name(self):
        return "%s" % self.round.season.name

    def round_number(self):
        return "%d" % self.round.number

    def white_team_name(self):
        return "%s" % self.white_team.name

    def black_team_name(self):
        return "%s" % self.black_team.name

    def __unicode__(self):
        return "%s - %s - %s" % (self.round, self.white_team.name, self.black_team.name)

#-------------------------------------------------------------------------------
class PlayerPairing(_BaseModel):
    white = models.ForeignKey(Player, blank=True, null=True, related_name="pairings_as_white")
    black = models.ForeignKey(Player, blank=True, null=True, related_name="pairings_as_black")

    result = models.CharField(max_length=16, blank=True)
    game_link = models.URLField(max_length=1024, blank=True)
    scheduled_time = models.DateTimeField(blank=True, null=True)

    def __init__(self, *args, **kwargs):
        super(PlayerPairing, self).__init__(*args, **kwargs)
        self.initial_result = self.result
        self.initial_white = self.white
        self.initial_black = self.black

    def white_score(self):
        if self.result == '1-0' or self.result == '1X-0F' or self.result == 'FULL BYE' and self.white is not None:
            return 1
        elif self.result == '0-1' or self.result == '0F-1X' or self.result == '0F-0F' or self.result == 'WITHDRAW':
            return 0
        elif self.result == '1/2-1/2' or self.result == '1/2Z-1/2Z' or self.result == 'BYE':
            return 0.5
        return None

    def black_score(self):
        if self.result == '0-1' or self.result == '0F-1X' or self.result == 'FULL BYE' and self.black is not None:
            return 1
        elif self.result == '1-0' or self.result == '1X-0F' or self.result == '0F-0F' or self.result == 'WITHDRAW':
            return 0
        elif self.result == '1/2-1/2' or self.result == '1/2Z-1/2Z' or self.result == 'BYE':
            return 0.5
        return None

    def game_played(self):
        return self.result in ('1-0', '1/2-1/2', '0-1')

    def __unicode__(self):
        return "%s - %s" % (self.white, self.black)

    def save(self, *args, **kwargs):
        result_changed = self.pk is None or self.result != self.initial_result
        white_changed = self.pk is None or self.white != self.initial_white
        black_changed = self.pk is None or self.black != self.initial_black
        super(PlayerPairing, self).save(*args, **kwargs)
        if hasattr(self, 'teamplayerpairing') and result_changed:
            self.teamplayerpairing.team_pairing.refresh_points()
            self.teamplayerpairing.team_pairing.save()
        if hasattr(self, 'loneplayerpairing'):
            if result_changed and self.loneplayerpairing.round.is_completed:
                self.loneplayerpairing.round.season.calculate_scores()
            # If the players for a PlayerPairing in the current round are edited, then we can update the player ranks
            if (white_changed or black_changed) and self.loneplayerpairing.round.publish_pairings and not self.loneplayerpairing.round.is_completed:
                self.loneplayerpairing.refresh_ranks()
                self.loneplayerpairing.save()
            # If the players for a PlayerPairing in a previous round are edited, then the player ranks will be out of
            # date but we can't recalculate them
            if white_changed and self.loneplayerpairing.round.is_completed:
                self.loneplayerpairing.white_rank = None
                self.loneplayerpairing.save()
            if black_changed and self.loneplayerpairing.round.is_completed:
                self.loneplayerpairing.black_rank = None
                self.loneplayerpairing.save()

#-------------------------------------------------------------------------------
class TeamPlayerPairing(PlayerPairing):
    team_pairing = models.ForeignKey(TeamPairing)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    class Meta:
        unique_together = ('team_pairing', 'board_number')

    def white_team(self):
        return self.team_pairing.white_team if self.board_number % 2 == 1 else self.team_pairing.black_team

    def black_team(self):
        return self.team_pairing.black_team if self.board_number % 2 == 1 else self.team_pairing.white_team

    def white_team_player(self):
        return self.white if self.board_number % 2 == 1 else self.black

    def black_team_player(self):
        return self.black if self.board_number % 2 == 1 else self.white

    def white_team_score(self):
        return self.white_score() if self.board_number % 2 == 1 else self.black_score()

    def black_team_score(self):
        return self.black_score() if self.board_number % 2 == 1 else self.white_score()

    def white_team_name(self):
        return "%s" % self.white_team().name

    def black_team_name(self):
        return "%s" % self.black_team().name

    def season_name(self):
        return "%s" % self.team_pairing.round.season.name

    def round_number(self):
        return "%d" % self.team_pairing.round.number

    def save(self, *args, **kwargs):
        result_changed = self.pk is None or self.result != self.initial_result
        super(TeamPlayerPairing, self).save(*args, **kwargs)
        if result_changed:
            self.team_pairing.refresh_points()
            self.team_pairing.save()

#-------------------------------------------------------------------------------
class LonePlayerPairing(PlayerPairing):
    round = models.ForeignKey(Round)
    pairing_order = models.PositiveIntegerField()
    white_rank = models.PositiveIntegerField(blank=True, null=True)
    black_rank = models.PositiveIntegerField(blank=True, null=True)

    def refresh_ranks(self):
        player_scores = list(enumerate(sorted(LonePlayerScore.objects.filter(season_player__season=self.round.season).select_related('season_player').nocache(), key=lambda s: s.pairing_sort_key(), reverse=True), 1))
        player_rank_dict = {p.season_player.player_id: n for n, p in player_scores}
        self.white_rank = player_rank_dict.get(self.white_id, None)
        self.black_rank = player_rank_dict.get(self.black_id, None)

    def save(self, *args, **kwargs):
        result_changed = self.pk is None or self.result != self.initial_result
        super(LonePlayerPairing, self).save(*args, **kwargs)
        if result_changed and self.round.is_completed:
            self.round.season.calculate_scores()

REGISTRATION_STATUS_OPTIONS = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
)

PREVIOUS_SEASON_ALTERNATE_OPTIONS = (
    ('alternate', 'Yes, I was an alternate at the end of the last season.'),
    ('alternate_to_full_time', 'Yes, but I was able to find a consistent team (did not simply fill in for a week or two).'),
    ('full_time', 'No, I was not an alternate for the last season. I played the season.'),
    ('new', 'No, I was not an alternate for the last season. I am a new member / I took last season off.'),
)

ALTERNATE_PREFERENCE_OPTIONS = (
    ('alternate', 'Alternate'),
    ('full_time', 'Full Time'),
)

#-------------------------------------------------------------------------------
class Registration(_BaseModel):
    season = models.ForeignKey(Season)
    status = models.CharField(max_length=255, choices=REGISTRATION_STATUS_OPTIONS)
    status_changed_by = models.CharField(blank=True, max_length=255)
    status_changed_date = models.DateTimeField(blank=True, null=True)

    lichess_username = models.CharField(max_length=255)
    slack_username = models.CharField(max_length=255)
    email = models.EmailField(max_length=255)

    classical_rating = models.PositiveIntegerField()
    peak_classical_rating = models.PositiveIntegerField()
    has_played_20_games = models.BooleanField()
    already_in_slack_group = models.BooleanField()
    previous_season_alternate = models.CharField(max_length=255, choices=PREVIOUS_SEASON_ALTERNATE_OPTIONS)
    can_commit = models.BooleanField()
    friends = models.CharField(blank=True, max_length=1023)
    agreed_to_rules = models.BooleanField()
    alternate_preference = models.CharField(max_length=255, choices=ALTERNATE_PREFERENCE_OPTIONS)
    weeks_unavailable = models.CharField(blank=True, max_length=255)

    def __unicode__(self):
        return "%s" % (self.lichess_username)

    def previous_registrations(self):
        return Registration.objects.filter(lichess_username__iexact=self.lichess_username, date_created__lt=self.date_created)

    def other_seasons(self):
        return SeasonPlayer.objects.filter(player__lichess_username__iexact=self.lichess_username).exclude(season=self.season)

    def player(self):
        return Player.objects.filter(lichess_username__iexact=self.lichess_username).first()

#-------------------------------------------------------------------------------
class SeasonPlayer(_BaseModel):
    season = models.ForeignKey(Season)
    player = models.ForeignKey(Player)
    registration = models.ForeignKey(Registration, on_delete=models.SET_NULL, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    games_missed = models.PositiveIntegerField(default=0)
    unresponsive = models.BooleanField(default=False)
    seed_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = ('season', 'player')

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class LonePlayerScore(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer)
    points = models.PositiveIntegerField(default=0)
    late_join_points = models.PositiveIntegerField(default=0)
    tiebreak1 = models.PositiveIntegerField(default=0)
    tiebreak2 = models.PositiveIntegerField(default=0)
    tiebreak3 = models.PositiveIntegerField(default=0)
    tiebreak4 = models.PositiveIntegerField(default=0)

    def round_scores(self, player_number_dict, white_pairings_dict, black_pairings_dict, round_changes_dict, include_current=False):
        white_pairings = white_pairings_dict.get(self.season_player.player, [])
        black_pairings = black_pairings_dict.get(self.season_player.player, [])
        cumul_score = 0.0
        for round_ in Round.objects.filter(season=self.season_player.season).order_by('number'):
            if not round_.is_completed and (not include_current or not round_.publish_pairings):
                yield (None, None)
                continue

            result_type = None
            opponent = None
            color = None

            white_pairing = find(white_pairings, round_id=round_.id)
            black_pairing = find(black_pairings, round_id=round_.id)
            round_changes = round_changes_dict.get((round_, self.season_player.player), [])
            bye = find(round_changes, action='half-point-bye')

            if white_pairing is not None and white_pairing.black is not None:
                opponent = white_pairing.black
                score = white_pairing.white_score()
                if white_pairing.game_played() or score is None:
                    # Normal result
                    color = 'W'
                    result_type = 'W' if score == 1.0 else 'D' if score == 0.5 else 'L' if score == 0.0 else ''
                else:
                    # Special result
                    result_type = 'X' if score == 1.0 else 'Z' if score == 0.5 else 'F' if score == 0.0 else ''
            elif black_pairing is not None and black_pairing.white is not None:
                opponent = black_pairing.white
                score = black_pairing.black_score()
                if black_pairing.game_played() or score is None:
                    # Normal result
                    color = 'B'
                    result_type = 'W' if score == 1.0 else 'D' if score == 0.5 else 'L' if score == 0.0 else ''
                else:
                    # Special result
                    result_type = 'X' if score == 1.0 else 'Z' if score == 0.5 else 'F' if score == 0.0 else ''
            elif bye is not None:
                score = 0.5
                result_type = 'H'
            else:
                score = 0.0
                result_type = 'U'

            if score is not None:
                cumul_score += score

            yield (result_type, player_number_dict.get(opponent, 0), color, cumul_score)

    def pairing_points_display(self):
        return "%.1f" % ((self.points + self.late_join_points) / 2.0)

    def final_standings_points_display(self):
        return "%.1f" % (self.points / 2.0)

    def late_join_points_display(self):
        return "%.1f" % (self.late_join_points / 2.0)

    def tiebreak1_display(self):
        return "%g" % (self.tiebreak1 / 2.0)

    def tiebreak2_display(self):
        return "%g" % (self.tiebreak2 / 2.0)

    def tiebreak3_display(self):
        return "%g" % (self.tiebreak3 / 2.0)

    def tiebreak4_display(self):
        return "%g" % (self.tiebreak4 / 2.0)

    def pairing_sort_key(self):
        return (self.points + self.late_join_points, self.tiebreak1, self.tiebreak2, self.tiebreak3, self.tiebreak4, self.season_player.player.rating)

    def final_standings_sort_key(self):
        return (self.points, self.tiebreak1, self.tiebreak2, self.tiebreak3, self.tiebreak4, self.season_player.player.rating)

    def __unicode__(self):
        return "%s" % (self.season_player)

#-------------------------------------------------------------------------------
class PlayerAvailability(_BaseModel):
    round = models.ForeignKey(Round)
    player = models.ForeignKey(Player)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'player availabilities'

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class Alternate(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    def update_board_number(self):
        season = self.season_player.season
        player = self.season_player.player
        buckets = AlternateBucket.objects.filter(season=season)
        if len(buckets) == season.boards and player.rating is not None:
            for b in buckets:
                if b.contains(player.rating):
                    self.board_number = b.board_number
                    self.save()

    def priority_date(self):
        most_recent_assign = AlternateAssignment.objects.filter(player=self.season_player.player).order_by('-round__start_date').first()

        if most_recent_assign is not None:
            round_date = most_recent_assign.round.start_date
            if round_date is not None:
                return round_date

        if self.season_player.registration is not None:
            return self.season_player.registration.date_created

        return self.date_created

    def __unicode__(self):
        return "%s" % self.season_player

#-------------------------------------------------------------------------------
class AlternateAssignment(_BaseModel):
    round = models.ForeignKey(Round)
    team = models.ForeignKey(Team)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    player = models.ForeignKey(Player)

    class Meta:
        unique_together = ('round', 'team', 'board_number')

    def save(self, *args, **kwargs):
        super(AlternateAssignment, self).save(*args, **kwargs)

        # Find and update any current pairings
        white_pairing = self.team.pairings_as_white.filter(round=self.round).first()
        if white_pairing is not None:
            pairing = white_pairing.teamplayerpairing_set.filter(board_number=self.board_number).nocache().first()
            if pairing is not None:
                if self.board_number % 2 == 1:
                    pairing.white = self.player
                else:
                    pairing.black = self.player
                pairing.save()
        black_pairing = self.team.pairings_as_black.filter(round=self.round).first()
        if black_pairing is not None:
            pairing = black_pairing.teamplayerpairing_set.filter(board_number=self.board_number).nocache().first()
            if pairing is not None:
                if self.board_number % 2 == 1:
                    pairing.black = self.player
                else:
                    pairing.white = self.player
                pairing.save()

    def __unicode__(self):
        return "%s - %s - Board %d" % (self.round, self.team.name, self.board_number)

#-------------------------------------------------------------------------------
class AlternateBucket(_BaseModel):
    season = models.ForeignKey(Season)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    min_rating = models.PositiveIntegerField(null=True, blank=True)
    max_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('season', 'board_number')

    def contains(self, rating):
        return (self.min_rating is None or rating > self.min_rating) and (self.max_rating is None or rating <= self.max_rating)

    def __unicode__(self):
        return "Board %d (%s, %s]" % (self.board_number, self.min_rating, self.max_rating)

def create_api_token():
    return get_random_string(length=32)

#-------------------------------------------------------------------------------
class ApiKey(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class Document(_BaseModel):
    name = models.CharField(max_length=255)
    content = RichTextField()

    def __unicode__(self):
        return self.name

LEAGUE_DOCUMENT_TYPES = (
    ('faq', 'FAQ'),
    ('rules', 'Rules'),
    ('intro', 'Intro'),
    ('slack-welcome', 'Slack Welcome'),
)

#-------------------------------------------------------------------------------
class LeagueDocument(_BaseModel):
    league = models.ForeignKey(League)
    document = models.ForeignKey(Document)
    tag = models.SlugField(help_text='The document will be accessible at /{league_tag}/document/{document_tag}/')
    type = models.CharField(blank=True, max_length=255, choices=LEAGUE_DOCUMENT_TYPES)

    class Meta:
        unique_together = ('league', 'tag')

    def __unicode__(self):
        return self.document.name
