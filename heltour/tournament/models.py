from __future__ import unicode_literals

from django.db import models, transaction
from django.utils.crypto import get_random_string
from ckeditor_uploader.fields import RichTextUploadingField
from django.core.validators import RegexValidator
from datetime import timedelta
from django.utils import timezone
from django import forms as django_forms
from collections import namedtuple, defaultdict
import re

# Helper function to find an item in a list by its properties
def find(lst, **prop_values):
    for k, v in prop_values.items():
        lst = [obj for obj in lst if _getnestedattr(obj, k) == v]
    return next(iter(lst), None)

def _getnestedattr(obj, k):
    for k2 in k.split('__'):
        if obj is None:
            return None
        obj = getattr(obj, k2)
    return obj

# Represents a positive number in increments of 0.5 (0, 0.5, 1, etc.)
class ScoreField(models.PositiveIntegerField):

    def from_db_value(self, value, expression, connection, context):
        if value is None:
            return None
        return value / 2.0

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        return int(value * 2)

    def to_python(self, value):
        if value is None or value == '':
            return None
        return float(value)

    def formfield(self, **kwargs):
        defaults = {'widget': django_forms.TextInput(attrs={'class': 'vIntegerField'}), 'initial': self.default}
        defaults.update(kwargs)
        return django_forms.FloatField(**defaults)

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

PLAYOFF_OPTIONS = (
    (0, 'None'),
    (1, 'Finals'),
    (2, 'Semi-Finals'),
    (3, 'Quarter-Finals'),
)

