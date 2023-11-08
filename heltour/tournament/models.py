from django.db import models, transaction
from django.utils.crypto import get_random_string
from ckeditor_uploader.fields import RichTextUploadingField
from django.core.validators import RegexValidator
from datetime import timedelta, date
from django.utils import timezone
from django import forms as django_forms
from collections import namedtuple, defaultdict
import re
from django.core.exceptions import ValidationError
from heltour.tournament import signals
import logging
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django_comments.models import Comment
from django.db.models import Q, JSONField
from heltour import settings
import reversion

logger = logging.getLogger(__name__)


# Helper function to find an item in a list by its properties
def find(lst, **prop_values):
    for k, v in list(prop_values.items()):
        lst = [obj for obj in lst if getnestedattr(obj, k) == v]
    return next(iter(lst), None)


def getnestedattr(obj, k):
    for k2 in k.split('__'):
        if obj is None:
            return None
        obj = getattr(obj, k2)
    return obj


def abs_url(url):
    site = Site.objects.get_current().domain
    return '%s://%s%s' % (settings.LINK_PROTOCOL, site, url)


def add_system_comment(obj, text, user_name='System'):
    Comment.objects.create(content_object=obj, site=Site.objects.get_current(), user_name=user_name,
                           comment=text, submit_date=timezone.now(), is_public=True)


def format_score(score, game_played=None):
    if score is None:
        return ''
    if str(score) == '0.5':
        score_str = '\u00BD'
    else:
        score_str = str(score).replace('.0', '').replace('.5', '\u00BD')
    if game_played is False:
        if score == 1:
            score_str += 'X'
        elif score == 0.5:
            score_str += 'Z'
        elif score == 0:
            score_str += 'F'
    return score_str


# Represents a positive number in increments of 0.5 (0, 0.5, 1, etc.)
class ScoreField(models.PositiveIntegerField):

    def from_db_value(self, value, expression, connection):
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
        defaults = {'widget': django_forms.TextInput(attrs={'class': 'vIntegerField'}),
                    'initial': self.default}
        defaults.update(kwargs)
        return django_forms.FloatField(**defaults)


# -------------------------------------------------------------------------------
class _BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


THEME_OPTIONS = (
    ('blue', 'Blue'),
    ('green', 'Green'),
    ('red', 'Red'),
    ('yellow', 'Yellow'),
)
RATING_TYPE_OPTIONS = (
    ('classical', 'Classical'),
    ('rapid', 'Rapid'),
    ('chess960', 'Chess 960'),
    ('blitz', 'Blitz'),
)
COMPETITOR_TYPE_OPTIONS = (
    ('team', 'Team'),
    ('individual', 'Individual'),
)
PAIRING_TYPE_OPTIONS = (
    ('swiss-dutch', 'Swiss Tournament: Dutch Algorithm'),
    ('swiss-dutch-baku-accel', 'Swiss Tournament: Dutch Algorithm + Baku Acceleration'),
)


# -------------------------------------------------------------------------------
class League(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    tag = models.SlugField(unique=True, help_text='The league will be accessible at /{league_tag}/')
    description = models.CharField(max_length=1023, blank=True)
    theme = models.CharField(max_length=32, choices=THEME_OPTIONS)
    display_order = models.PositiveIntegerField(default=0)
    time_control = models.CharField(max_length=32, blank=True)
    rating_type = models.CharField(max_length=32, choices=RATING_TYPE_OPTIONS)
    competitor_type = models.CharField(max_length=32, choices=COMPETITOR_TYPE_OPTIONS)
    pairing_type = models.CharField(max_length=32, choices=PAIRING_TYPE_OPTIONS)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    enable_notifications = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('view_dashboard', 'Can view dashboard'),
        )

    def time_control_initial(self):
        parts = self.time_control.split('+')
        if len(parts) != 2:
            return None
        return int(parts[0]) * 60

    def time_control_increment(self):
        parts = self.time_control.split('+')
        if len(parts) != 2:
            return None
        return int(parts[1])

    def time_control_total(self):
        initial = self.time_control_initial()
        increment = self.time_control_increment() or 0
        if not initial:
            return None
        expected_moves = 60
        return initial + increment * expected_moves

    def get_leaguesetting(self):
        try:
            return self.leaguesetting
        except LeagueSetting.DoesNotExist:
            return LeagueSetting.objects.create(league=self)
        
    def is_team_league(self):
        return self.competitor_type == 'team'

    def __str__(self):
        return self.name


class LeagueSetting(_BaseModel):
    league = models.OneToOneField(League, on_delete=models.CASCADE)
    contact_period = models.DurationField(default=timedelta(hours=48))
    notify_for_comments = models.BooleanField(default=True)
    notify_for_latereg_and_withdraw = models.BooleanField(default=True)
    notify_for_forfeits = models.BooleanField(default=True)
    notify_for_registrations = models.BooleanField(default=True)
    notify_for_pre_season_registrations = models.BooleanField(default=False)
    close_registration_at_last_round = models.BooleanField(default=True)
    warning_for_late_response = models.BooleanField(default=True)
    carry_over_red_cards_as_yellow = models.BooleanField(default=True)
    limit_game_nominations_to_participants = models.BooleanField(default=True)
    max_game_nominations_per_user = models.PositiveIntegerField(default=3)
    start_games = models.BooleanField(default=False, help_text='Try to start games automatically, if the scheduled time was confirmed by both players')

    def __str__(self):
        return '%s Settings' % self.league


PLAYOFF_OPTIONS = (
    (0, 'None'),
    (1, 'Finals'),
    (2, 'Semi-Finals'),
    (3, 'Quarter-Finals'),
)


# -------------------------------------------------------------------------------
class Season(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    tag = models.SlugField(
        help_text='The season will be accessible at /{league_tag}/season/{season_tag}/')
    start_date = models.DateTimeField(blank=True, null=True)
    rounds = models.PositiveIntegerField()
    round_duration = models.DurationField(default=timedelta(days=7))
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
        ordering = ['is_completed', 'league__name', '-name']

    def __init__(self, *args, **kwargs):
        super(Season, self).__init__(*args, **kwargs)
        self.initial_rounds = self.rounds
        self.initial_round_duration = self.round_duration
        self.initial_start_date = self.start_date
        self.initial_is_completed = self.is_completed

    def last_season_alternates(self):
        last_season = Season.objects.filter(league=self.league, start_date__lt=self.start_date) \
            .order_by('-start_date').first()
        last_season_alts = Alternate.objects.filter(season_player__season=last_season) \
            .select_related('season_player__player').nocache()
        return {alt.season_player.player for alt in last_season_alts}

    def export_players(self):
        last_season_alts = self.last_season_alternates()

        def extract(sp):
            info = {
                'name': sp.player.lichess_username,
                'rating': sp.player.rating_for(self.league),
                'has_20_games': not sp.player.provisional_for(self.league),
                'in_slack': bool(sp.player.slack_user_id),
                'account_status': sp.player.account_status,
                'date_created': None,
                'friends': None,
                'avoid': None,
                'prefers_alt': False,
                'alt_fine': False,
                'previous_season_alternate': sp.player in last_season_alts
            }
            reg = sp.registration
            if reg is not None:
                info.update({
                    'date_created': reg.date_created.isoformat(),
                    'peak_classical_rating': reg.peak_classical_rating,
                    'friends': reg.friends,
                    'avoid': reg.avoid,
                    'prefers_alt': reg.alternate_preference == 'alternate',
                    'alt_fine': reg.alternate_preference == 'either',
                })
            return info

        season_players = (self.seasonplayer_set
                          .filter(is_active=True)
                          .select_related('player', 'registration')
                          .nocache())
        return [extract(sp) for sp in season_players]

    def clean(self):
        if self.league_id and self.league.competitor_type == 'team' and self.boards is None:
            raise ValidationError('Boards must be specified for a team season')

    def save(self, *args, **kwargs):
        # TODO: Add validation to prevent changes after a certain point
        new_obj = self.pk is None
        rounds_changed = self.pk is None or self.rounds != self.initial_rounds
        round_duration_changed = self.pk is None or self.round_duration != self.initial_round_duration
        start_date_changed = self.pk is None or self.start_date != self.initial_start_date
        is_completed_changed = self.pk is None or self.is_completed != self.initial_is_completed

        if self.is_completed and self.registration_open:
            self.registration_open = False
        super(Season, self).save(*args, **kwargs)

        if rounds_changed or round_duration_changed or start_date_changed:
            date = self.start_date
            for round_num in range(1, self.rounds + 1):
                next_date = date + self.round_duration if date is not None else None
                Round.objects.update_or_create(season=self, number=round_num,
                                               defaults={'start_date': date, 'end_date': next_date})
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
            if self.league.is_team_league():
                team_scores = sorted(
                    TeamScore.objects.filter(team__season=self).select_related('team').nocache(),
                    reverse=True)
                for prize in self.seasonprize_set.filter(max_rating=None):
                    if prize.rank <= len(team_scores):
                        # Award a prize to each team member
                        for member in team_scores[prize.rank - 1].team.teammember_set.all():
                            SeasonPrizeWinner.objects.create(season_prize=prize,
                                                             player=member.player)
            else:
                player_scores = sorted(
                    LonePlayerScore.objects.filter(season_player__season=self).select_related(
                        'season_player__player').nocache(),
                    key=lambda s: s.final_standings_sort_key(), reverse=True)
                for prize in self.seasonprize_set.all():
                    eligible_players = [s.season_player.player for s in player_scores if
                                        prize.max_rating is None or (
                                            s.season_player.seed_rating is not None and s.season_player.seed_rating < prize.max_rating)]
                    if prize.rank <= len(eligible_players):
                        SeasonPrizeWinner.objects.create(season_prize=prize,
                                                         player=eligible_players[prize.rank - 1])

    def calculate_scores(self):
        if self.league.is_team_league():
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

                def increment_score(round_opponent, round_points, round_opponent_points,
                                    round_wins):
                    playoff_score, match_count, match_points, game_points, games_won, _, _, _, _ = \
                        score_dict[(team.pk, last_round.number)] if last_round is not None else (
                            0, 0, 0, 0, 0, 0, 0, None, 0)
                    round_match_points = 0
                    if round_opponent is None:
                        if not is_playoffs:
                            # Bye
                            match_points += 1
                            game_points += self.boards / 2
                    else:
                        if is_playoffs:
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
                    score_dict[(team.pk, round_.number)] = _TeamScoreState(playoff_score,
                                                                           match_count,
                                                                           match_points,
                                                                           game_points, games_won,
                                                                           round_match_points,
                                                                           round_points,
                                                                           round_opponent,
                                                                           round_opponent_points)

                if white_pairing is not None:
                    increment_score(white_pairing.black_team_id, white_pairing.white_points,
                                    white_pairing.black_points, white_pairing.white_wins)
                elif black_pairing is not None:
                    increment_score(black_pairing.white_team_id, black_pairing.black_points,
                                    black_pairing.white_points, black_pairing.black_wins)
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
                            score.sb_score += score_dict[
                                (round_state.round_opponent, last_round.number)].match_points
                        elif round_state.round_match_points == 1:
                            score.sb_score += score_dict[(
                                round_state.round_opponent, last_round.number)].match_points / 2.0
                        if opponent in tied_team_set:
                            score.head_to_head += round_state.round_match_points
            score.save()

    def _calculate_lone_scores(self):
        season_players = SeasonPlayer.objects.filter(season=self).select_related(
            'loneplayerscore').nocache()
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
                    total, mm_total, cumul, perf, _, _ = score_dict[
                        (sp.player_id, last_round.number)] if last_round is not None else (
                        0, 0, 0, PerfRatingCalc(), None, False)
                    total += round_score
                    cumul += total
                    if round_played:
                        mm_total += round_score
                        opp_rating = seed_rating_dict.get(round_opponent, None)
                        if opp_rating is not None:
                            perf.add_game(round_score, opp_rating)
                    else:
                        # Special cases for unplayed games
                        mm_total += 0.5
                        cumul -= round_score
                    score_dict[(sp.player_id, round_.number)] = _LoneScoreState(total, mm_total,
                                                                                cumul, perf,
                                                                                round_opponent,
                                                                                round_played)

                if white_pairing is not None:
                    increment_score(white_pairing.black_id, white_pairing.white_score() or 0,
                                    white_pairing.game_played())
                elif black_pairing is not None:
                    increment_score(black_pairing.white_id, black_pairing.black_score() or 0,
                                    black_pairing.game_played())
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
                        opponent_scores.append(
                            score_dict[(round_state.round_opponent, last_round.number)].mm_total)
                        opponent_cumuls.append(
                            score_dict[(round_state.round_opponent, last_round.number)].cumul)
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
                score.perf_rating = score_state.perf.calculate()

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

    def alternates_manager_enabled(self):
        if not hasattr(self.league, 'alternatesmanagersetting'):
            return False
        return self.league.alternatesmanagersetting.is_active

    def alternates_manager_setting(self):
        if not hasattr(self.league, 'alternatesmanagersetting'):
            return None
        return self.league.alternatesmanagersetting

    def section_list(self):
        if not hasattr(self, 'section'):
            return [self]
        return Season.objects.filter(
            section__section_group_id=self.section.section_group_id).order_by('section__order')

    def section_group_name(self):
        if not hasattr(self, 'section'):
            return self.name
        return self.section.section_group.name

    @classmethod
    def get_registration_season(cls, league, season=None):
        if season is not None and season.registration_open:
            return season
        else:
            return cls.objects.filter(league=league, registration_open=True).order_by(
                '-start_date').first()

    @property
    def pairings(self):
        return (PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round__season=self)
                | PlayerPairing.objects.filter(loneplayerpairing__round__season=self)).nocache()

    def __str__(self):
        return self.name