#-------------------------------------------------------------------------------
class Season(_BaseModel):
    league = models.ForeignKey(League)
    name = models.CharField(max_length=255)
    tag = models.SlugField(help_text='The season will be accessible at /{league_tag}/season/{season_tag}/')
    start_date = models.DateTimeField(blank=True, null=True)
    rounds = models.PositiveIntegerField()
    boards = models.PositiveIntegerField(blank=True, null=True)
    playoffs = models.PositiveIntegerField(default=0, choices=PLAYOFF_OPTIONS)

    is_active = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    registration_open = models.BooleanField(default=False)
    nominations_open = models.BooleanField(default=False)

    class Meta:
        unique_together = (('league', 'name'), ('league', 'tag'))
        permissions = (
            ('manage_players', 'Can manage players'),
            ('review_nominated_games', 'Can review nominated games'),
        )

    def __init__(self, *args, **kwargs):
        super(Season, self).__init__(*args, **kwargs)
        self.initial_rounds = self.rounds
        self.initial_start_date = self.start_date
        self.initial_is_completed = self.is_completed

    def save(self, *args, **kwargs):
        # TODO: Add validation to prevent changes after a certain point
        new_obj = self.pk is None
        rounds_changed = self.pk is None or self.rounds != self.initial_rounds
        start_date_changed = self.pk is None or self.start_date != self.initial_start_date
        is_completed_changed = self.pk is None or self.is_completed != self.initial_is_completed

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

        if new_obj:
            # Create a default set of prizes. This may need to be modified in the future
            SeasonPrize.objects.create(season=self, rank=1)
            SeasonPrize.objects.create(season=self, rank=2)
            SeasonPrize.objects.create(season=self, rank=3)
            if self.league.competitor_type != 'team':
                SeasonPrize.objects.create(season=self, max_rating=1600, rank=1)

        if is_completed_changed and self.is_completed:
            # Remove out of date prizes
            SeasonPrizeWinner.objects.filter(season_prize__season=self).delete()
            # Award prizes
            if self.league.competitor_type == 'team':
                team_scores = sorted(TeamScore.objects.filter(team__season=self).select_related('team').nocache(), reverse=True)
                for prize in self.seasonprize_set.filter(max_rating=None):
                    if prize.rank <= len(team_scores):
                        # Award a prize to each team member
                        for member in team_scores[prize.rank - 1].team.teammember_set.all():
                            SeasonPrizeWinner.objects.create(season_prize=prize, player=member.player)
            else:
                player_scores = sorted(LonePlayerScore.objects.filter(season_player__season=self).select_related('season_player__player').nocache(), key=lambda s: s.final_standings_sort_key(), reverse=True)
                for prize in self.seasonprize_set.all():
                    eligible_players = [s.season_player.player for s in player_scores if prize.max_rating is None or s.season_player.seed_rating < prize.max_rating]
                    if prize.rank <= len(eligible_players):
                        SeasonPrizeWinner.objects.create(season_prize=prize, player=eligible_players[prize.rank - 1])

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
                is_playoffs = round_.number > self.rounds - self.playoffs

                def increment_score(round_opponent, round_points, round_opponent_points, round_wins):
                    playoff_score, match_count, match_points, game_points, games_won, _, _, _, _ = score_dict[(team.pk, last_round.number)] if last_round is not None else (0, 0, 0, 0, 0, 0, 0, None, 0)
                    round_match_points = 0
                    if round_opponent is None:
                        if not is_playoffs:
                            # Bye
                            match_points += 1
                            game_points += self.boards / 2
                    else:
                        if is_playoffs:
                            print 'Playoff', round_points
                            if round_points > round_opponent_points:
                                playoff_score += 2 ** (self.rounds - round_.number)
                            # TODO: Handle ties/tiebreaks somehow?
                        else:
                            match_count += 1
                            if round_points > round_opponent_points:
                                round_match_points = 2
                            elif round_points == round_opponent_points:
                                round_match_points = 1
                            match_points += round_match_points
                            game_points += round_points
                            games_won += round_wins
                    score_dict[(team.pk, round_.number)] = _TeamScoreState(playoff_score, match_count, match_points, game_points, games_won, round_match_points, round_points, round_opponent, round_opponent_points)

                if white_pairing is not None:
                    increment_score(white_pairing.black_team_id, white_pairing.white_points, white_pairing.black_points, white_pairing.white_wins)
                elif black_pairing is not None:
                    increment_score(black_pairing.white_team_id, black_pairing.black_points, black_pairing.white_points, black_pairing.black_wins)
                else:
                    increment_score(None, 0, 0, 0)
            last_round = round_

        # Precalculate groups of tied teams for the tiebreaks
        tied_team_map = defaultdict(set)
        for team in Team.objects.filter(season=self):
            score_state = score_dict[(team.pk, last_round.number)]
            tied_team_map[(score_state.match_points, score_state.game_points)].add(team.pk)

        team_scores = TeamScore.objects.filter(team__season=self)
        for score in team_scores:
            if last_round is None:
                score.playoff_score = 0
                score.match_count = 0
                score.match_points = 0
                score.game_points = 0
                score.head_to_head = 0
                score.games_won = 0
                score.sb_score = 0
            else:
                score_state = score_dict[(score.team_id, last_round.number)]
                score.playoff_score = score_state.playoff_score
                score.match_count = score_state.match_count
                score.match_points = score_state.match_points
                score.game_points = score_state.game_points
                score.games_won = score_state.games_won

                # Tiebreak calculations
                tied_team_set = tied_team_map[(score_state.match_points, score_state.game_points)]
                score.head_to_head = 0
                score.sb_score = 0
                for round_number in range(1, last_round.number + 1):
                    round_state = score_dict[(score.team_id, round_number)]
                    opponent = round_state.round_opponent
                    if opponent is not None:
                        if round_state.round_match_points == 2:
                            score.sb_score += score_dict[(round_state.round_opponent, last_round.number)].match_points
                        elif round_state.round_match_points == 1:
                            score.sb_score += score_dict[(round_state.round_opponent, last_round.number)].match_points / 2.0
                        if opponent in tied_team_set:
                            score.head_to_head += round_state.match_points
            score.save()

    def _calculate_lone_scores(self):
        season_players = SeasonPlayer.objects.filter(season=self).select_related('loneplayerscore').nocache()
        seed_rating_dict = {sp.player_id: sp.seed_rating for sp in season_players}
        score_dict = {}
        last_round = None
        for round_ in self.round_set.filter(is_completed=True).order_by('number'):
            pairings = round_.loneplayerpairing_set.all().nocache()
            byes = PlayerBye.objects.filter(round=round_)
            for sp in season_players:
                white_pairing = find(pairings, white_id=sp.player_id)
                black_pairing = find(pairings, black_id=sp.player_id)
                bye = find(byes, player_id=sp.player_id)

                def increment_score(round_opponent, round_score, round_played):
                    total, mm_total, cumul, perf_total_rating, perf_score, perf_n, _, _ = score_dict[(sp.player_id, last_round.number)] if last_round is not None else (0, 0, 0, 0, 0, 0, None, False)
                    total += round_score
                    cumul += total
                    if round_played:
                        mm_total += round_score
                        opp_rating = seed_rating_dict.get(round_opponent, None)
                        if opp_rating is not None:
                            perf_total_rating += opp_rating
                            perf_score += round_score
                            perf_n += 1
                    else:
                        # Special cases for unplayed games
                        mm_total += 0.5
                        cumul -= round_score
                    score_dict[(sp.player_id, round_.number)] = _LoneScoreState(total, mm_total, cumul, perf_total_rating, perf_score, perf_n, round_opponent, round_played)

                if white_pairing is not None:
                    increment_score(white_pairing.black_id, white_pairing.white_score() or 0, white_pairing.game_played())
                elif black_pairing is not None:
                    increment_score(black_pairing.white_id, black_pairing.black_score() or 0, black_pairing.game_played())
                elif bye is not None:
                    increment_score(None, bye.score(), False)
                else:
                    increment_score(None, 0, False)
            last_round = round_

        player_scores = [sp.get_loneplayerscore() for sp in season_players]

        for score in player_scores:
            player_id = score.season_player.player_id
            if last_round is None:
                score.points = 0
                score.tiebreak1 = 0
                score.tiebreak2 = 0
                score.tiebreak3 = 0
                score.tiebreak4 = 0
            else:
                score_state = score_dict[(score.season_player.player_id, last_round.number)]
                score.points = score_state.total

                # Tiebreak calculations

                opponent_scores = []
                opponent_cumuls = []
                for round_number in range(1, last_round.number + 1):
                    round_state = score_dict[(player_id, round_number)]
                    if round_state.round_played and round_state.round_opponent is not None:
                        opponent_scores.append(score_dict[(round_state.round_opponent, last_round.number)].mm_total)
                        opponent_cumuls.append(score_dict[(round_state.round_opponent, last_round.number)].cumul)
                    else:
                        opponent_scores.append(0)
                opponent_scores.sort()

                # TB1: Modified Median
                median_scores = opponent_scores
                skip = 2 if last_round.number >= 9 else 1
                if score.points <= last_round.number / 2.0:
                    median_scores = median_scores[:-skip]
                if score.points >= last_round.number / 2.0:
                    median_scores = median_scores[skip:]
                score.tiebreak1 = sum(median_scores)

                # TB2: Solkoff
                score.tiebreak2 = sum(opponent_scores)

                # TB3: Cumulative
                score.tiebreak3 = score_state.cumul

                # TB4: Cumulative opponent
                score.tiebreak4 = sum(opponent_cumuls)

                # Performance rating
                if score_state.perf_n >= 5:
                    average_opp_rating = int(round(score_state.perf_total_rating / float(score_state.perf_n)))
                    # Turn the score into a number from 0-100 (0 = 0%, 100 = 100%)
                    lookup_index = max(min(int(round(100.0 * score_state.perf_score / score_state.perf_n)), 100), 0)
                    # Use that number to get a rating difference from the FIDE lookup table
                    dp = fide_dp_lookup[lookup_index]
                    score.perf_rating = average_opp_rating + dp
                else:
                    score.perf_rating = None

            score.save()

    def is_started(self):
        return self.start_date is not None and self.start_date < timezone.now()

    def end_date(self):
        last_round = self.round_set.filter(number=self.rounds).first()
        if last_round is not None:
            return last_round.end_date
        return None

    def board_number_list(self):
        if self.boards is None:
            raise Exception('Tried to get board list but season.boards is None')
        return [n for n in range(1, self.boards + 1)]

    def __unicode__(self):
        return self.name

_TeamScoreState = namedtuple('_TeamScoreState', 'playoff_score, match_count, match_points, game_points, games_won, round_match_points, round_points, round_opponent, round_opponent_points')
_LoneScoreState = namedtuple('_LoneScoreState', 'total, mm_total, cumul, perf_total_rating, perf_score, perf_n, round_opponent, round_played')

# From https://www.fide.com/component/handbook/?id=174&view=article
# Used for performance rating calculations
fide_dp_lookup = [-800, -677, -589, -538, -501, -470, -444, -422, -401, -383, -366, -351, -336, -322, -309, -296, -284, -273, -262, -251,
                   - 240, -230, -220, -211, -202, -193, -184, -175, -166, -158, -149, -141, -133, -125, -117, -110, -102, -95, -87, -80, -72,
                   - 65, -57, -50, -43, -36, -29, -21, -14, -7, 0, 7, 14, 21, 29, 36, 43, 50, 57, 65, 72, 80, 87, 95, 102, 110, 117, 125, 133,
                   141, 149, 158, 166, 175, 184, 193, 202, 211, 220, 230, 240, 251, 262, 273, 284, 296, 309, 322, 336, 351, 366, 383, 401,
                   422, 444, 470, 501, 538, 589, 677, 800]

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

username_validator = RegexValidator('^[\w-]+$')