_TeamScoreState = namedtuple('_TeamScoreState',
                             'playoff_score, match_count, match_points, game_points, games_won, round_match_points, round_points, round_opponent, round_opponent_points')
_LoneScoreState = namedtuple('_LoneScoreState',
                             'total, mm_total, cumul, perf, round_opponent, round_played')

# From https://www.fide.com/component/handbook/?id=174&view=article
# Used for performance rating calculations
fide_dp_lookup = [-800, -677, -589, -538, -501, -470, -444, -422, -401, -383, -366, -351, -336,
                  -322, -309, -296, -284, -273, -262, -251,
                  - 240, -230, -220, -211, -202, -193, -184, -175, -166, -158, -149, -141, -133,
                  -125, -117, -110, -102, -95, -87, -80, -72,
                  - 65, -57, -50, -43, -36, -29, -21, -14, -7, 0, 7, 14, 21, 29, 36, 43, 50, 57, 65,
                  72, 80, 87, 95, 102, 110, 117, 125, 133,
                  141, 149, 158, 166, 175, 184, 193, 202, 211, 220, 230, 240, 251, 262, 273, 284,
                  296, 309, 322, 336, 351, 366, 383, 401,
                  422, 444, 470, 501, 538, 589, 677, 800]


def get_fide_dp(score, total):
    # Turn the score into a number from 0-100 (0 = 0%, 100 = 100%)
    lookup_index = max(min(int(round(100.0 * score / total)), 100), 0)
    # Use that number to get a rating difference from the FIDE lookup table
    return fide_dp_lookup[lookup_index]


class PerfRatingCalc():
    def __init__(self):
        self._score = 0
        self._game_count = 0
        self._opponent_ratings = []

    def merge(self, other):
        self._score += other._score
        self._game_count += other._game_count
        self._opponent_ratings += other._opponent_ratings

    def add_game(self, score, opponent_rating):
        self._score += score
        self._game_count += 1
        self._opponent_ratings.append(opponent_rating)

    def calculate(self):
        if self._game_count < 5:
            return None
        average_opp_rating = int(round(sum(self._opponent_ratings) / float(self._game_count)))
        dp = get_fide_dp(self._score, self._game_count)
        return average_opp_rating + dp

    def debug(self):
        return '%.1f / %d [%s]' % (
            self._score, self._game_count, ', '.join((str(r) for r in self._opponent_ratings)))


# -------------------------------------------------------------------------------
class Round(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    number = models.PositiveIntegerField(verbose_name='round number')
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)

    publish_pairings = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    class Meta:
        permissions = (
            ('generate_pairings', 'Can generate and review pairings'),
        )
        ordering = ['is_completed', '-start_date']

    def __init__(self, *args, **kwargs):
        super(Round, self).__init__(*args, **kwargs)
        self.initial_is_completed = self.is_completed
        self.initial_publish_pairings = self.publish_pairings

    def save(self, *args, **kwargs):
        is_completed_changed = self.pk is None and self.is_completed or self.is_completed != self.initial_is_completed
        publish_pairings_changed = self.pk is None and self.publish_pairings or self.publish_pairings != self.initial_publish_pairings
        super(Round, self).save(*args, **kwargs)
        if is_completed_changed:
            self.season.calculate_scores()
        if publish_pairings_changed and self.publish_pairings and not self.is_completed:
            signals.do_pairings_published.send(Round, round_id=self.pk)

    @property
    def pairings(self):
        return (PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round=self)
                | PlayerPairing.objects.filter(loneplayerpairing__round=self)).nocache()

    def pairing_for(self, player):
        pairings = self.pairings
        return (pairings.filter(white=player) | pairings.filter(black=player)).first()

    def __str__(self):
        return "%s - Round %d" % (self.season, self.number)