#-------------------------------------------------------------------------------
class Player(_BaseModel):
    # TODO: we should find out the real restrictions on a lichess username and
    #       duplicate them here.
    # Note: a case-insensitive unique index for lichess_username is added via migration to the DB
    lichess_username = models.CharField(max_length=255, validators=[username_validator])
    rating = models.PositiveIntegerField(blank=True, null=True)
    games_played = models.PositiveIntegerField(blank=True, null=True)
    email = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['lichess_username']

    def __unicode__(self):
        if self.rating is None:
            return self.lichess_username
        else:
            return "%s (%d)" % (self.lichess_username, self.rating)

#-------------------------------------------------------------------------------
class LeagueModerator(_BaseModel):
    league = models.ForeignKey(League)
    player = models.ForeignKey(Player)

    send_contact_emails = models.BooleanField(default=True)

    class Meta:
        unique_together = ('league', 'player')

    def __unicode__(self):
        return "%s - %s" % (self.league, self.player.lichess_username)

ROUND_CHANGE_OPTIONS = (
    ('register', 'Register'),
    ('withdraw', 'Withdraw'),
    ('half-point-bye', 'Half-Point Bye'),
)

#-------------------------------------------------------------------------------
class PlayerLateRegistration(_BaseModel):
    round = models.ForeignKey(Round)
    player = models.ForeignKey(Player)
    retroactive_byes = models.PositiveIntegerField(default=0)
    late_join_points = ScoreField(default=0)

    class Meta:
        unique_together = ('round', 'player')

    def perform_registration(self):
        with transaction.atomic():
            # Set the SeasonPlayer as active
            sp, _ = SeasonPlayer.objects.get_or_create(season=self.round.season, player=self.player)
            sp.is_active = True
            sp.save()

            # Create any retroactive byes (but don't overwrite existing byes/pairings)
            rounds = self.round.season.round_set.all()
            for i in range(self.retroactive_byes):
                round_number = self.round.number - i - 1
                round_ = find(rounds, number=round_number)
                pairings = round_.loneplayerpairing_set.filter(white=self.player) | round_.loneplayerpairing_set.filter(black=self.player)
                byes = round_.playerbye_set.filter(player=self.player)
                if pairings.count() == 0 and byes.count() == 0:
                    PlayerBye.objects.create(round=round_, player=self.player, type='half-point-bye')

            # Set the late-join points
            score = sp.get_loneplayerscore()
            score.late_join_points = self.late_join_points
            score.save()

    def __unicode__(self):
        return "%s - %s" % (self.round, self.player)

#-------------------------------------------------------------------------------
class PlayerWithdrawl(_BaseModel):
    round = models.ForeignKey(Round)
    player = models.ForeignKey(Player)

    class Meta:
        unique_together = ('round', 'player')

    def perform_withdrawl(self):
        with transaction.atomic():
            # Set the SeasonPlayer as inactive
            sp, _ = SeasonPlayer.objects.get_or_create(season=self.round.season, player=self.player)
            sp.is_active = False
            sp.save()

    def __unicode__(self):
        return "%s - %s" % (self.round, self.player)

BYE_TYPE_OPTIONS = (
    ('full-point-pairing-bye', 'Full-Point Bye (Pairing)'),
    ('full-point-bye', 'Full-Point Bye'),
    ('half-point-bye', 'Half-Point Bye'),
    ('zero-point-bye', 'Zero-Point Bye'),
)

#-------------------------------------------------------------------------------
class PlayerBye(_BaseModel):
    round = models.ForeignKey(Round)
    player = models.ForeignKey(Player)
    type = models.CharField(max_length=31, choices=BYE_TYPE_OPTIONS)
    player_rank = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = ('round', 'player')

    def __init__(self, *args, **kwargs):
        super(PlayerBye, self).__init__(*args, **kwargs)
        self.initial_round_id = self.round_id
        self.initial_player_id = self.player_id
        self.initial_type = self.type

    def refresh_rank(self, rank_dict=None):
        if rank_dict == None:
            rank_dict = lone_player_pairing_rank_dict(self.round.season)
        self.player_rank = rank_dict.get(self.player_id, None)

    def score(self):
        if self.type == 'full-point-bye' or self.type == 'full-point-pairing-bye':
            return 1
        elif self.type == 'half-point-bye':
            return 0.5
        else:
            return 0

    def __unicode__(self):
        return "%s - %s" % (self.player, self.get_type_display())

    def save(self, *args, **kwargs):
        round_changed = self.pk is None or self.round_id != self.initial_round_id
        player_changed = self.pk is None or self.player_id != self.initial_player_id
        type_changed = self.pk is None or self.type != self.initial_type
        if (round_changed or player_changed) and self.round.publish_pairings:
            if not self.round.is_completed:
                self.refresh_rank()
            else:
                self.player_rank = None
        super(PlayerBye, self).save(*args, **kwargs)
        if (round_changed or player_changed or type_changed) and self.round.is_completed:
            self.round.season.calculate_scores()

    def delete(self, *args, **kwargs):
        round_ = self.round
        super(PlayerBye, self).delete(*args, **kwargs)
        if round_.is_completed:
            round_.season.calculate_scores()

#-------------------------------------------------------------------------------
class Team(_BaseModel):
    season = models.ForeignKey(Season)
    number = models.PositiveIntegerField(verbose_name='team number')
    name = models.CharField(max_length=255, verbose_name='team name')
    is_active = models.BooleanField(default=True)

    seed_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = (('season', 'number'), ('season', 'name'))

    def get_teamscore(self):
        try:
            return self.teamscore
        except TeamScore.DoesNotExist:
            return TeamScore.objects.create(team=self)

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
    game_points = ScoreField(default=0)

    playoff_score = models.PositiveIntegerField(default=0)
    head_to_head = models.PositiveIntegerField(default=0)
    games_won = models.PositiveIntegerField(default=0)
    sb_score = ScoreField(default=0)

    def match_points_display(self):
        return str(self.match_points)

    def game_points_display(self):
        return "%g" % self.game_points

    def pairing_sort_key(self):
        return (self.match_points, self.game_points, self.team.seed_rating)

    def round_scores(self):
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for round_ in Round.objects.filter(season_id=self.team.season_id).order_by('number'):
            if round_ is None or not round_.is_completed:
                yield None, None, None
                continue
            points = None
            opp_points = None
            pk = None
            white_pairing = find(white_pairings, round_id=round_.id)
            black_pairing = find(black_pairings, round_id=round_.id)
            if white_pairing is not None:
                points = white_pairing.white_points
                opp_points = white_pairing.black_points
                pk = white_pairing.pk
            if black_pairing is not None:
                points = black_pairing.black_points
                opp_points = black_pairing.white_points
                pk = black_pairing.pk
            yield points, opp_points, pk

    def cross_scores(self):
        other_teams = Team.objects.filter(season_id=self.team.season_id).order_by('number')
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for other_team in other_teams:
            white_pairing = find(white_pairings, black_team_id=other_team.pk)
            black_pairing = find(black_pairings, white_team_id=other_team.pk)
            points = None
            opp_points = None
            pk = None
            if white_pairing is not None and white_pairing.round.is_completed:
                points = white_pairing.white_points
                opp_points = white_pairing.black_points
                pk = white_pairing.pk
            if black_pairing is not None and black_pairing.round.is_completed:
                points = black_pairing.black_points
                opp_points = black_pairing.white_points
                pk = black_pairing.pk
            yield other_team.number, points, opp_points, pk

    def __unicode__(self):
        return "%s" % (self.team)

    def __cmp__(self, other):
        return cmp((self.playoff_score, self.match_points, self.game_points, self.head_to_head, self.games_won, self.sb_score),
                   (other.playoff_score, other.match_points, other.game_points, other.head_to_head, other.games_won, other.sb_score))

#-------------------------------------------------------------------------------
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(Team, related_name="pairings_as_white")
    black_team = models.ForeignKey(Team, related_name="pairings_as_black")
    round = models.ForeignKey(Round)
    pairing_order = models.PositiveIntegerField()

    white_points = ScoreField(default=0)
    white_wins = models.PositiveIntegerField(default=0)
    black_points = ScoreField(default=0)
    black_wins = models.PositiveIntegerField(default=0)

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
        self.white_wins = 0
        self.black_wins = 0
        for pairing in self.teamplayerpairing_set.all().nocache():
            if pairing.board_number % 2 == 1:
                self.white_points += pairing.white_score() or 0
                self.black_points += pairing.black_score() or 0
                if pairing.white_score() == 1:
                    self.white_wins += 1
                if pairing.black_score() == 1:
                    self.black_wins += 1
            else:
                self.white_points += pairing.black_score() or 0
                self.black_points += pairing.white_score() or 0
                if pairing.black_score() == 1:
                    self.white_wins += 1
                if pairing.white_score() == 1:
                    self.black_wins += 1

    def white_points_display(self):
        return "%g" % self.white_points

    def black_points_display(self):
        return "%g" % self.black_points

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

# Game link structure:
# 1. (Optional) http/s prefix
# 2. (Optional) Subdomain, e.g. "en."
# 3. "lichess.org/"
# 4. The gameid (8 chars)
# 5. (Optional) Extended id for games in progress (4 chars)
# 6. (Optional) Any junk at the end, e.g. "/black", etc.
game_link_regex = re.compile(r'^(https?://)?([a-z]+\.)?lichess\.org/([A-Za-z0-9]{8})([A-Za-z0-9]{4})?([/#\?].*)?$')
game_link_validator = RegexValidator(game_link_regex)