# -------------------------------------------------------------------------------
class SectionGroup(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


# -------------------------------------------------------------------------------
class Section(_BaseModel):
    season = models.OneToOneField(Season, on_delete=models.CASCADE)
    section_group = models.ForeignKey(SectionGroup, on_delete=models.CASCADE)
    name = models.CharField(max_length=255, verbose_name='section name')
    order = models.PositiveIntegerField()
    min_rating = models.PositiveIntegerField(blank=True, null=True)
    max_rating = models.PositiveIntegerField(blank=True, null=True)

    def clean(self):
        if self.season and self.section_group and self.season.league_id != self.section_group.league_id:
            raise ValidationError('Season and section group leagues must match')

    def is_eligible(self, player):
        rating = player.rating_for(self.season.league)
        if self.min_rating is not None and (rating is None or rating < self.min_rating):
            return False
        if self.max_rating is not None and (rating is None or rating >= self.max_rating):
            return False
        return True

    def __str__(self):
        return '%s - %s' % (self.name, self.section_group.name)


# -------------------------------------------------------------------------------
class OauthToken(_BaseModel):
    access_token = models.CharField(max_length=4096)
    token_type = models.CharField(max_length=255)
    expires = models.DateTimeField()
    refresh_token = models.CharField(max_length=4096, blank=True)
    scope = models.TextField(blank=True)

    account_username = models.CharField(max_length=255)
    account_email = models.CharField(max_length=255, blank=True)

    def is_expired(self):
        return self.expires < timezone.now()

    def __str__(self):
        return self.account_username


username_validator = RegexValidator(r'^[\w-]+$')

ACCOUNT_STATUS_OPTIONS = (
    ('normal', 'Normal'),
    ('tos_violation', 'ToS Violation'),
    ('closed', 'Closed'),
)


# -------------------------------------------------------------------------------
class Player(_BaseModel):
    # TODO: we should find out the real restrictions on a lichess username and
    #       duplicate them here.
    # Note: a case-insensitive unique index for lichess_username is added via migration to the DB
    lichess_username = models.CharField(max_length=255, validators=[username_validator])
    rating = models.PositiveIntegerField(blank=True, null=True)
    games_played = models.PositiveIntegerField(blank=True, null=True)
    email = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    slack_user_id = models.CharField(max_length=255, blank=True)
    timezone_offset = models.DurationField(blank=True, null=True)
    account_status = models.CharField(default='normal', max_length=31,
                                      choices=ACCOUNT_STATUS_OPTIONS)
    oauth_token = models.ForeignKey(OauthToken, null=True, on_delete=models.CASCADE)

    profile = JSONField(blank=True, null=True)

    date_first_agreed_to_tos = models.DateTimeField(blank=True, null=True)
    date_last_agreed_to_tos = models.DateTimeField(blank=True, null=True)

    def player_rating_display(self, league=None):
        return self.rating_for(league)

    @property
    def pairings(self):
        return (self.pairings_as_white.all() | self.pairings_as_black.all()).nocache()

    class Meta:
        ordering = ['lichess_username']
        permissions = (
            ('change_player_details', 'Can change player details'),
            ('invite_to_slack', 'Can invite to slack'),
            ('link_slack', 'Can manually link slack accounts'),
            ('dox', 'Can see player emails'),
        )

    def __init__(self, *args, **kwargs):
        super(Player, self).__init__(*args, **kwargs)
        self.initial_account_status = self.account_status

    def save(self, *args, **kwargs):
        account_status_changed = self.pk and self.account_status != self.initial_account_status
        super(Player, self).save(*args, **kwargs)
        if account_status_changed:
            signals.player_account_status_changed.send(Player, instance=self,
                                                       old_value=self.initial_account_status,
                                                       new_value=self.account_status)

    def update_profile(self, user_meta):
        classical = user_meta.get('perfs', {}).get('classical')
        if classical is not None:
            self.rating = classical['rating']
            self.games_played = classical['games']
        is_closed = user_meta.get('disabled', False)
        is_tosViolation = user_meta.get('tosViolation', False)
        self.account_status = 'closed' if is_closed else 'tos_violation' if is_tosViolation else 'normal'
        
        # profile is used to get rating data which should not be updated anymore once an account is closed.
        if not is_closed:
            self.profile = user_meta
        self.save()

    @classmethod
    def get_or_create(cls, lichess_username):
        player, _ = Player.objects.get_or_create(lichess_username__iexact=lichess_username,
                                                 defaults={'lichess_username': lichess_username})
        return player

    @classmethod
    def link_slack_account(cls, lichess_username, slack_user_id):
        player = Player.get_or_create(lichess_username)
        if player.slack_user_id == slack_user_id:
            # No change needed
            return False
        with reversion.create_revision():
            reversion.set_comment('Link slack account')
            player.slack_user_id = slack_user_id
            player.save()
            signals.slack_account_linked.send(sender=cls, lichess_username=lichess_username,
                                              slack_user_id=slack_user_id)
            return True

    def is_available_for(self, round_):
        return not PlayerAvailability.objects.filter(round=round_, player=self,
                                                     is_available=False).exists()

    def rating_for(self, league):
        if league:
            if self.profile is None:
                # some admin screens cannot handle a None rating, so we return 0 instead.
                # self.profile is only None if the player profile has never been downloaded
                # from lichess or the account had already been closed at that first download.
                return 0
            return self.profile.get('perfs', {}).get(league.rating_type, {}).get('rating')
        return self.rating

    def games_played_for(self, league):
        if league:
            if self.profile is None:
                return None
            return self.profile.get('perfs', {}).get(league.rating_type, {}).get('games')

        return self.games_played  # classical

    def provisional_for(self, league):
        if self.profile is None:
            return True
        perf = self.profile.get('perfs', {}).get(league.rating_type)
        if perf is None:
            return True
        return perf.get('prov', False)

    @property
    def timezone_str(self):
        if self.timezone_offset == None:
            return '?'
        seconds = self.timezone_offset.total_seconds()
        sign = '-' if seconds < 0 else '+'
        hours = abs(seconds) / 3600
        minutes = (abs(seconds) % 3600) / 60
        return 'UTC%s%02d:%02d' % (sign, hours, minutes)

    def get_season_prizes(self, league):
        return SeasonPrize.objects \
            .filter(season__league=league, seasonprizewinner__player=self) \
            .order_by('rank', '-season')

    def agreed_to_tos(self):
        now = timezone.now()
        # Update
        me = Player.objects.filter(pk=self.pk)
        me.update(
            date_last_agreed_to_tos=now
        )
        me.filter(date_first_agreed_to_tos__isnull=True).update(
            date_first_agreed_to_tos=now
        )


    def __str__(self):
        if self.rating is None:
            return self.lichess_username
        else:
            return "%s (%d)" % (self.lichess_username, self.rating)

    def __lt__(self, other):
        return self.lichess_username.lower() < other.lichess_username.lower()


# -------------------------------------------------------------------------------
class PlayerSetting(_BaseModel):
    player = models.OneToOneField(Player, on_delete=models.CASCADE)

    dark_mode = models.BooleanField(default=False)


# -------------------------------------------------------------------------------
class LeagueModerator(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    is_active = models.BooleanField(default=True)
    send_contact_emails = models.BooleanField(default=True)

    class Meta:
        unique_together = ('league', 'player')

    def __str__(self):
        return "%s - %s" % (self.league, self.player.lichess_username)


ROUND_CHANGE_OPTIONS = (
    ('register', 'Register'),
    ('withdraw', 'Withdraw'),
    ('half-point-bye', 'Half-Point Bye'),
)


# -------------------------------------------------------------------------------
class PlayerLateRegistration(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    retroactive_byes = models.PositiveIntegerField(default=0)
    late_join_points = ScoreField(default=0)

    class Meta:
        unique_together = ('round', 'player')

    def perform_registration(self):
        with transaction.atomic():
            # Set the SeasonPlayer as active
            sp, _ = SeasonPlayer.objects.get_or_create(season=self.round.season, player=self.player)
            sp.is_active = True
            if sp.seed_rating is None:
                sp.seed_rating = self.player.rating_for(self.round.season.league)
            sp.save()

            # Create any retroactive byes (but don't overwrite existing byes/pairings)
            rounds = self.round.season.round_set.all()
            for i in range(self.retroactive_byes):
                round_number = self.round.number - i - 1
                if round_number < 1:
                    # Too many byes specified, we can just skip them
                    break
                round_ = find(rounds, number=round_number)
                pairings = round_.loneplayerpairing_set.filter(
                    white=self.player) | round_.loneplayerpairing_set.filter(black=self.player)
                byes = round_.playerbye_set.filter(player=self.player)
                if pairings.count() == 0 and byes.count() == 0:
                    PlayerBye.objects.create(round=round_, player=self.player,
                                             type='half-point-bye')

            # Set the late-join points
            score = sp.get_loneplayerscore()
            score.late_join_points = max(score.late_join_points, self.late_join_points)
            score.save()

    def save(self, *args, **kwargs):
        super(PlayerLateRegistration, self).save(*args, **kwargs)
        if self.round.publish_pairings and not self.round.is_completed:
            self.perform_registration()

    def clean(self):
        if self.round_id and self.round.season.league.is_team_league():
            raise ValidationError('Player late registrations can only be created for lone leagues')

    def __str__(self):
        return "%s - %s" % (self.round, self.player)


# -------------------------------------------------------------------------------
class PlayerWithdrawal(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('round', 'player')

    def perform_withdrawal(self):
        with transaction.atomic():
            # Set the SeasonPlayer as inactive
            sp, _ = SeasonPlayer.objects.get_or_create(season=self.round.season, player=self.player)
            sp.is_active = False
            sp.save()

            # Delete pairings and give opponents byes
            for pairing in self.round.loneplayerpairing_set.filter(white=self.player):
                PlayerBye.objects.create(round=self.round, player=pairing.black,
                                         type='full-point-pairing-bye')
                pairing.delete()
            for pairing in self.round.loneplayerpairing_set.filter(black=self.player):
                PlayerBye.objects.create(round=self.round, player=pairing.white,
                                         type='full-point-pairing-bye')
                pairing.delete()

    def perform_team_season_withdrawal(self):
        SeasonPlayer.withdraw_from_team_season(round=self.round, player=self.player)

    def save(self, *args, **kwargs):
        if self.round.season.league.is_team_league():
            self.perform_team_season_withdrawal()
        super(PlayerWithdrawal, self).save(*args, **kwargs)
        if self.round.publish_pairings and not self.round.is_completed:
            self.perform_withdrawal()

    def clean(self):
        if self.round_id and self.round.season.league.is_team_league():
            raise ValidationError('Player withdrawals can only be created for lone leagues')

    def __str__(self):
        return "%s - %s" % (self.round, self.player)


BYE_TYPE_OPTIONS = (
    ('full-point-pairing-bye', 'Full-Point Bye (Pairing)'),
    ('full-point-bye', 'Full-Point Bye'),
    ('half-point-bye', 'Half-Point Bye'),
    ('zero-point-bye', 'Zero-Point Bye'),
)


# -------------------------------------------------------------------------------
class PlayerBye(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=31, choices=BYE_TYPE_OPTIONS)
    player_rank = models.PositiveIntegerField(blank=True, null=True)
    player_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = ('round', 'player')

    def __init__(self, *args, **kwargs):
        super(PlayerBye, self).__init__(*args, **kwargs)
        self.initial_round_id = self.round_id
        self.initial_player_id = self.player_id
        self.initial_type = self.type

    def player_rating_display(self, league=None):
        if self.player_rating is not None:
            return self.player_rating
        else:
            if league is None:
                league = self.round.season.league
            return self.player.rating_for(league)

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

    def __str__(self):
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
        if player_changed:
            self.player_rating = None
        super(PlayerBye, self).save(*args, **kwargs)
        if (round_changed or player_changed or type_changed) and self.round.is_completed:
            self.round.season.calculate_scores()

    def delete(self, *args, **kwargs):
        round_ = self.round
        super(PlayerBye, self).delete(*args, **kwargs)
        if round_.is_completed:
            round_.season.calculate_scores()

    def clean(self):
        if self.round_id and self.round.season.league.is_team_league():
            raise ValidationError('Player byes can only be created for lone leagues')


# -------------------------------------------------------------------------------
class Team(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    number = models.PositiveIntegerField(verbose_name='team number')
    name = models.CharField(max_length=255, verbose_name='team name')
    slack_channel = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    seed_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = (('season', 'number'), ('season', 'name'))
        ordering = ('season__is_completed', '-season__start_date')

    def get_teamscore(self):
        try:
            return self.teamscore
        except TeamScore.DoesNotExist:
            return TeamScore.objects.create(team=self)

    def boards(self):
        team_members = self.teammember_set.all()
        return [(n, find(team_members, board_number=n)) for n in
                Season.objects.get(pk=self.season_id).board_number_list()]

    def average_rating(self, expected_rating=False):
        n = 0
        total = 0.0
        for _, board in self.boards():
            if board is not None:
                if expected_rating:
                    rating = board.expected_rating()
                else:
                    rating = board.player.rating_for(self.season.league)
                if rating is not None:
                    n += 1
                    total += rating
        return total / n if n > 0 else None

    def get_mean(self, expected_rating=False):
        return self.average_rating(expected_rating)

    def captain(self):
        return self.teammember_set.filter(is_captain=True).first()

    def get_teampairing(self, round_):
        return (round_.teampairing_set.filter(white_team=self) | round_.teampairing_set.filter(
            black_team=self)).first()

    def get_opponent(self, round_):
        team_pairing = self.get_teampairing(round_)
        if team_pairing is None:
            return None
        if team_pairing.white_team != self:
            return team_pairing.white_team
        if team_pairing.black_team != self:
            return team_pairing.black_team
        return None

    @property
    def pairings(self):
        return self.pairings_as_white.all() | self.pairings_as_black.all()

    def __str__(self):
        return "%s - %s" % (self.season, self.name)


BOARD_NUMBER_OPTIONS = (
    (1, '1'),
    (2, '2'),
    (3, '3'),
    (4, '4'),
    (5, '5'),
    (6, '6'),
    (7, '7'),
    (8, '8'),
    (9, '9'),
    (10, '10'),
    (11, '11'),
    (12, '12'),
)


# -------------------------------------------------------------------------------
class TeamMember(_BaseModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    is_captain = models.BooleanField(default=False)
    is_vice_captain = models.BooleanField(default=False)

    player_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('team', 'board_number')

    def __init__(self, *args, **kwargs):
        super(TeamMember, self).__init__(*args, **kwargs)
        self.initial_player_id = self.player_id

    def player_rating_display(self, league=None):
        if self.player_rating is not None:
            return self.player_rating
        else:
            if league is None:
                league = self.team.season.league
            return self.player.rating_for(league)

    def expected_rating(self):
        try:
            sp = SeasonPlayer.objects.get(season=self.team.season, player=self.player)
            return sp.expected_rating(self.team.season.league)
        except SeasonPlayer.DoesNotExist:
            return None

    def save(self, *args, **kwargs):
        player_changed = self.pk is None or self.player_id != self.initial_player_id
        if player_changed:
            self.player_rating = None
        super(TeamMember, self).save(*args, **kwargs)

        # A little trick here to add a corresponding entry to the team model's history when using reversion
        self.team.save()

    def delete(self, *args, **kwargs):
        super(TeamMember, self).delete(*args, **kwargs)
        self.team.save()

    def clean(self):
        if self.team_id and self.player_id and not SeasonPlayer.objects.filter(
            season=self.team.season, player=self.player).exists():
            raise ValidationError('Team member must be a player in the season')

    def __str__(self):
        return "%s%s" % (
            self.player, ' (C)' if self.is_captain else ' (V)' if self.is_vice_captain else '')


# -------------------------------------------------------------------------------
class TeamScore(_BaseModel):
    team = models.OneToOneField(Team, on_delete=models.CASCADE)
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
        return (
            self.playoff_score, self.match_points, self.game_points, self.head_to_head,
            self.games_won,
            self.sb_score, self.team.seed_rating)

    def round_scores(self):
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for round_ in Round.objects.filter(season_id=self.team.season_id).order_by('number'):
            if round_ is None or not round_.is_completed:
                yield None, None, None
                continue
            points = None
            opp_points = None
            white_pairing = find(white_pairings, round_id=round_.id)
            black_pairing = find(black_pairings, round_id=round_.id)
            if white_pairing is not None:
                points = white_pairing.white_points
                opp_points = white_pairing.black_points
            if black_pairing is not None:
                points = black_pairing.black_points
                opp_points = black_pairing.white_points
            yield points, opp_points, round_.number

    def cross_scores(self, sorted_teams=None):
        if sorted_teams is None:
            sorted_teams = Team.objects.filter(season_id=self.team.season_id).order_by('number')
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        for other_team in sorted_teams:
            white_pairing = find(white_pairings, black_team_id=other_team.pk)
            black_pairing = find(black_pairings, white_team_id=other_team.pk)
            points = None
            opp_points = None
            round_num = None
            if white_pairing is not None and white_pairing.round.is_completed:
                points = white_pairing.white_points
                opp_points = white_pairing.black_points
                round_num = white_pairing.round.number
            if black_pairing is not None and black_pairing.round.is_completed:
                points = black_pairing.black_points
                opp_points = black_pairing.white_points
                round_num = black_pairing.round.number
            yield other_team.number, points, opp_points, round_num

    def __str__(self):
        return "%s" % (self.team)

    def __lt__(self, other):
        return (self.playoff_score, self.match_points, self.game_points, self.head_to_head,
                self.games_won, self.sb_score) < \
               (other.playoff_score, other.match_points, other.game_points, other.head_to_head,
                other.games_won, other.sb_score)


# -------------------------------------------------------------------------------
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(Team, related_name="pairings_as_white", on_delete=models.CASCADE)
    black_team = models.ForeignKey(Team, related_name="pairings_as_black", on_delete=models.CASCADE)
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
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

    def clean(self):
        if self.white_team_id and self.black_team_id and self.white_team.season != self.round.season or self.black_team.season != self.round.season:
            raise ValidationError('Round and team seasons must match')

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

    def __str__(self):
        return "%s - %s - %s" % (self.round, self.white_team.name, self.black_team.name)


# Game link structure:
# 1. (Optional) http/s prefix
# 2. (Optional) Subdomain, e.g. "en."
# 3. "lichess.org/" – fetched from settings
# 4. The gameid (8 chars)
# 5. (Optional) Extended id for games in progress (4 chars)
# 6. (Optional) Any junk at the end, e.g. "/black", etc.
game_link_regex = re.compile(
    fr'^(https?://)?([a-z]+\.)?{settings.LICHESS_NAME}\.{settings.LICHESS_TOPLEVEL}/([A-Za-z0-9]{{8}})([A-Za-z0-9]{{4}})?([/#\?].*)?$')
game_link_validator = RegexValidator(game_link_regex)


def get_gameid_from_gamelink(gamelink):
    if gamelink is None or gamelink == '':
        return None
    match = game_link_regex.match(gamelink)
    if match is None:
        return None
    return match.group(3)


def get_gamelink_from_gameid(gameid):
    return f'{settings.LICHESS_DOMAIN}{gameid}'


def normalize_gamelink(gamelink):
    if gamelink == '':
        return gamelink, True
    gameid = get_gameid_from_gamelink(gamelink)
    if gameid is None:
        return gamelink, False
    return get_gamelink_from_gameid(gameid), True


RESULT_OPTIONS = (
    ('1-0', '1-0'),
    ('1/2-1/2', '\u00BD-\u00BD'),
    ('0-1', '0-1'),
    ('1X-0F', '1X-0F'),
    ('1/2Z-1/2Z', '\u00BDZ-\u00BDZ'),
    ('0F-1X', '0F-1X'),
    ('0F-0F', '0F-0F'),
)

TV_STATE_OPTIONS = (
    ('default', 'Default'),
    ('hide', 'Hide'),
)


# -------------------------------------------------------------------------------
class PlayerPairing(_BaseModel):
    white = models.ForeignKey(Player,
                              blank=True, null=True, related_name="pairings_as_white",
                              on_delete=models.CASCADE)
    black = models.ForeignKey(Player,
                              blank=True, null=True, related_name="pairings_as_black",
                              on_delete=models.CASCADE)
    white_rating = models.PositiveIntegerField(blank=True, null=True)
    black_rating = models.PositiveIntegerField(blank=True, null=True)

    result = models.CharField(max_length=16, blank=True, choices=RESULT_OPTIONS)
    game_link = models.URLField(max_length=1024, blank=True, validators=[game_link_validator])
    scheduled_time = models.DateTimeField(blank=True, null=True)
    #*_confirmed: whether the player confirmed the scheduled time, so we may start games automatically.
    white_confirmed = models.BooleanField(default=False)
    black_confirmed = models.BooleanField(default=False)

    colors_reversed = models.BooleanField(default=False)

    
    #We do not want to mark players as unresponsive if their opponents got assigned after round start
    date_player_changed = models.DateTimeField(blank=True, null=True)

    tv_state = models.CharField(max_length=31, default='default', choices=TV_STATE_OPTIONS)

    def __init__(self, *args, **kwargs):
        super(PlayerPairing, self).__init__(*args, **kwargs)
        self.initial_result = '' if self.pk is None else self.result
        self.initial_white_id = None if self.pk is None else self.white_id
        self.initial_black_id = None if self.pk is None else self.black_id
        self.initial_game_link = '' if self.pk is None else self.game_link
        self.initial_scheduled_time = None if self.pk is None else self.scheduled_time

    def white_rating_display(self, league=None):
        if self.white_rating is not None:
            return self.white_rating
        elif self.white is not None:
            if league is None:
                round_ = self.get_round()
                if round_ is not None:
                    league = round_.season.league
            return self.white.rating_for(league)
        else:
            return None

    def black_rating_display(self, league=None):
        if self.black_rating is not None:
            return self.black_rating
        elif self.black is not None:
            if league is None:
                round_ = self.get_round()
                if round_ is not None:
                    league = round_.season.league
            return self.black.rating_for(league)
        else:
            return None

    def white_display(self):
        if not self.white:
            return '?'
        if self.white_rating:
            return '%s (%d)' % (self.white.lichess_username, self.white_rating)
        else:
            return self.white

    def black_display(self):
        if not self.black:
            return '?'
        if self.black_rating:
            return '%s (%d)' % (self.black.lichess_username, self.black_rating)
        else:
            return self.black

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
        result = self.result.replace('1/2', '\u00BD')
        if self.colors_reversed:
            result += '*'
        return result

    def game_played(self):
        return self.result in ('1-0', '1/2-1/2', '0-1')

    def game_id(self):
        return get_gameid_from_gamelink(self.game_link)

    def get_round(self):
        if hasattr(self, 'teamplayerpairing'):
            return self.teamplayerpairing.team_pairing.round
        if hasattr(self, 'loneplayerpairing'):
            return self.loneplayerpairing.round
        return None

    def get_player_presence(self, player):
        presence = self.playerpresence_set.filter(player=player).first()
        if not presence:
            presence = PlayerPresence.objects.create(pairing=self, player=player,
                                                     round=self.get_round())
        return presence
    
    def pairing_changed_after_round_start(self):
        if self.date_player_changed is None:
            return False
        else:
            return self.date_player_changed > self.get_round().start_date

    def __str__(self):
        return "%s - %s" % (self.white_display(), self.black_display())
    
    def update_available_upon_schedule(self, player_id):
        #set players available if game gets scheduled and they are unavailable,
        #do not set a player with a red card available, though.
        if not SeasonPlayer.objects.filter(player__id=player_id, season=self.get_round().season, games_missed__gte=2).exists():
            PlayerAvailability.objects.filter(
                player__id=player_id, round=self.get_round()).update(is_available=True)

    def save(self, *args, **kwargs):
        result_changed = self.result != self.initial_result
        white_changed = self.white_id != self.initial_white_id
        black_changed = self.black_id != self.initial_black_id
        game_link_changed = self.game_link != self.initial_game_link
        scheduled_time_changed = self.scheduled_time != self.initial_scheduled_time

        if game_link_changed:
            self.game_link, _ = normalize_gamelink(self.game_link)
            self.tv_state = 'default'
        if white_changed or black_changed or game_link_changed:
            self.white_rating = None
            self.black_rating = None
        
        #we only want to set date_player_changed if a player was changed after the initial creation of the pairing
        if (white_changed and self.initial_white_id is not None) or (black_changed and self.initial_black_id is not None):
            self.date_player_changed = timezone.now()

        super(PlayerPairing, self).save(*args, **kwargs)

        if hasattr(self, 'teamplayerpairing') and result_changed:
            self.teamplayerpairing.team_pairing.refresh_points()
            self.teamplayerpairing.team_pairing.save()
        if hasattr(self, 'loneplayerpairing'):
            lpp = LonePlayerPairing.objects.nocache().get(pk=self.loneplayerpairing.pk)
            if result_changed and lpp.round.is_completed:
                lpp.round.season.calculate_scores()
            # If the players for a PlayerPairing in the current round are edited, then we can update the player ranks
            if (
                white_changed or black_changed) and lpp.round.publish_pairings and not lpp.round.is_completed:
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
        if result_changed and (
            result_is_forfeit(self.result) or result_is_forfeit(self.initial_result)):
            signals.pairing_forfeit_changed.send(sender=self.__class__, instance=self)

        # Update scheduled notifications based on the scheduled time
        if scheduled_time_changed:
            league = self.get_round().season.league
            # Calling the save method triggers the logic to recreate notifications
            white_setting = PlayerNotificationSetting.get_or_default(player_id=self.white_id,
                                                                     type='before_game_time',
                                                                     league=league)
            white_setting.save()
            black_setting = PlayerNotificationSetting.get_or_default(player_id=self.black_id,
                                                                     type='before_game_time',
                                                                     league=league)
            black_setting.save()
            if white_changed and self.initial_white_id:
                old_white_setting = PlayerNotificationSetting.get_or_default(
                    player_id=self.initial_white_id, type='before_game_time', league=league)
                old_white_setting.save()
            if black_changed and self.initial_black_id:
                old_black_setting = PlayerNotificationSetting.get_or_default(
                    player_id=self.initial_black_id, type='before_game_time', league=league)
                old_black_setting.save()
            
            self.update_available_upon_schedule(self.white_id)
            self.update_available_upon_schedule(self.black_id)

            # We also want the players to confirm (again) if the scheduled time changes.
            white_confirmed = False
            black_confirmed = False
    
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


def result_is_forfeit(result):
    return result.endswith(('X', 'F', 'Z'))


# -------------------------------------------------------------------------------
class TeamPlayerPairing(PlayerPairing):
    team_pairing = models.ForeignKey(TeamPairing, on_delete=models.CASCADE)
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

    def white_team_rating(self, league=None):
        return self.white_rating_display(
            league) if self.board_number % 2 == 1 else self.black_rating_display(league)

    def black_team_rating(self, league=None):
        return self.black_rating_display(
            league) if self.board_number % 2 == 1 else self.white_rating_display(league)

    def white_team_color(self):
        return 'white' if self.board_number % 2 == 1 else 'black'

    def black_team_color(self):
        return 'black' if self.board_number % 2 == 1 else 'white'

    def white_team_score(self):
        return self.white_score() if self.board_number % 2 == 1 else self.black_score()

    def white_team_score_str(self):
        return format_score(self.white_team_score(), self.game_played())

    def black_team_score(self):
        return self.black_score() if self.board_number % 2 == 1 else self.white_score()

    def black_team_score_str(self):
        return format_score(self.black_team_score(), self.game_played())

    def white_team_match_score(self):
        return self.team_pairing.white_points if self.board_number % 2 == 1 else self.team_pairing.black_points

    def black_team_match_score(self):
        return self.team_pairing.black_points if self.board_number % 2 == 1 else self.team_pairing.white_points

    def white_team_name(self):
        return "%s" % self.white_team().name

    def black_team_name(self):
        return "%s" % self.black_team().name

    def season_name(self):
        return "%s" % self.team_pairing.round.season.name

    def round_number(self):
        return "%d" % self.team_pairing.round.number


# -------------------------------------------------------------------------------
class LonePlayerPairing(PlayerPairing):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
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
    ('alternate_to_full_time',
     'Yes, but I was able to find a consistent team (did not simply fill in for a week or two).'),
    ('full_time', 'No, I was not an alternate for the last season. I played the season.'),
    ('new',
     'No, I was not an alternate for the last season. I am a new member / I took last season off.'),
)

ALTERNATE_PREFERENCE_OPTIONS = (
    ('alternate', 'Alternate'),
    ('full_time', 'Full Time'),
    ('either', "Either is fine for me."),
)


# -------------------------------------------------------------------------------
class Registration(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    status = models.CharField(max_length=255, choices=REGISTRATION_STATUS_OPTIONS)
    status_changed_by = models.CharField(blank=True, max_length=255)
    status_changed_date = models.DateTimeField(blank=True, null=True)

    lichess_username = models.CharField(max_length=255, validators=[username_validator])
    slack_username = models.CharField(max_length=255, blank=True)
    email = models.EmailField(max_length=255)

    classical_rating = models.PositiveIntegerField(verbose_name='rating')
    peak_classical_rating = models.PositiveIntegerField(blank=True, null=True,
                                                        verbose_name='peak rating')
    has_played_20_games = models.BooleanField()
    already_in_slack_group = models.BooleanField()
    previous_season_alternate = models.CharField(blank=True, max_length=255,
                                                 choices=PREVIOUS_SEASON_ALTERNATE_OPTIONS)

    can_commit = models.BooleanField()
    friends = models.CharField(blank=True, max_length=1023)
    avoid = models.CharField(blank=True, max_length=1023)
    agreed_to_rules = models.BooleanField()
    agreed_to_tos = models.BooleanField()
    alternate_preference = models.CharField(blank=True, max_length=255,
                                            choices=ALTERNATE_PREFERENCE_OPTIONS)
    section_preference = models.ForeignKey(Section, on_delete=models.SET_NULL, blank=True,
                                           null=True)
    weeks_unavailable = models.CharField(blank=True, max_length=255)

    validation_ok = models.BooleanField(blank=True, null=True, default=None)
    validation_warning = models.BooleanField(default=False)
    last_validation_try = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return "%s" % (self.lichess_username)

    def previous_registrations(self):
        return Registration.objects.filter(lichess_username__iexact=self.lichess_username,
                                           date_created__lt=self.date_created)

    def other_seasons(self):
        return SeasonPlayer.objects.filter(
            player__lichess_username__iexact=self.lichess_username).exclude(season=self.season)

    def player(self):
        return Player.objects.filter(lichess_username__iexact=self.lichess_username).first()

    @classmethod
    def can_register(cls, user, season):
        if not season or not season.registration_open:
            return False
        return not cls.was_rejected(user, season)

    @classmethod
    def was_rejected(cls, user, season):
        reg = cls.get_latest_registration(user, season)
        return reg and reg.status == 'rejected'

    @classmethod
    def get_latest_registration(cls, user, season):
        return (cls.objects
                .filter(lichess_username__iexact=user.username, season=season)
                .order_by('-date_created')
                .first())

    @classmethod
    def is_registered(cls, user, season):
        return cls.objects.filter(lichess_username__iexact=user.username, season=season).exists()


# -------------------------------------------------------------------------------
class SeasonPlayer(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    registration = models.ForeignKey(Registration, on_delete=models.SET_NULL, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    games_missed = models.PositiveIntegerField(default=0)
    unresponsive = models.BooleanField(default=False)
    seed_rating = models.PositiveIntegerField(blank=True, null=True)
    final_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = ('season', 'player')

    def __init__(self, *args, **kwargs):
        super(SeasonPlayer, self).__init__(*args, **kwargs)
        self.initial_unresponsive = self.unresponsive
        self.initial_player_id = self.player_id
        self.initial_games_missed = self.games_missed
        
    def _set_unavailable_for_season(self, skip_current=False):
        rounds = Round.objects.filter(season=self.season, is_completed=False)
        for r in rounds:
            if skip_current and r.publish_pairings:
                continue
            PlayerAvailability.objects.update_or_create(round=r, player=self.player,
                                                        defaults={'is_available': False})
            
    def has_scheduled_game_in_round(self, round):
        pairingModel = TeamPlayerPairing.objects.filter(team_pairing__round=round)
        if not self.season.league.is_team_league():
            pairingModel = LonePlayerPlairing.objects.filter(round=round)
            
        return pairingModel.filter(
            (Q(white=self.player) | Q(black=self.player)) & Q(scheduled_time__isnull=False)#
          ).exists()
    
    def player_rating_display(self, league=None):
        if self.final_rating is not None:
            return self.final_rating
        else:
            if league is None:
                league = self.season.league
            return self.player.rating_for(league)

    def save(self, *args, **kwargs):
        unresponsive_changed = self.pk is None or self.unresponsive != self.initial_unresponsive
        player_changed = self.pk is None or self.player_id != self.initial_player_id

        if player_changed:
            self.player_rating = None

        if unresponsive_changed and self.unresponsive and hasattr(self, 'alternate'):
            alt = self.alternate
            current_date = timezone.now()
            if alt.priority_date_override is None or alt.priority_date_override < current_date:
                alt.priority_date_override = current_date
                alt.save()
                
        if self.games_missed >= 2 and self.initial_games_missed < 2:
            self._set_unavailable_for_season()

        super(SeasonPlayer, self).save(*args, **kwargs)

    def expected_rating(self, league=None):
        rating = self.player.rating_for(league)
        if rating is None:
            return None
        if self.registration is not None:
            peak = max(self.registration.peak_classical_rating or 0, rating)
            return (rating + peak) / 2
        return rating

    def seed_rating_display(self, league=None):
        if self.seed_rating is not None:
            return self.seed_rating
        else:
            if league is None:
                league = self.season.league
            return self.player.rating_for(league)
    
    @classmethod
    def withdraw_from_team_season(cls, round, player):
        #We can only set players inactive that are not part of a team.
        if not TeamMember.objects.filter(player=player, team__season=round.season).exists():
            cls.objects.filter(season=round.season, player=player).update(is_active=False)
        
        sp = SeasonPlayer.objects.get(season=round.season, player=player)
        sp._set_unavailable_for_season(skip_current=True)
        add_system_comment(sp, 'player withdrawn: %s'%round)
        

    @property
    def card_color(self):
        if self.games_missed >= 2:
            return 'red'
        elif self.games_missed == 1:
            return 'yellow'
        else:
            return None

    def get_loneplayerscore(self):
        try:
            return self.loneplayerscore
        except LonePlayerScore.DoesNotExist:
            return LonePlayerScore.objects.create(season_player=self)

    def __str__(self):
        return "%s - %s" % (self.season, self.player)


# -------------------------------------------------------------------------------
class LonePlayerScore(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer, on_delete=models.CASCADE)
    points = ScoreField(default=0)
    late_join_points = ScoreField(default=0)
    tiebreak1 = ScoreField(default=0)
    tiebreak2 = ScoreField(default=0)
    tiebreak3 = ScoreField(default=0)
    tiebreak4 = ScoreField(default=0)
    acceleration_group = models.PositiveIntegerField(default=0)

    perf_rating = models.PositiveIntegerField(blank=True, null=True)

    def round_scores(self, rounds, player_number_dict, white_pairings_dict, black_pairings_dict,
                     byes_dict, include_current=False):
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
                result_type = 'B' if score == 1 else 'H' if score == 0.5 else 'U'
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
        return (
            self.points + self.late_join_points, self.season_player.player_rating_display() or 0)

    def intermediate_standings_sort_key(self):
        return (self.points + self.late_join_points, self.tiebreak1, self.tiebreak2, self.tiebreak3,
                self.tiebreak4, self.season_player.player_rating_display() or 0)

    def final_standings_sort_key(self):
        return (self.points, self.tiebreak1, self.tiebreak2, self.tiebreak3, self.tiebreak4,
                self.season_player.player_rating_display() or 0)

    def __str__(self):
        return "%s" % (self.season_player)


def lone_player_pairing_rank_dict(season):
    raw_player_scores = LonePlayerScore.objects.filter(season_player__season=season) \
        .select_related('season_player__season__league', 'season_player__player').nocache()
    player_scores = list(
        enumerate(sorted(raw_player_scores, key=lambda s: s.pairing_sort_key(), reverse=True), 1))
    return {p.season_player.player_id: n for n, p in player_scores}


# -------------------------------------------------------------------------------
class PlayerAvailability(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = 'player availabilities'

    def __str__(self):
        return "%s" % self.player


ALTERNATE_STATUS_OPTIONS = (
    ('waiting', 'Waiting'),
    ('contacted', 'Contacted'),
    ('accepted', 'Accepted'),
    ('declined', 'Declined'),
    ('unresponsive', 'Unresponsive'),
)


# -------------------------------------------------------------------------------
class Alternate(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    priority_date_override = models.DateTimeField(null=True, blank=True)

    status = models.CharField(blank=True, default='waiting', max_length=31,
                              choices=ALTERNATE_STATUS_OPTIONS)
    last_contact_date = models.DateTimeField(null=True, blank=True)
    player_rating = models.PositiveIntegerField(null=True, blank=True)

    def __init__(self, *args, **kwargs):
        super(Alternate, self).__init__(*args, **kwargs)
        self.initial_season_player_id = self.season_player_id
        self.initial_status = self.status

    def player_rating_display(self, league=None):
        if self.player_rating is not None:
            return self.player_rating
        else:
            if league is None:
                league = self.season_player.season.league
            return self.season_player.player.rating_for(league)

    def save(self, *args, **kwargs):
        season_player_changed = self.pk is None or self.season_player_id != self.initial_season_player_id
        status_changed = self.pk is None or self.status != self.initial_status
        if season_player_changed:
            self.player_rating = None
        if status_changed and self.status == 'unresponsive':
            current_date = timezone.now()
            if self.priority_date_override is None or self.priority_date_override < current_date:
                self.priority_date_override = current_date
        super(Alternate, self).save(*args, **kwargs)

    def update_board_number(self):
        season = self.season_player.season
        player = self.season_player.player
        buckets = AlternateBucket.objects.filter(season=season)
        if len(buckets) == season.boards and player.rating_for(season.league) is not None:
            for b in buckets:
                if b.contains(player.rating_for(season.league)):
                    self.board_number = b.board_number
                    self.save()

    def priority_date(self):
        return self.priority_date_and_reason()[0]

    def priority_date_and_reason(self):
        if self.priority_date_override is not None:
            return max((self.priority_date_override, 'Was unresponsive'),
                       self._priority_date_without_override())
        return self._priority_date_without_override()

    def _priority_date_without_override(self):
        most_recent_assign = AlternateAssignment.objects.filter(
            team__season_id=self.season_player.season_id, player_id=self.season_player.player_id) \
            .order_by('-round__start_date').first()

        if most_recent_assign is not None:
            round_date = most_recent_assign.round.end_date
            if round_date is not None:
                return (round_date, 'Assigned game')

        if self.season_player.registration is not None:
            return (self.season_player.registration.date_created, 'Registered')

        return (self.date_created, 'Made alternate')

    def __str__(self):
        return "%s" % self.season_player

    def __lt__(self, other):
        return self.priority_date() < other.priority_date()


# -------------------------------------------------------------------------------
class AlternateAssignment(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    replaced_player = models.ForeignKey(Player,
                                        null=True, blank=True, on_delete=models.SET_NULL,
                                        related_name='alternate_replacements')

    class Meta:
        unique_together = ('round', 'team', 'board_number')

    def __init__(self, *args, **kwargs):
        super(AlternateAssignment, self).__init__(*args, **kwargs)
        self.initial_player_id = self.player_id
        self.initial_team_id = self.team_id
        self.initial_board_number = self.board_number

    def clean(self):
        if self.round_id and self.team_id and self.round.season_id != self.team.season_id:
            raise ValidationError('Round and team seasons must match')
        if self.team_id and self.player_id and not SeasonPlayer.objects.filter(
            season=self.team.season, player=self.player).exists():
            raise ValidationError('Assigned player must be a player in the season')

    def save(self, *args, **kwargs):
        if self.replaced_player is None:
            tm = TeamMember.objects.filter(team=self.team, board_number=self.board_number).first()
            if tm is not None:
                self.replaced_player = tm.player

        super(AlternateAssignment, self).save(*args, **kwargs)

        # Find and update any current pairings
        white_pairing = self.team.pairings_as_white.filter(round=self.round).first()
        if white_pairing is not None:
            pairing = white_pairing.teamplayerpairing_set.filter(
                board_number=self.board_number).nocache().first()
            if pairing is not None:
                if self.board_number % 2 == 1:
                    pairing.white = self.player
                else:
                    pairing.black = self.player
                pairing.save()
        black_pairing = self.team.pairings_as_black.filter(round=self.round).first()
        if black_pairing is not None:
            pairing = black_pairing.teamplayerpairing_set.filter(
                board_number=self.board_number).nocache().first()
            if pairing is not None:
                if self.board_number % 2 == 1:
                    pairing.black = self.player
                else:
                    pairing.white = self.player
                pairing.save()

    def __str__(self):
        return "%s - %s - Board %d" % (self.round, self.team.name, self.board_number)


# -------------------------------------------------------------------------------
class AlternateBucket(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    min_rating = models.PositiveIntegerField(null=True, blank=True)
    max_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('season', 'board_number')

    def contains(self, rating):
        if rating is None:
            return self.min_rating is None
        return (self.min_rating is None or rating > self.min_rating) and (
            self.max_rating is None or rating <= self.max_rating)

    def __str__(self):
        return "Board %d (%s, %s]" % (self.board_number, self.min_rating, self.max_rating)


def create_api_token():
    return get_random_string(length=32)


ALTERNATE_SEARCH_STATUS_OPTIONS = (
    ('started', 'Started'),
    ('all_contacted', 'All alternates contacted'),
    ('completed', 'Completed'),
    ('cancelled', 'Cancelled'),
    ('failed', 'Failed'),
)


# -------------------------------------------------------------------------------
class AlternateSearch(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    is_active = models.BooleanField(default=True)
    status = models.CharField(blank=True, max_length=31, choices=ALTERNATE_SEARCH_STATUS_OPTIONS)
    last_alternate_contact_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ('round', 'team', 'board_number')

    def clean(self):
        if self.round_id and self.team_id and self.round.season_id != self.team.season_id:
            raise ValidationError('Round and team seasons must match')

    def still_needs_alternate(self):
        if self.round.publish_pairings:
            team_pairing = self.team.get_teampairing(self.round)
            player_pairing = TeamPlayerPairing.objects.filter(team_pairing=team_pairing,
                                                              board_number=self.board_number,
                                                              result='',
                                                              game_link='').nocache().first()
            return player_pairing is not None and \
                   (player_pairing.white_team() == self.team and (
                       not player_pairing.white or not player_pairing.white.is_available_for(
                       self.round)) or \
                    player_pairing.black_team() == self.team and (
                        not player_pairing.black or not player_pairing.black.is_available_for(
                        self.round)))
        else:
            player = None
            aa = AlternateAssignment.objects.filter(round=self.round, team=self.team,
                                                    board_number=self.board_number).first()
            if aa is not None:
                player = aa.player
            else:
                team_member = TeamMember.objects.filter(team=self.team,
                                                        board_number=self.board_number).first()
                if team_member is not None:
                    player = team_member.player
            return player is not None and not player.is_available_for(self.round)

    def __str__(self):
        return "%s - %s - Board %d" % (self.round, self.team.name, self.board_number)


# -------------------------------------------------------------------------------
class AlternatesManagerSetting(_BaseModel):
    league = models.OneToOneField(League, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    contact_interval = models.DurationField(default=timedelta(hours=8),
                                            help_text='How long before the next alternate will be contacted during the round.')
    unresponsive_interval = models.DurationField(default=timedelta(hours=24),
                                                 help_text='How long after being contacted until an alternate will be marked as unresponsive.')
    rating_flex = models.PositiveIntegerField(default=0,
                                              help_text='How far out of a board\'s rating range an alternate can be if it helps alternate balance.')

    contact_before_round_start = models.BooleanField(default=True,
                                                     help_text='If we should search for alternates before the pairings are published. Has no effect for round 1.')
    contact_offset_before_round_start = models.DurationField(default=timedelta(hours=48),
                                                             help_text='How long before the round starts we should start searching for alternates. Also ends the previous round searches early.')
    contact_interval_before_round_start = models.DurationField(default=timedelta(hours=12),
                                                               help_text='How long before the next alternate will be contacted, if the round hasn\'t started yet.')

    def clean(self):
        if self.league_id and self.league.competitor_type != 'team':
            raise ValidationError(
                'Alternates manager settings can only be created for team leagues')

    def __str__(self):
        return "%s" % (self.league)


# -------------------------------------------------------------------------------
class SeasonPrize(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()
    max_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('season', 'rank', 'max_rating')

    def __str__(self):
        if self.max_rating is not None:
            return '%s - U%d #%d' % (self.season, self.max_rating, self.rank)
        else:
            return '%s - #%d' % (self.season, self.rank)


# -------------------------------------------------------------------------------
class SeasonPrizeWinner(_BaseModel):
    season_prize = models.ForeignKey(SeasonPrize, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('season_prize', 'player')

    def __str__(self):
        return '%s - %s' % (self.season_prize, self.player)


# -------------------------------------------------------------------------------
class GameNomination(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    nominating_player = models.ForeignKey(Player,
                                          on_delete=models.CASCADE)
    game_link = models.URLField(validators=[game_link_validator])
    pairing = models.ForeignKey(PlayerPairing, blank=True, null=True, on_delete=models.SET_NULL)

    def __str__(self):
        return '%s - %s' % (self.season, self.nominating_player)


# -------------------------------------------------------------------------------
class GameSelection(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    game_link = models.URLField(validators=[game_link_validator])
    pairing = models.ForeignKey(PlayerPairing, blank=True, null=True, on_delete=models.SET_NULL)

    class Meta:
        unique_together = ('season', 'game_link')

    def __str__(self):
        return '%s - %s' % (self.season, self.game_link)


class AvailableTime(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    time = models.DateTimeField()


# -------------------------------------------------------------------------------
class NavItem(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', blank=True, null=True, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    text = models.CharField(max_length=255)
    path = models.CharField(max_length=1023, blank=True)
    league_relative = models.BooleanField(default=False)
    season_relative = models.BooleanField(default=False)
    append_separator = models.BooleanField(default=False)

    def __str__(self):
        return '%s - %s' % (self.league, self.text)


# -------------------------------------------------------------------------------
class ApiKey(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)

    def __str__(self):
        return self.name


# -------------------------------------------------------------------------------
class PrivateUrlAuth(_BaseModel):
    # Note: Could separate the one-time-URL and timed-auth portions into separate models at some point in the future
    authenticated_user = models.CharField(max_length=255, validators=[username_validator])
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_expired(self):
        return self.expires < timezone.now()

    def __str__(self):
        return self.authenticated_user


# -------------------------------------------------------------------------------
class LoginToken(_BaseModel):
    lichess_username = models.CharField(max_length=255, blank=True, validators=[username_validator])
    username_hint = models.CharField(max_length=255, blank=True)
    slack_user_id = models.CharField(max_length=255, blank=True)
    secret_token = models.CharField(max_length=255, unique=True, default=create_api_token)
    mail_id = models.CharField(max_length=255, blank=True)
    source_ip = models.GenericIPAddressField(null=True, blank=True)
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_expired(self):
        return self.expires < timezone.now()

    def __str__(self):
        return self.lichess_username or self.slack_user_id


# -------------------------------------------------------------------------------
class Document(_BaseModel):
    name = models.CharField(max_length=255)
    content = RichTextUploadingField()
    allow_editors = models.BooleanField(default=False, verbose_name='Allow designated editors')
    owner = models.ForeignKey(User,
                              limit_choices_to=models.Q(is_staff=True), on_delete=models.PROTECT)

    def owned_by(self, user):
        return self.owner == user

    def __str__(self):
        return self.name


LEAGUE_DOCUMENT_TYPES = (
    ('faq', 'FAQ'),
    ('rules', 'Rules'),
    ('intro', 'Intro'),
    ('slack-welcome', 'Slack Welcome'),
)


# -------------------------------------------------------------------------------
class LeagueDocument(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    document = models.OneToOneField(Document, on_delete=models.CASCADE)
    tag = models.SlugField(
        help_text='The document will be accessible at /{league_tag}/document/{document_tag}/')
    type = models.CharField(blank=True, max_length=255, choices=LEAGUE_DOCUMENT_TYPES)

    class Meta:
        unique_together = ('league', 'tag')

    def clean(self):
        if SeasonDocument.objects.filter(document_id=self.document_id):
            raise ValidationError('Document already belongs to a season')

    def __str__(self):
        return self.document.name


SEASON_DOCUMENT_TYPES = (
    ('links', 'Links'),
)


# -------------------------------------------------------------------------------
class SeasonDocument(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    document = models.OneToOneField(Document, on_delete=models.CASCADE)
    tag = models.SlugField(
        help_text='The document will be accessible at /{league_tag}/season/{season_tag}/document/{document_tag}/')
    type = models.CharField(blank=True, max_length=255, choices=SEASON_DOCUMENT_TYPES)

    class Meta:
        unique_together = ('season', 'tag')

    def clean(self):
        if LeagueDocument.objects.filter(document_id=self.document_id):
            raise ValidationError('Document already belongs to a league')

    def __str__(self):
        return self.document.name


LEAGUE_CHANNEL_TYPES = (
    ('mod', 'Mods'),
    ('captains', 'Captains'),
    ('scheduling', 'Scheduling'),
)


# -------------------------------------------------------------------------------
class LeagueChannel(_BaseModel):
    # TODO: Rename to LeagueChannel
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=LEAGUE_CHANNEL_TYPES)
    slack_channel = models.CharField(max_length=255)
    slack_channel_id = models.CharField(max_length=255, blank=True)
    send_messages = models.BooleanField(default=True)

    class Meta:
        unique_together = ('league', 'slack_channel', 'type')

    def channel_link(self):
        if not self.slack_channel_id:
            return self.slack_channel
        return '<%s%s|%s>' % (self.slack_channel[0], self.slack_channel_id, self.slack_channel[1:])

    def __str__(self):
        return '%s - %s' % (self.league, self.get_type_display())


SCHEDULED_EVENT_TYPES = (
    ('notify_mods_unscheduled', 'Notify mods of unscheduled games'),
    ('notify_mods_no_result', 'Notify mods of games without results'),
    ('notify_mods_pending_regs', 'Notify mods of pending registrations'),
    ('start_round_transition', 'Start round transition'),
    ('notify_players_unscheduled', 'Notify players of unscheduled games'),
    ('notify_players_game_time', 'Notify players of their game time'),
    ('automod_unresponsive', 'Auto-mod unresponsive players'),
    ('automod_noshow', 'Auto-mod no-shows'),
)

SCHEDULED_EVENT_RELATIVE_TO = (
    ('round_start', 'Round start'),
    ('round_end', 'Round end'),
    ('game_scheduled_time', 'Game scheduled time'),
)


# -------------------------------------------------------------------------------
class ScheduledEvent(_BaseModel):
    league = models.ForeignKey(League, blank=True, null=True, on_delete=models.CASCADE)
    season = models.ForeignKey(Season, blank=True, null=True, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=SCHEDULED_EVENT_TYPES)
    offset = models.DurationField()
    relative_to = models.CharField(max_length=255, choices=SCHEDULED_EVENT_RELATIVE_TO)
    last_run = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return '%s' % (self.get_type_display())

    def run(self, obj):
        self.last_run = timezone.now()
        self.save()

        if self.type == 'notify_mods_unscheduled' and isinstance(obj, Round):
            signals.notify_mods_unscheduled.send(sender=self.__class__, round_=obj)
        elif self.type == 'notify_mods_no_result' and isinstance(obj, Round):
            signals.notify_mods_no_result.send(sender=self.__class__, round_=obj)
        elif self.type == 'notify_mods_pending_regs' and isinstance(obj, Round):
            signals.notify_mods_pending_regs.send(sender=self.__class__, round_=obj)
        elif self.type == 'start_round_transition' and isinstance(obj, Round):
            signals.do_round_transition.send(sender=self.__class__, round_id=obj.pk)
        elif self.type == 'notify_players_unscheduled' and isinstance(obj, Round):
            signals.notify_players_unscheduled.send(sender=self.__class__, round_=obj)
        elif self.type == 'notify_players_game_time' and isinstance(obj, PlayerPairing):
            signals.notify_players_game_time.send(sender=self.__class__, pairing=obj)
        elif self.type == 'automod_unresponsive' and isinstance(obj, Round):
            signals.automod_unresponsive.send(sender=self.__class__, round_=obj)
        elif self.type == 'automod_noshow' and isinstance(obj, PlayerPairing):
            signals.automod_noshow.send(sender=self.__class__, pairing=obj)

    def clean(self):
        if self.league_id and self.season_id and self.season.league != self.league:
            raise ValidationError('League and season must be compatible')


PLAYER_NOTIFICATION_TYPES = (
    ('round_started', 'Round started'),
    ('before_game_time', 'Before game time'),
    ('game_started', 'Game started'),
    ('game_time', 'Game time'),
    ('unscheduled_game', 'Unscheduled game'),
    ('game_warning', 'Game warning'),
    ('alternate_needed', 'Alternate needed'),
)


# -------------------------------------------------------------------------------
class PlayerNotificationSetting(_BaseModel):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=PLAYER_NOTIFICATION_TYPES)
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    offset = models.DurationField(blank=True, null=True)
    enable_lichess_mail = models.BooleanField()
    enable_slack_im = models.BooleanField()
    enable_slack_mpim = models.BooleanField()

    class Meta:
        unique_together = ('player', 'type', 'league')

    def __str__(self):
        return '%s - %s' % (self.player, self.get_type_display())

    def save(self, *args, **kwargs):
        super(PlayerNotificationSetting, self).save(*args, **kwargs)
        if self.type == 'before_game_time':
            # Rebuild scheduled notifications based on offset
            self.schedulednotification_set.all().delete()
            upcoming_pairings = self.player.pairings.filter(scheduled_time__gt=timezone.now())
            upcoming_pairings = upcoming_pairings.filter(
                teamplayerpairing__team_pairing__round__season__league=self.league) | \
                                upcoming_pairings.filter(
                                    loneplayerpairing__round__season__league=self.league)
            for p in upcoming_pairings:
                notification_time = p.scheduled_time - self.offset
                ScheduledNotification.objects.create(setting=self, pairing=p,
                                                     notification_time=notification_time)

    @classmethod
    def get_or_default(cls, **kwargs):
        obj = PlayerNotificationSetting.objects.filter(**kwargs).first()
        if obj is not None:
            return obj
        # Return (but don't create) the default setting based on the type
        obj = PlayerNotificationSetting(**kwargs)
        type_ = kwargs.get('type')
        if type_ == 'before_game_time' and obj.offset is not None:
            del kwargs['offset']
            has_other_offset = PlayerNotificationSetting.objects.filter(**kwargs).exists()
            if has_other_offset or obj.offset != timedelta(minutes=60):
                # Non-default offset, so leave everything disabled
                return obj
        obj.enable_lichess_mail = type_ in ('round_started', 'game_warning', 'alternate_needed')
        obj.enable_slack_im = type_ in (
            'round_started', 'game_started', 'before_game_time', 'game_time', 'unscheduled_game',
            'alternate_needed')
        obj.enable_slack_mpim = type_ in (
            'round_started', 'game_started', 'before_game_time', 'game_time', 'unscheduled_game')
        if type_ == 'before_game_time':
            obj.offset = timedelta(minutes=60)
        return obj

    def clean(self):
        if self.type in ('before_game_time',):
            if self.offset is None:
                raise ValidationError('Offset is required for this type')
        else:
            if self.offset is not None:
                raise ValidationError('Offset is not applicable for this type')


# -------------------------------------------------------------------------------
class PlayerPresence(_BaseModel):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    pairing = models.ForeignKey(PlayerPairing, on_delete=models.CASCADE)
    round = models.ForeignKey(Round, on_delete=models.CASCADE)

    first_msg_time = models.DateTimeField(null=True, blank=True)
    last_msg_time = models.DateTimeField(null=True, blank=True)
    online_for_game = models.BooleanField(default=False)

    def __str__(self):
        return '%s' % (self.player)


PLAYER_WARNING_TYPE_OPTIONS = (
    ('unresponsive', 'unresponsive'),
    ('card_unresponsive', 'card for unresponsive'),
    ('card_noshow', 'card for no-show'),
)


# -------------------------------------------------------------------------------
class PlayerWarning(_BaseModel):
    round = models.ForeignKey(Round, null=True, blank=True, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=PLAYER_WARNING_TYPE_OPTIONS)

    class Meta:
        unique_together = ('round', 'player', 'type')

    def __str__(self):
        return '%s - %s' % (self.player.lichess_username, self.get_type_display())


# -------------------------------------------------------------------------------
class ScheduledNotification(_BaseModel):
    setting = models.ForeignKey(PlayerNotificationSetting, on_delete=models.CASCADE)
    pairing = models.ForeignKey(PlayerPairing, on_delete=models.CASCADE)
    notification_time = models.DateTimeField()

    def __str__(self):
        return '%s' % (self.setting)

    def save(self, *args, **kwargs):
        if self.notification_time < timezone.now():
            if self.pk:
                self.delete()
        else:
            super(ScheduledNotification, self).save(*args, **kwargs)

    def run(self):
        try:
            if self.setting.type == 'before_game_time':
                pairing = PlayerPairing.objects.nocache().get(pk=self.pairing_id)
                if pairing.scheduled_time is not None:
                    signals.before_game_time.send(sender=self.__class__, player=self.setting.player,
                                                  pairing=pairing, offset=self.setting.offset)
        except Exception:
            logger.exception('Error running scheduled notification')
        self.delete()

    def clean(self):
        if self.setting.offset is None:
            raise ValidationError('Setting must have an offset')


# -------------------------------------------------------------------------------
class FcmSub(_BaseModel):
    slack_user_id = models.CharField(max_length=31)
    reg_id = models.CharField(max_length=4096, unique=True)


MOD_REQUEST_STATUS_OPTIONS = (
    ('pending', 'Pending'),
    ('approved', 'Approved'),
    ('rejected', 'Rejected'),
)

MOD_REQUEST_TYPE_OPTIONS = (
    ('withdraw', 'Withdraw'),
    ('reregister', 'Re-register'),
    ('appeal_late_response', 'Appeal late response'),
    ('appeal_noshow', 'Appeal no-show'),
    ('appeal_draw_scheduling', 'Appeal scheduling draw'),
    ('claim_win_noshow', 'Claim a forfeit win (no-show)'),
    ('claim_win_effort', 'Claim a forfeit win (insufficient effort)'),
    ('claim_draw_scheduling', 'Claim a scheduling draw'),
    ('claim_loss', 'Claim a forfeit loss'),
    ('request_continuation', 'Request continuation'),
)

# A plain string literal won't work as a Django signal sender since it will have a unique object reference
# By using a common dict we can make sure we're working with the same object (using `intern` would also work)
# This also has the advantage that typos will create a KeyError instead of silently failing
MOD_REQUEST_SENDER = {a: a for a, _ in MOD_REQUEST_TYPE_OPTIONS}


# -------------------------------------------------------------------------------
class ModRequest(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    round = models.ForeignKey(Round, null=True, blank=True, on_delete=models.CASCADE)
    pairing = models.ForeignKey(PlayerPairing, null=True, blank=True, on_delete=models.CASCADE)
    requester = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=MOD_REQUEST_TYPE_OPTIONS)
    status = models.CharField(max_length=31, choices=MOD_REQUEST_STATUS_OPTIONS)
    status_changed_by = models.CharField(blank=True, max_length=255)
    status_changed_date = models.DateTimeField(blank=True, null=True)

    notes = models.TextField(blank=True)
    # TODO: Multiple screenshot support?
    screenshot = models.ImageField(upload_to='screenshots/%Y/%m/%d/', null=True, blank=True)
    response = models.TextField(blank=True)

    def approve(self, user='System', response=''):
        with reversion.create_revision():
            reversion.set_comment(f'Mod request approved by {user}')
            self.status = 'approved'
            self.status_changed_by = user
            self.status_changed_date = timezone.now()
            self.response = response
            self.save()
        signals.mod_request_approved.send(sender=MOD_REQUEST_SENDER[self.type], instance=self)

    def reject(self, user='System', response=''):
        with reversion.create_revision():
            reversion.set_comment(f'Mod request rejected by {user}')
            self.status = 'rejected'
            self.status_changed_by = user
            self.status_changed_date = timezone.now()
            self.response = response
            self.save()
        signals.mod_request_rejected.send(sender=MOD_REQUEST_SENDER[self.type], instance=self,
                                          response=response)

    def clean(self):
        pass
        # TODO: This validation isn't working because type is not populated in the form.

    #         if not self.screenshot and self.type in ('appeal_late_response', 'claim_win_noshow', 'claim_win_effort', 'claim_draw_scheduling'):
    #             raise ValidationError('Screenshot is required')

    def __str__(self):
        return '%s - %s' % (self.requester.lichess_username, self.get_type_display())