def get_gameid_from_gamelink(gamelink):
    if gamelink is None or gamelink == '':
        return None
    match = game_link_regex.match(gamelink)
    if match is None:
        return None
    return match.group(3)

def get_gamelink_from_gameid(gameid):
    return 'https://en.lichess.org/%s' % gameid

def normalize_gamelink(gamelink):
    if gamelink == '':
        return gamelink, True
    gameid = get_gameid_from_gamelink(gamelink)
    if gameid is None:
        return gamelink, False
    return get_gamelink_from_gameid(gameid), True

RESULT_OPTIONS = (
    ('1-0', '1-0'),
    ('1/2-1/2', u'\u00BD-\u00BD'),
    ('0-1', '0-1'),
    ('1X-0F', '1X-0F'),
    ('1/2Z-1/2Z', u'\u00BDZ-\u00BDZ'),
    ('0F-1X', '0F-1X'),
    ('0F-0F', '0F-0F'),
)

TV_STATE_OPTIONS = (
    ('default', 'Default'),
    ('hide', 'Hide'),
)

#-------------------------------------------------------------------------------
class PlayerPairing(_BaseModel):
    white = models.ForeignKey(Player, blank=True, null=True, related_name="pairings_as_white")
    black = models.ForeignKey(Player, blank=True, null=True, related_name="pairings_as_black")

    result = models.CharField(max_length=16, blank=True, choices=RESULT_OPTIONS)
    game_link = models.URLField(max_length=1024, blank=True, validators=[game_link_validator])
    scheduled_time = models.DateTimeField(blank=True, null=True)
    colors_reversed = models.BooleanField(default=False)

    tv_state = models.CharField(max_length=31, default='default', choices=TV_STATE_OPTIONS)

    def __init__(self, *args, **kwargs):
        super(PlayerPairing, self).__init__(*args, **kwargs)
        self.initial_result = self.result
        self.initial_white_id = self.white_id
        self.initial_black_id = self.black_id
        self.initial_game_link = self.game_link

    def white_score(self):
        if self.result == '1-0' or self.result == '1X-0F':
            return 1 if not self.colors_reversed else 0
        elif self.result == '0-1' or self.result == '0F-1X' or self.result == '0F-0F':
            return 0 if not self.colors_reversed else 1
        elif self.result == '1/2-1/2' or self.result == '1/2Z-1/2Z':
            return 0.5
        return None

    def black_score(self):
        if self.result == '0-1' or self.result == '0F-1X':
            return 1 if not self.colors_reversed else 0
        elif self.result == '1-0' or self.result == '1X-0F' or self.result == '0F-0F':
            return 0 if not self.colors_reversed else 1
        elif self.result == '1/2-1/2' or self.result == '1/2Z-1/2Z':
            return 0.5
        return None

    def result_display(self):
        if not self.result:
            return ''
        result = self.result.replace('1/2', u'\u00BD')
        if self.colors_reversed:
            result += '*'
        return result

    def game_played(self):
        return self.result in ('1-0', '1/2-1/2', '0-1')

    def game_id(self):
        return get_gameid_from_gamelink(self.game_link)

    def __unicode__(self):
        return "%s - %s" % (self.white, self.black)

    def save(self, *args, **kwargs):
        result_changed = self.pk is None or self.result != self.initial_result
        white_changed = self.pk is None or self.white_id != self.initial_white_id
        black_changed = self.pk is None or self.black_id != self.initial_black_id
        game_link_changed = self.pk is None or self.game_link != self.initial_game_link

        if game_link_changed:
            self.game_link, _ = normalize_gamelink(self.game_link)

        super(PlayerPairing, self).save(*args, **kwargs)

        if hasattr(self, 'teamplayerpairing') and result_changed:
            self.teamplayerpairing.team_pairing.refresh_points()
            self.teamplayerpairing.team_pairing.save()
        if hasattr(self, 'loneplayerpairing'):
            lpp = LonePlayerPairing.objects.nocache().get(pk=self.loneplayerpairing.pk)
            if result_changed and lpp.round.is_completed:
                lpp.round.season.calculate_scores()
            # If the players for a PlayerPairing in the current round are edited, then we can update the player ranks
            if (white_changed or black_changed) and lpp.round.publish_pairings and not lpp.round.is_completed:
                lpp.refresh_ranks()
                lpp.save()
            # If the players for a PlayerPairing in a previous round are edited, then the player ranks will be out of
            # date but we can't recalculate them
            if white_changed and lpp.round.is_completed:
                lpp.white_rank = None
                lpp.save()
            if black_changed and lpp.round.is_completed:
                lpp.black_rank = None
                lpp.save()

    def delete(self, *args, **kwargs):
        team_pairing = None
        round_ = None
        if hasattr(self, 'teamplayerpairing'):
            team_pairing = self.teamplayerpairing.team_pairing
        if hasattr(self, 'loneplayerpairing'):
            lpp = LonePlayerPairing.objects.nocache().get(pk=self.loneplayerpairing.pk)
            if lpp.round.is_completed:
                round_ = lpp.round
        super(PlayerPairing, self).delete(*args, **kwargs)
        if team_pairing is not None:
            self.teamplayerpairing.team_pairing.refresh_points()
            self.teamplayerpairing.team_pairing.save()
        if round_ is not None:
            round_.season.calculate_scores()

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

#-------------------------------------------------------------------------------
class LonePlayerPairing(PlayerPairing):
    round = models.ForeignKey(Round)
    pairing_order = models.PositiveIntegerField()
    white_rank = models.PositiveIntegerField(blank=True, null=True)
    black_rank = models.PositiveIntegerField(blank=True, null=True)

    def refresh_ranks(self, rank_dict=None):
        if rank_dict == None:
            rank_dict = lone_player_pairing_rank_dict(self.round.season)
        self.white_rank = rank_dict.get(self.white_id, None)
        self.black_rank = rank_dict.get(self.black_id, None)

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

    lichess_username = models.CharField(max_length=255, validators=[username_validator])
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

    def get_loneplayerscore(self):
        try:
            return self.loneplayerscore
        except LonePlayerScore.DoesNotExist:
            return LonePlayerScore.objects.create(season_player=self)

    def __unicode__(self):
        return "%s" % self.player

#-------------------------------------------------------------------------------
class LonePlayerScore(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer)
    points = ScoreField(default=0)
    late_join_points = ScoreField(default=0)
    tiebreak1 = ScoreField(default=0)
    tiebreak2 = ScoreField(default=0)
    tiebreak3 = ScoreField(default=0)
    tiebreak4 = ScoreField(default=0)

    perf_rating = models.PositiveIntegerField(blank=True, null=True)

    def round_scores(self, rounds, player_number_dict, white_pairings_dict, black_pairings_dict, byes_dict, include_current=False):
        white_pairings = white_pairings_dict.get(self.season_player.player, [])
        black_pairings = black_pairings_dict.get(self.season_player.player, [])
        byes = byes_dict.get(self.season_player.player, [])
        cumul_score = 0.0
        for round_ in rounds:
            if not round_.is_completed and (not include_current or not round_.publish_pairings):
                yield (None, None, None, None)
                continue

            result_type = None
            opponent = None
            color = None

            white_pairing = find(white_pairings, round_id=round_.id)
            black_pairing = find(black_pairings, round_id=round_.id)
            bye = find(byes, round_id=round_.id)

            if white_pairing is not None and white_pairing.black is not None:
                opponent = white_pairing.black
                score = white_pairing.white_score()
                if white_pairing.game_played() or score is None:
                    # Normal result
                    color = 'W'
                    result_type = 'W' if score == 1 else 'D' if score == 0.5 else 'L' if score == 0 else 'F'
                else:
                    # Special result
                    result_type = 'X' if score == 1 else 'Z' if score == 0.5 else 'F' if score == 0 else ''
            elif black_pairing is not None and black_pairing.white is not None:
                opponent = black_pairing.white
                score = black_pairing.black_score()
                if black_pairing.game_played() or score is None:
                    # Normal result
                    color = 'B'
                    result_type = 'W' if score == 1 else 'D' if score == 0.5 else 'L' if score == 0 else 'F'
                else:
                    # Special result
                    result_type = 'X' if score == 1 else 'Z' if score == 0.5 else 'F' if score == 0 else ''
            elif bye is not None:
                score = bye.score()
                result_type = 'H'
            else:
                score = 0
                result_type = 'U'

            if score is not None:
                cumul_score += score

            yield (result_type, player_number_dict.get(opponent, 0), color, cumul_score)

    def pairing_points(self):
        return self.points + self.late_join_points

    def pairing_points_display(self):
        return "%.1f" % (self.points + self.late_join_points)

    def final_standings_points_display(self):
        return "%.1f" % self.points

    def late_join_points_display(self):
        return "%.1f" % self.late_join_points

    def tiebreak1_display(self):
        return "%g" % self.tiebreak1

    def tiebreak2_display(self):
        return "%g" % self.tiebreak2

    def tiebreak3_display(self):
        return "%g" % self.tiebreak3

    def tiebreak4_display(self):
        return "%g" % self.tiebreak4

    def pairing_sort_key(self):
        return (self.points + self.late_join_points, self.tiebreak1, self.tiebreak2, self.tiebreak3, self.tiebreak4, self.season_player.player.rating)

    def final_standings_sort_key(self):
        return (self.points, self.tiebreak1, self.tiebreak2, self.tiebreak3, self.tiebreak4, self.season_player.player.rating)

    def __unicode__(self):
        return "%s" % (self.season_player)

def lone_player_pairing_rank_dict(season):
    player_scores = list(enumerate(sorted(LonePlayerScore.objects.filter(season_player__season=season).select_related('season_player').nocache(), key=lambda s: s.pairing_sort_key(), reverse=True), 1))
    return {p.season_player.player_id: n for n, p in player_scores}

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
        if rating is None:
            return self.min_rating is None
        return (self.min_rating is None or rating > self.min_rating) and (self.max_rating is None or rating <= self.max_rating)

    def __unicode__(self):
        return "Board %d (%s, %s]" % (self.board_number, self.min_rating, self.max_rating)

def create_api_token():
    return get_random_string(length=32)

#-------------------------------------------------------------------------------
class SeasonPrize(_BaseModel):
    season = models.ForeignKey(Season)
    rank = models.PositiveIntegerField()
    max_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('season', 'rank', 'max_rating')

    def __unicode__(self):
        if self.max_rating is not None:
            return '%s - U%d #%d' % (self.season, self.max_rating, self.rank)
        else:
            return '%s - #%d' % (self.season, self.rank)

#-------------------------------------------------------------------------------
class SeasonPrizeWinner(_BaseModel):
    season_prize = models.ForeignKey(SeasonPrize)
    player = models.ForeignKey(Player)

    class Meta:
        unique_together = ('season_prize', 'player')

    def __unicode__(self):
        return '%s - %s' % (self.season_prize, self.player)

#-------------------------------------------------------------------------------
class GameNomination(_BaseModel):
    season = models.ForeignKey(Season)
    nominating_player = models.ForeignKey(Player)
    game_link = models.URLField(validators=[game_link_validator])
    pairing = models.ForeignKey(PlayerPairing, blank=True, null=True, on_delete=models.SET_NULL)

    def __unicode__(self):
        return '%s - %s' % (self.season, self.nominating_player)

#-------------------------------------------------------------------------------
class GameSelection(_BaseModel):
    season = models.ForeignKey(Season)
    game_link = models.URLField(validators=[game_link_validator])
    pairing = models.ForeignKey(PlayerPairing, blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ('season', 'game_link')

    def __unicode__(self):
        return '%s - %s' % (self.season, self.game_link)

#-------------------------------------------------------------------------------
class NavItem(_BaseModel):
    league = models.ForeignKey(League)
    parent = models.ForeignKey('self', blank=True, null=True)
    order = models.PositiveIntegerField()
    text = models.CharField(max_length=255)
    path = models.CharField(max_length=1023, blank=True)
    league_relative = models.BooleanField(default=False)
    season_relative = models.BooleanField(default=False)
    append_separator = models.BooleanField(default=False)

    def __unicode__(self):
        return '%s - %s' % (self.league, self.text)

#-------------------------------------------------------------------------------
class ApiKey(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)

    def __unicode__(self):
        return self.name

#-------------------------------------------------------------------------------
class PrivateUrlAuth(_BaseModel):
    authenticated_user = models.CharField(max_length=255, validators=[username_validator])
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)
    expires = models.DateTimeField()

    def is_expired(self):
        return self.expires < timezone.now()

    def __unicode__(self):
        return self.authenticated_user

#-------------------------------------------------------------------------------
class Document(_BaseModel):
    name = models.CharField(max_length=255)
    content = RichTextUploadingField()

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

SEASON_DOCUMENT_TYPES = (
    ('links', 'Links'),
)

#-------------------------------------------------------------------------------
class SeasonDocument(_BaseModel):
    season = models.ForeignKey(Season)
    document = models.ForeignKey(Document)
    tag = models.SlugField(help_text='The document will be accessible at /{league_tag}/season/{season_tag}/document/{document_tag}/')
    type = models.CharField(blank=True, max_length=255, choices=SEASON_DOCUMENT_TYPES)

    class Meta:
        unique_together = ('season', 'tag')

    def __unicode__(self):
        return self.document.name
