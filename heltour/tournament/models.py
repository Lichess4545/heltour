from __future__ import annotations
import logging
import re
from collections import namedtuple
from collections.abc import Callable
from typing import ClassVar
from datetime import datetime, timedelta

import reversion
from ckeditor_uploader.fields import RichTextUploadingField
from django import forms as django_forms
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import connection, models, transaction
from django.db.models import JSONField, Q
from django.utils import timezone
from django.utils.crypto import get_random_string
from django_comments.models import Comment
from phonenumber_field.modelfields import PhoneNumberField
from django_countries.fields import CountryField

from django.conf import settings
from heltour.tournament import signals
from heltour.tournament_core import tiebreaks

logger = logging.getLogger(__name__)


# Helper function to find an item in a list by its properties
def find(lst, **prop_values):
    for k, v in list(prop_values.items()):
        lst = [obj for obj in lst if getnestedattr(obj, k) == v]
    return next(iter(lst), None)


def getnestedattr(obj, k):
    for k2 in k.split("__"):
        if obj is None:
            return None
        obj = getattr(obj, k2)
    return obj


def abs_url(url):
    site = Site.objects.get_current().domain
    return "%s://%s%s" % (settings.LINK_PROTOCOL, site, url)


def add_system_comment(obj, text, user_name="System"):
    Comment.objects.create(
        content_object=obj,
        site=Site.objects.get_current(),
        user_name=user_name,
        comment=text,
        submit_date=timezone.now(),
        is_public=True,
    )


def format_score(score, game_played=None):
    if score is None:
        return ""

    # Handle quarter values
    if str(score) == "0.25":
        score_str = "\u00bc"
    elif str(score) == "0.5":
        score_str = "\u00bd"
    elif str(score) == "0.75":
        score_str = "\u00be"
    else:
        score_str = (
            str(score)
            .replace(".0", "")
            .replace(".25", "\u00bc")
            .replace(".5", "\u00bd")
            .replace(".75", "\u00be")
        )

    if game_played is False:
        if score == 1:
            score_str += "X"
        elif score == 0.5:
            score_str += "Z"
        elif score == 0:
            score_str += "F"
    return score_str


# Represents a positive number in increments of 0.25 (0, 0.25, 0.5, 0.75, 1, etc.)
class ScoreField(models.PositiveIntegerField):
    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return value / 4.0

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        return int(value * 4)

    def to_python(self, value):
        if value is None or value == "":
            return None
        return float(value)

    def formfield(self, **kwargs):
        defaults = {
            "widget": django_forms.TextInput(attrs={"class": "vIntegerField"}),
            "initial": self.default,
        }
        defaults.update(kwargs)
        return django_forms.FloatField(**defaults)


# -------------------------------------------------------------------------------
class _BaseModel(models.Model):
    date_created = models.DateTimeField(auto_now_add=True)
    date_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


THEME_OPTIONS = (
    ("blue", "Blue"),
    ("green", "Green"),
    ("red", "Red"),
    ("yellow", "Yellow"),
    ("custom", "Custom (colors from settings)"),
)
RATING_TYPE_OPTIONS = (
    ("classical", "Classical"),
    ("rapid", "Rapid"),
    ("chess960", "Chess 960"),
    ("blitz", "Blitz"),
    ("fide_standard", "FIDE Standard"),
    ("fide_rapid", "FIDE Rapid"),
    ("fide_blitz", "FIDE Blitz"),
    ("fide", "FIDE (Standard → Rapid → Blitz)"),
)

# Order in which FIDE rating keys are tried for the "fide" rating type.
FIDE_RATING_FALLBACK_KEYS = ("standard", "rapid", "blitz")
FIDE_RATING_DEFAULT = 1400


def is_fide_rating_type(rating_type: str) -> bool:
    return rating_type == "fide" or rating_type.startswith("fide_")


COMPETITOR_TYPE_OPTIONS = (
    ("team", "Team"),
    ("individual", "Individual"),
)
PAIRING_TYPE_OPTIONS = (
    ("swiss-dutch", "Swiss Tournament: Dutch Algorithm"),
    ("swiss-dutch-baku-accel", "Swiss Tournament: Dutch Algorithm + Baku Acceleration"),
    ("knockout-single", "Knockout Tournament: Single Match"),
    ("knockout-multi", "Knockout Tournament: Multi-Match"),
)
KNOCKOUT_SEEDING_OPTIONS = (
    ("traditional", "Traditional (1 vs 32, 2 vs 31, etc.)"),
    ("adjacent", "Adjacent (1 vs 2, 3 vs 4, etc.)"),
)
KNOCKOUT_STAGE_OPTIONS = (
    ("round-of-128", "Round of 128"),
    ("round-of-64", "Round of 64"),
    ("round-of-32", "Round of 32"),
    ("round-of-16", "Round of 16"),
    ("quarterfinals", "Quarter-finals"),
    ("semifinals", "Semi-finals"),
    ("finals", "Finals"),
)
TEAM_TIEBREAK_OPTIONS = (
    ("match_points", "Match Points"),
    ("game_points", "Game Points"),
    ("head_to_head", "Head-to-Head"),
    ("games_won", "Games Won"),
    ("sonneborn_berger", "Sonneborn-Berger"),
    ("buchholz", "Buchholz"),
    ("eggsb", "EGGSB - Extended Game-Game Sonneborn-Berger"),
    ("emmsb", "EMMSB - Extended Match-Match Sonneborn-Berger"),
    ("emgsb", "EMGSB - Extended Match-Game Sonneborn-Berger"),
    ("egmsb", "EGMSB - Extended Game-Match Sonneborn-Berger"),
)
LONE_TIEBREAK_OPTIONS = (
    ("head_to_head", "Head-to-Head"),
    ("buchholz_cut1", "Buchholz Cut-1"),
    ("buchholz", "Buchholz"),
    ("games_won", "Games Won"),
    ("games_with_black", "Games with Black"),
    ("sonneborn_berger", "Sonneborn-Berger"),
)


# -------------------------------------------------------------------------------
class RegistrationMode(models.TextChoices):
    OPEN = "open", "Open/Established Rating"
    INVITE_ONLY = "invite_only", "Invite By Code"


# -------------------------------------------------------------------------------
class ValidationStatus(models.TextChoices):
    OK = "ok", "OK"
    WARNING = "warning", "Warning"
    ERROR = "error", "Error"


# -------------------------------------------------------------------------------
class League(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    tag = models.SlugField(
        unique=True, help_text="The league will be accessible at /{league_tag}/"
    )
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
    skip_slack_invites = models.BooleanField(
        default=True,
        help_text="Skip sending Slack workspace invites when approving registrations",
    )
    registration_mode = models.CharField(
        max_length=20,
        choices=RegistrationMode.choices,
        default=RegistrationMode.OPEN,
        help_text="Controls how players can register for this league",
    )
    email_required = models.BooleanField(
        default=False,
        help_text="If true, email is required during registration. Default is false (email optional).",
    )
    show_provisional_warning = models.BooleanField(
        default=True,
        help_text="If true, show warning about provisional ratings during registration. Default is true.",
    )
    ask_availability = models.BooleanField(
        default=True,
        help_text="If true, ask players about their availability during registration. Default is true.",
    )
    # Personal information settings
    require_name = models.BooleanField(
        default=False,
        help_text="If true, require first_name and last_name during registration. Default is false.",
    )
    require_personal_email = models.BooleanField(
        default=False,
        help_text="If true, require personal_email during registration. Default is false.",
    )
    require_gender = models.BooleanField(
        default=False,
        help_text="If true, require gender during registration. Default is false.",
    )
    require_date_of_birth = models.BooleanField(
        default=False,
        help_text="If true, require date_of_birth during registration. Default is false.",
    )
    require_nationality = models.BooleanField(
        default=False,
        help_text="If true, require nationality during registration. Default is false.",
    )

    # Corporate/organizational information settings
    organisation_label = models.CharField(
        max_length=100,
        blank=True,
        default="Company / University / Organisation",
        help_text="Label used for organisation-related fields in registration and team creation forms (e.g., 'Company', 'University', 'Organisation').",
    )
    require_corporate_email = models.BooleanField(
        default=False,
        help_text="If true, require corporate_email during registration. Default is false.",
    )
    require_contact_number = models.BooleanField(
        default=False,
        help_text="If true, require contact_number during registration. Default is false.",
    )

    # Chess federation information
    require_fide_id = models.BooleanField(
        default=False,
        help_text="If true, require FIDE ID during registration. Default is false.",
    )
    require_regional_rating = models.BooleanField(
        default=False,
        help_text="If true, require a regional rating during registration. Default is false.",
    )
    regional_rating_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Name of the regional rating system (e.g., 'USCF', 'ECF', 'CFC'). Used when require_regional_rating is True.",
    )
    show_fide_names = models.BooleanField(
        default=False,
        help_text="If true, display FIDE names with lichess usernames in parentheses.",
    )

    # Team league tiebreak configuration
    team_tiebreak_1 = models.CharField(
        max_length=32,
        choices=TEAM_TIEBREAK_OPTIONS,
        blank=True,
        default="game_points",
        help_text="First tiebreak for team tournaments",
    )
    team_tiebreak_2 = models.CharField(
        max_length=32,
        choices=TEAM_TIEBREAK_OPTIONS,
        blank=True,
        default="head_to_head",
        help_text="Second tiebreak for team tournaments",
    )
    team_tiebreak_3 = models.CharField(
        max_length=32,
        choices=TEAM_TIEBREAK_OPTIONS,
        blank=True,
        default="games_won",
        help_text="Third tiebreak for team tournaments",
    )
    team_tiebreak_4 = models.CharField(
        max_length=32,
        choices=TEAM_TIEBREAK_OPTIONS,
        blank=True,
        default="sonneborn_berger",
        help_text="Fourth tiebreak for team tournaments",
    )

    # Lone league tiebreak configuration (FIDE order by default)
    lone_tiebreak_1 = models.CharField(
        max_length=32,
        choices=LONE_TIEBREAK_OPTIONS,
        blank=True,
        default="head_to_head",
        help_text="First tiebreak for individual tournaments",
    )
    lone_tiebreak_2 = models.CharField(
        max_length=32,
        choices=LONE_TIEBREAK_OPTIONS,
        blank=True,
        default="buchholz_cut1",
        help_text="Second tiebreak for individual tournaments",
    )
    lone_tiebreak_3 = models.CharField(
        max_length=32,
        choices=LONE_TIEBREAK_OPTIONS,
        blank=True,
        default="buchholz",
        help_text="Third tiebreak for individual tournaments",
    )
    lone_tiebreak_4 = models.CharField(
        max_length=32,
        choices=LONE_TIEBREAK_OPTIONS,
        blank=True,
        default="games_won",
        help_text="Fourth tiebreak for individual tournaments",
    )
    lone_tiebreak_5 = models.CharField(
        max_length=32,
        choices=LONE_TIEBREAK_OPTIONS,
        blank=True,
        default="games_with_black",
        help_text="Fifth tiebreak for individual tournaments",
    )

    # Knockout tournament settings
    knockout_games_per_match = models.PositiveIntegerField(
        default=1,
        help_text="Number of games per knockout match (1 for single, 2+ for multi-game)",
    )
    knockout_seeding_style = models.CharField(
        max_length=16,
        choices=KNOCKOUT_SEEDING_OPTIONS,
        default="traditional",
        help_text="Knockout bracket seeding pattern",
    )

    class Meta:
        permissions = (("view_dashboard", "Can view dashboard"),)

    @property
    def registration_season(self):
        return Season.get_registration_season(league=self)

    @property
    def most_recent_season(self):
        return self.season_set.order_by("-start_date").first()

    def time_control_initial(self):
        parts = self.time_control.split("+")
        if len(parts) != 2:
            return None
        return int(parts[0]) * 60

    def time_control_increment(self):
        parts = self.time_control.split("+")
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
        return self.competitor_type == "team"

    def is_player_scheduled_league(self) -> bool:
        return self.get_leaguesetting().schedule_type == 2

    def get_team_tiebreaks(self):
        """Return ordered list of configured tiebreak names for team leagues"""
        if not self.is_team_league():
            return []
        tiebreaks = []
        for attr in [
            "team_tiebreak_1",
            "team_tiebreak_2",
            "team_tiebreak_3",
            "team_tiebreak_4",
        ]:
            value = getattr(self, attr, None)
            if value and value not in tiebreaks:  # Avoid duplicates
                tiebreaks.append(value)
        return tiebreaks

    def get_lone_tiebreaks(self):
        """Return ordered list of configured tiebreak names for lone leagues"""
        if self.is_team_league():
            return []
        tiebreaks = []
        for attr in [
            "lone_tiebreak_1",
            "lone_tiebreak_2",
            "lone_tiebreak_3",
            "lone_tiebreak_4",
            "lone_tiebreak_5",
        ]:
            value = getattr(self, attr, None)
            if value and value not in tiebreaks:
                tiebreaks.append(value)
        return tiebreaks

    def is_invite_only(self):
        return self.registration_mode == RegistrationMode.INVITE_ONLY

    def get_active_players(self):
        def loneteam_query() -> str:
            if self.is_team_league():
                return """
                       INNER JOIN tournament_teamplayerpairing tpp ON tpp.playerpairing_ptr_id = pp.id
                       INNER JOIN tournament_teampairing tp ON tpp.team_pairing_id = tp.id
                       """
            else:
                return """
                       INNER JOIN tournament_loneplayerpairing tp ON tp.playerpairing_ptr_id = pp.id
                       """

        def games_query(*, colour: str) -> str:
            return f"""
                    SELECT pp.{colour}_id as player_id, scheduled_time as played_time
                    FROM tournament_playerpairing pp
                    {loneteam_query()}
                    INNER JOIN tournament_round r ON tp.round_id = r.id
                    INNER JOIN tournament_season s ON r.season_id = s.id
                    INNER JOIN tournament_league l ON s.league_id = l.id
                    WHERE pp.game_link != '' AND l.id = %s
                    """

        query = f"""
                 SELECT player_id, COUNT(player_id) as game_count, MAX(played_time) as last_played
                 FROM (
                 {games_query(colour="white")}
                 UNION ALL
                 {games_query(colour="black")}
                 ) as all_games
                 GROUP BY player_id
                 ORDER BY game_count DESC
                 """
        with connection.cursor() as cursor:
            cursor.execute(query, [self.pk, self.pk])
            desc = cursor.description
            nt_result = namedtuple("Player", [col[0] for col in desc])
            return [nt_result(*row) for row in cursor.fetchall()]

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
    start_games = models.BooleanField(
        default=False,
        help_text=(
            "Try to start games automatically, if the scheduled time was confirmed by both players. "
            "Games are started in 5 minute batches."
        ),
    )
    start_clocks = models.BooleanField(
        default=False,
        help_text="For games started by us, automatically start clocks too.",
    )
    start_clock_time = models.PositiveSmallIntegerField(
        default=6,
        help_text=(
            "For games started by us, start clocks n minutes later. Since we start games in 5 minute batches, "
            "a value of 5 will mean most games are started at the scheduled time. "
            "This also means that you should and cannot set this value below 5."
        ),
        validators=[
            MinValueValidator(
                5,
                message="Values below 5 would make clocks start before the scheduled time.",
            ),
            MaxValueValidator(
                30,
                message=(
                    "Pick a value <= 30. If we start clocks too late, "
                    "we might hit lichess api limits."
                ),
            ),
        ],
    )

    class ScheduleType(models.IntegerChoices):
        FIXED_TIME = 1, "Fixed Time - All games start at set times"
        TIME_WINDOW = 2, "Time Window - Players schedule within deadline"

    schedule_type = models.PositiveSmallIntegerField(
        choices=ScheduleType.choices,
        default=ScheduleType.FIXED_TIME,
        help_text="How game scheduling is handled for this league",
    )

    board_update_deadline_minutes = models.PositiveIntegerField(
        default=15,
        help_text="Minutes before round start when team board assignments are locked",
    )

    def __str__(self):
        return "%s Settings" % self.league


PLAYOFF_OPTIONS = (
    (0, "None"),
    (1, "Finals"),
    (2, "Semi-Finals"),
    (3, "Quarter-Finals"),
)


# -------------------------------------------------------------------------------
class Season(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    tag = models.SlugField(
        help_text="The season will be accessible at /{league_tag}/season/{season_tag}/"
    )
    start_date = models.DateTimeField(blank=True, null=True)
    rounds = models.PositiveIntegerField()
    round_duration = models.DurationField(default=timedelta(days=7))
    boards = models.PositiveIntegerField(blank=True, null=True)
    playoffs = models.PositiveIntegerField(default=0, choices=PLAYOFF_OPTIONS)

    is_active = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)
    registration_open = models.BooleanField(default=False)
    nominations_open = models.BooleanField(default=False)
    codes_per_captain_limit = models.PositiveIntegerField(
        default=20, help_text="Maximum number of invite codes each captain can create"
    )

    create_broadcast = models.BooleanField(
        default=False,
        help_text='Automatically update broadcasts. Run "create broadcast" for initial creation.',
    )
    broadcast_title_override = models.CharField(
        # max length from lichess api
        max_length=80,
        blank=True,
        null=True,
        help_text="Change the broadcast name. Leave empty for default.",
    )

    welcome_message = RichTextUploadingField(
        blank=True,
        help_text="Optional welcome message to display in the registration box. Supports rich text formatting.",
        verbose_name="Welcome Message",
    )

    predefined_player_list = models.TextField(
        blank=True,
        help_text="One entry per line: lichess_username,fide_id",
    )

    validate_account_status = models.BooleanField(default=True)
    validate_has_rating = models.BooleanField(default=True)
    validate_not_provisional = models.BooleanField(default=True)
    validate_agreed_to_rules = models.BooleanField(default=True)
    validate_agreed_to_tos = models.BooleanField(default=True)
    validate_predefined_list_contains_username = models.BooleanField(default=False)
    validate_predefined_list_contains_fide_id = models.BooleanField(default=False)
    validate_predefined_list_contains_username_fide_id_together = models.BooleanField(default=False)

    class Meta:
        unique_together = (("league", "name"), ("league", "tag"))
        permissions = (
            ("manage_players", "Can manage players"),
            ("review_nominated_games", "Can review nominated games"),
        )
        ordering = ["is_completed", "league__name", "-name"]

    def __init__(self, *args, **kwargs):
        super(Season, self).__init__(*args, **kwargs)
        self.initial_rounds = self.rounds
        self.initial_round_duration = self.round_duration
        self.initial_start_date = self.start_date
        self.initial_is_completed = self.is_completed

    def parse_predefined_player_list(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for line in self.predefined_player_list.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(",", 1)
            if len(parts) == 2:
                username = parts[0].strip().lower()
                fide_id = parts[1].strip()
                if username and fide_id:
                    result[username] = fide_id
        return result

    def predefined_fide_to_username(self) -> dict[str, str]:
        return {
            fide: user for user, fide in self.parse_predefined_player_list().items()
        }

    def last_season_alternates(self) -> set[Player]:
        start_date = self.start_date or timezone.now()
        last_season = (
            Season.objects.filter(league=self.league, start_date__lt=start_date)
            .order_by("-start_date")
            .first()
        )
        last_season_alts = (
            Alternate.objects.filter(season_player__season=last_season)
            .select_related("season_player__player")
            .nocache()
        )
        return {alt.season_player.player for alt in last_season_alts}

    def export_players(self):
        last_season_alts = self.last_season_alternates()

        def extract(sp):
            info = {
                "name": sp.player.lichess_username,
                "rating": sp.player.rating_for(self.league),
                "has_20_games": not sp.player.provisional_for(self.league),
                "in_slack": bool(sp.player.slack_user_id),
                "account_status": sp.player.account_status,
                "date_created": None,
                "friends": None,
                "avoid": None,
                "prefers_alt": False,
                "alt_fine": False,
                "previous_season_alternate": sp.player in last_season_alts,
            }
            reg = sp.registration
            if reg is not None:
                info.update(
                    {
                        "date_created": reg.date_created.isoformat(),
                        "friends": reg.friends,
                        "avoid": reg.avoid,
                        "prefers_alt": reg.alternate_preference == "alternate",
                        "alt_fine": reg.alternate_preference == "either",
                    }
                )
            return info

        season_players = (
            self.seasonplayer_set.filter(is_active=True)
            .select_related("player", "registration")
            .nocache()
        )
        return [extract(sp) for sp in season_players]

    def clean(self):
        if (
            self.league_id
            and self.league.competitor_type == "team"
            and self.boards is None
        ):
            raise ValidationError("Boards must be specified for a team season")

    def save(self, *args, **kwargs):
        # TODO: Add validation to prevent changes after a certain point
        new_obj = self.pk is None
        rounds_changed = self.pk is None or self.rounds != self.initial_rounds
        round_duration_changed = (
            self.pk is None or self.round_duration != self.initial_round_duration
        )
        start_date_changed = (
            self.pk is None or self.start_date != self.initial_start_date
        )
        is_completed_changed = (
            self.pk is None or self.is_completed != self.initial_is_completed
        )

        if self.is_completed and self.registration_open:
            self.registration_open = False
        super(Season, self).save(*args, **kwargs)

        if rounds_changed or round_duration_changed or start_date_changed:
            date = self.start_date
            for round_num in range(1, self.rounds + 1):
                next_date = date + self.round_duration if date is not None else None
                Round.objects.update_or_create(
                    season=self,
                    number=round_num,
                    defaults={"start_date": date, "end_date": next_date},
                )
                date = next_date

        if new_obj:
            # Create a default set of prizes. This may need to be modified in the future
            SeasonPrize.objects.create(season=self, rank=1)
            SeasonPrize.objects.create(season=self, rank=2)
            SeasonPrize.objects.create(season=self, rank=3)
            if self.league.competitor_type != "team":
                SeasonPrize.objects.create(season=self, max_rating=1600, rank=1)

        if is_completed_changed and self.is_completed:
            # Remove out of date prizes
            SeasonPrizeWinner.objects.filter(season_prize__season=self).delete()
            # Award prizes
            if self.league.is_team_league():
                team_scores = sorted(
                    TeamScore.objects.filter(team__season=self)
                    .select_related("team")
                    .nocache(),
                    reverse=True,
                )
                for prize in self.seasonprize_set.filter(max_rating=None):
                    if prize.rank <= len(team_scores):
                        # Award a prize to each team member
                        for member in team_scores[
                            prize.rank - 1
                        ].team.teammember_set.all():
                            SeasonPrizeWinner.objects.create(
                                season_prize=prize, player=member.player
                            )
            else:
                player_scores = sorted(
                    LonePlayerScore.objects.filter(season_player__season=self)
                    .select_related("season_player__player")
                    .nocache(),
                    key=lambda s: s.final_standings_sort_key(),
                    reverse=True,
                )
                for prize in self.seasonprize_set.all():
                    eligible_players = [
                        s.season_player.player
                        for s in player_scores
                        if prize.max_rating is None
                        or (
                            s.season_player.seed_rating is not None
                            and s.season_player.seed_rating < prize.max_rating
                        )
                    ]
                    if prize.rank <= len(eligible_players):
                        SeasonPrizeWinner.objects.create(
                            season_prize=prize, player=eligible_players[prize.rank - 1]
                        )

    def calculate_scores(self):
        if self.league.is_team_league():
            self._calculate_team_scores()
        else:
            self._calculate_lone_scores()

    def _calculate_team_scores(self):
        from heltour.tournament.db_to_structure import season_to_tournament_structure

        # Check if we have any completed rounds
        if not self.round_set.filter(is_completed=True).exists():
            # No completed rounds - reset all scores
            team_scores = TeamScore.objects.filter(team__season=self)
            for score in team_scores:
                score.playoff_score = 0
                score.match_count = 0
                score.match_points = 0
                score.game_points = 0
                score.head_to_head = 0
                score.games_won = 0
                score.sb_score = 0
                score.buchholz = 0
                score.save()
            return

        # Convert to tournament structure and calculate results
        tournament = season_to_tournament_structure(self)
        results = tournament.calculate_results()

        # Get configured tiebreaks
        tiebreak_order = self.league.get_team_tiebreaks()

        # Calculate all tiebreaks
        tiebreak_results = tiebreaks.calculate_all_tiebreaks(results, tiebreak_order)

        # Update team scores with calculated values
        team_scores = TeamScore.objects.filter(team__season=self)
        for score in team_scores:
            if score.team_id in results:
                result = results[score.team_id]
                score.match_points = result.match_points
                score.game_points = result.game_points

                # Count games won from match results
                score.games_won = sum(mr.games_won for mr in result.match_results)

                # Count matches (excluding byes)
                score.match_count = sum(
                    1 for mr in result.match_results if not mr.is_bye
                )

                # TODO: Handle playoff_score - need to determine if we're in playoffs
                score.playoff_score = 0

                # Set tiebreak values
                tiebreak_values = tiebreak_results.get(score.team_id, {})
                # Use any of the Extended Sonneborn-Berger variants if configured,
                # otherwise fall back to regular Sonneborn-Berger
                score.sb_score = (
                    tiebreak_values.get("eggsb", 0)
                    or tiebreak_values.get("emmsb", 0)
                    or tiebreak_values.get("emgsb", 0)
                    or tiebreak_values.get("egmsb", 0)
                    or tiebreak_values.get("sonneborn_berger", 0)
                )
                score.buchholz = tiebreak_values.get("buchholz", 0)
                score.head_to_head = tiebreak_values.get("head_to_head", 0)
            else:
                # Team has no results (no games played)
                score.playoff_score = 0
                score.match_count = 0
                score.match_points = 0
                score.game_points = 0
                score.games_won = 0
                score.sb_score = 0
                score.buchholz = 0
                score.head_to_head = 0

            score.save()

    def _calculate_lone_scores(self):
        from heltour.tournament.db_to_structure import season_to_tournament_structure

        season_players = (
            SeasonPlayer.objects.filter(season=self)
            .select_related("loneplayerscore")
            .nocache()
        )
        player_scores = [sp.get_loneplayerscore() for sp in season_players]

        completed_rounds = list(
            self.round_set.filter(is_completed=True).order_by("number")
        )
        if not completed_rounds:
            for score in player_scores:
                score.points = 0
                score.head_to_head = 0
                score.buchholz_cut1 = 0
                score.buchholz = 0
                score.games_won = 0
                score.games_with_black = 0
                score.sonneborn_berger = 0
                score.perf_rating = None
                score.save()
            return

        # --- Points and perf rating via legacy accumulation ---
        seed_rating_dict = {sp.player_id: sp.seed_rating for sp in season_players}
        score_dict = {}
        last_round = None
        for round_ in completed_rounds:
            pairings = round_.loneplayerpairing_set.all().nocache()
            byes = PlayerBye.objects.filter(round=round_)
            for sp in season_players:
                white_pairing = find(pairings, white_id=sp.player_id)
                black_pairing = find(pairings, black_id=sp.player_id)
                bye = find(byes, player_id=sp.player_id)

                def increment_score(round_opponent, round_score, round_played):
                    total, _mm, _cumul, perf, _, _ = (
                        score_dict[(sp.player_id, last_round.number)]
                        if last_round is not None
                        else (0, 0, 0, PerfRatingCalc(), None, False)
                    )
                    total += round_score
                    if round_played:
                        opp_rating = seed_rating_dict.get(round_opponent, None)
                        if opp_rating is not None:
                            perf.add_game(round_score, opp_rating)
                    score_dict[(sp.player_id, round_.number)] = _LoneScoreState(
                        total, 0, 0, perf, round_opponent, round_played
                    )

                if white_pairing is not None:
                    increment_score(
                        white_pairing.black_id,
                        white_pairing.white_score() or 0,
                        white_pairing.game_played(),
                    )
                elif black_pairing is not None:
                    increment_score(
                        black_pairing.white_id,
                        black_pairing.black_score() or 0,
                        black_pairing.game_played(),
                    )
                elif bye is not None:
                    increment_score(None, bye.score(), False)
                else:
                    increment_score(None, 0, False)
            last_round = round_

        # --- Tiebreaks via tournament_core ---
        tournament = season_to_tournament_structure(self)
        results = tournament.calculate_results()

        tiebreak_order = self.league.get_lone_tiebreaks()
        core_tiebreaks = [tb for tb in tiebreak_order if tb != "games_with_black"]
        tiebreak_results = tiebreaks.calculate_all_tiebreaks(
            results, core_tiebreaks, use_game_points=True
        )

        # --- Games with black: count from DB pairings ---
        games_with_black_map = _count_games_with_black(completed_rounds)

        # --- Write scores ---
        for score in player_scores:
            player_id = score.season_player.player_id
            score_state = score_dict.get((player_id, last_round.number))
            score.points = score_state.total if score_state else 0
            score.perf_rating = score_state.perf.calculate() if score_state else None

            tb_vals = tiebreak_results.get(player_id, {})
            score.head_to_head = tb_vals.get("head_to_head", 0)
            score.buchholz_cut1 = tb_vals.get("buchholz_cut1", 0)
            score.buchholz = tb_vals.get("buchholz", 0)
            score.games_won = tb_vals.get("games_won", 0)
            score.sonneborn_berger = tb_vals.get("sonneborn_berger", 0)
            score.games_with_black = games_with_black_map.get(player_id, 0)
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
            raise Exception("Tried to get board list but season.boards is None")
        return [n for n in range(1, self.boards + 1)]

    def alternates_manager_enabled(self):
        if not hasattr(self.league, "alternatesmanagersetting"):
            return False
        return self.league.alternatesmanagersetting.is_active

    def alternates_manager_setting(self):
        if not hasattr(self.league, "alternatesmanagersetting"):
            return None
        return self.league.alternatesmanagersetting

    def section_list(self):
        if not hasattr(self, "section"):
            return [self]
        return Season.objects.filter(
            section__section_group_id=self.section.section_group_id
        ).order_by("section__order")

    def section_group_name(self):
        if not hasattr(self, "section"):
            return self.name
        return self.section.section_group.name

    def get_broadcast_id(self, first_board: int = 1) -> str:
        if self.create_broadcast:
            bc = Broadcast.objects.filter(season=self, first_board=first_board)
            if bc.exists():
                return bc[0].lichess_id
        return ""

    def is_player_scheduled_league(self) -> bool:
        return self.league.is_player_scheduled_league()

    @classmethod
    def get_registration_season(cls, league, season=None):
        if season is not None and season.registration_open:
            return season
        else:
            return (
                cls.objects.filter(league=league, registration_open=True)
                .order_by("-start_date")
                .first()
            )

    @property
    def pairings(self):
        return (
            PlayerPairing.objects.filter(
                teamplayerpairing__team_pairing__round__season=self
            )
            | PlayerPairing.objects.filter(loneplayerpairing__round__season=self)
        ).nocache()

    def __str__(self):
        return self.name


_TeamScoreState = namedtuple(
    "_TeamScoreState",
    "playoff_score, match_count, match_points, game_points, games_won, round_match_points, round_points, round_opponent, round_opponent_points",
)
_LoneScoreState = namedtuple(
    "_LoneScoreState", "total, mm_total, cumul, perf, round_opponent, round_played"
)


def _count_games_with_black(completed_rounds):
    """Count played games where each player had the black pieces.

    Accounts for ``colors_reversed`` on ``LonePlayerPairing``.
    Returns a dict mapping player_id → count.
    """
    counts: dict[int, int] = {}
    for round_ in completed_rounds:
        for pairing in round_.loneplayerpairing_set.select_related(
            "white", "black"
        ).all():
            if not pairing.game_played():
                continue
            if pairing.colors_reversed:
                if pairing.white_id:
                    counts[pairing.white_id] = counts.get(pairing.white_id, 0) + 1
            else:
                if pairing.black_id:
                    counts[pairing.black_id] = counts.get(pairing.black_id, 0) + 1
    return counts


# From https://www.fide.com/component/handbook/?id=174&view=article
# Used for performance rating calculations
fide_dp_lookup = [
    -800,
    -677,
    -589,
    -538,
    -501,
    -470,
    -444,
    -422,
    -401,
    -383,
    -366,
    -351,
    -336,
    -322,
    -309,
    -296,
    -284,
    -273,
    -262,
    -251,
    -240,
    -230,
    -220,
    -211,
    -202,
    -193,
    -184,
    -175,
    -166,
    -158,
    -149,
    -141,
    -133,
    -125,
    -117,
    -110,
    -102,
    -95,
    -87,
    -80,
    -72,
    -65,
    -57,
    -50,
    -43,
    -36,
    -29,
    -21,
    -14,
    -7,
    0,
    7,
    14,
    21,
    29,
    36,
    43,
    50,
    57,
    65,
    72,
    80,
    87,
    95,
    102,
    110,
    117,
    125,
    133,
    141,
    149,
    158,
    166,
    175,
    184,
    193,
    202,
    211,
    220,
    230,
    240,
    251,
    262,
    273,
    284,
    296,
    309,
    322,
    336,
    351,
    366,
    383,
    401,
    422,
    444,
    470,
    501,
    538,
    589,
    677,
    800,
]


def get_fide_dp(score, total):
    # Turn the score into a number from 0-100 (0 = 0%, 100 = 100%)
    lookup_index = max(min(int(round(100.0 * score / total)), 100), 0)
    # Use that number to get a rating difference from the FIDE lookup table
    return fide_dp_lookup[lookup_index]


class PerfRatingCalc:
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
        average_opp_rating = int(
            round(sum(self._opponent_ratings) / float(self._game_count))
        )
        dp = get_fide_dp(self._score, self._game_count)
        return average_opp_rating + dp

    def debug(self):
        return "%.1f / %d [%s]" % (
            self._score,
            self._game_count,
            ", ".join((str(r) for r in self._opponent_ratings)),
        )


# -------------------------------------------------------------------------------
class Round(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    number = models.PositiveIntegerField(verbose_name="round number")
    start_date = models.DateTimeField(blank=True, null=True)
    end_date = models.DateTimeField(blank=True, null=True)
    bulk_id = models.SlugField(default="", null=True, blank=True)

    publish_pairings = models.BooleanField(default=False)
    is_completed = models.BooleanField(default=False)

    # Knockout-specific fields
    knockout_stage = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        choices=KNOCKOUT_STAGE_OPTIONS,
        help_text="Knockout tournament stage name",
    )

    # For multi-match knockouts using multiple rounds approach
    is_knockout_multi_round = models.BooleanField(
        default=False,
        help_text="True if this round is part of a multi-game knockout match",
    )
    knockout_multi_round_group = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Identifier grouping multiple rounds that form one knockout match",
    )

    class Meta:
        permissions = (("generate_pairings", "Can generate and review pairings"),)
        ordering = ["is_completed", "-start_date"]

    def __init__(self, *args, **kwargs):
        super(Round, self).__init__(*args, **kwargs)
        self.initial_is_completed = self.is_completed
        self.initial_publish_pairings = self.publish_pairings

    def save(self, *args, **kwargs):
        is_completed_changed = (
            self.pk is None
            and self.is_completed
            or self.is_completed != self.initial_is_completed
        )
        publish_pairings_changed = (
            self.pk is None
            and self.publish_pairings
            or self.publish_pairings != self.initial_publish_pairings
        )
        super(Round, self).save(*args, **kwargs)
        if is_completed_changed:
            self.season.calculate_scores()
        if publish_pairings_changed and self.publish_pairings and not self.is_completed:
            signals.do_pairings_published.send(Round, round_id=self.pk)

    @property
    def pairings(self):
        return (
            PlayerPairing.objects.filter(teamplayerpairing__team_pairing__round=self)
            | PlayerPairing.objects.filter(loneplayerpairing__round=self)
        ).nocache()

    def pairing_for(self, player):
        pairings = self.pairings
        return (pairings.filter(white=player) | pairings.filter(black=player)).first()

    def get_league(self):
        return self.season.league

    def is_team_league(self):
        return self.season.league.is_team_league()

    def get_broadcast_id(self, first_board: int = 1) -> str:
        return self.season.get_broadcast_id(first_board=first_board)

    def get_broadcast_round_id(self, first_board: int = 1) -> str:
        if not self.season.get_broadcast_id():
            return ""
        bc = Broadcast.objects.get(season=self.season, first_board=first_board)
        bcr = BroadcastRound.objects.filter(broadcast=bc, round_id=self)
        if bcr.exists():
            return bcr[0].lichess_id
        else:
            return ""

    def is_player_scheduled_league(self) -> bool:
        return self.get_league().is_player_scheduled_league()

    def get_board_update_deadline(self):
        """Get the deadline for board updates for this round"""
        if not self.start_date:
            return None

        try:
            league_setting = self.season.league.leaguesetting
            deadline_minutes = league_setting.board_update_deadline_minutes
        except LeagueSetting.DoesNotExist:
            deadline_minutes = 15  # Default fallback

        return self.start_date - timedelta(minutes=deadline_minutes)

    def is_board_update_allowed(self):
        """Check if board updates are allowed for this round"""
        deadline = self.get_board_update_deadline()
        if not deadline:
            return True  # No start date means no restrictions

        return timezone.now() < deadline

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
    name = models.CharField(max_length=255, verbose_name="section name")
    order = models.PositiveIntegerField()
    min_rating = models.PositiveIntegerField(blank=True, null=True)
    max_rating = models.PositiveIntegerField(blank=True, null=True)

    def clean(self):
        if (
            self.season
            and self.section_group
            and self.season.league_id != self.section_group.league_id
        ):
            raise ValidationError("Season and section group leagues must match")

    def is_eligible(self, player):
        rating = player.rating_for(self.season.league)
        if self.min_rating is not None and (rating is None or rating < self.min_rating):
            return False
        if self.max_rating is not None and (
            rating is None or rating >= self.max_rating
        ):
            return False
        return True

    def __str__(self):
        return "%s - %s" % (self.name, self.section_group.name)


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

    def expire(self):
        self.expires = timezone.now() + timedelta(days=-1)
        self.save()

    def is_valid(self):
        return self.access_token is not None and not self.is_expired()

    def __str__(self):
        return self.account_username


username_validator = RegexValidator(r"^[\w-]+$")

ACCOUNT_STATUS_OPTIONS = (
    ("normal", "Normal"),
    ("tos_violation", "ToS Violation"),
    ("closed", "Closed"),
)

GENDER_CHOICES = (
    ("male", "Male"),
    ("female", "Female"),
    ("non-binary", "Non-binary"),
    ("not-represented", "My gender is not represented"),
    ("prefer-not-disclose", "Prefer not to disclose"),
)


# -------------------------------------------------------------------------------
class Player(_BaseModel):
    lichess_username = models.CharField(
        max_length=255, validators=[username_validator], unique=True
    )
    rating = models.PositiveIntegerField(blank=True, null=True)
    games_played = models.PositiveIntegerField(blank=True, null=True)
    email = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    slack_user_id = models.CharField(max_length=255, blank=True)
    timezone_offset = models.DurationField(blank=True, null=True)
    account_status = models.CharField(
        default="normal", max_length=31, choices=ACCOUNT_STATUS_OPTIONS
    )
    oauth_token = models.ForeignKey(OauthToken, null=True, on_delete=models.CASCADE)

    profile = JSONField(blank=True, null=True)

    fide_id = models.CharField(max_length=20, blank=True)
    fide_profile = JSONField(blank=True, null=True)

    gender = models.CharField(max_length=50, blank=True, choices=GENDER_CHOICES)

    date_first_agreed_to_tos = models.DateTimeField(blank=True, null=True)
    date_last_agreed_to_tos = models.DateTimeField(blank=True, null=True)

    def player_rating_display(self, league=None):
        return self.rating_for(league)

    @property
    def pairings(self):
        return (self.pairings_as_white.all() | self.pairings_as_black.all()).nocache()

    class Meta:
        ordering = ["lichess_username"]
        permissions = (
            ("change_player_details", "Can change player details"),
            ("invite_to_slack", "Can invite to slack"),
            ("link_slack", "Can manually link slack accounts"),
            ("dox", "Can see player emails"),
        )

    def __init__(self, *args, **kwargs):
        super(Player, self).__init__(*args, **kwargs)
        self.initial_account_status = self.account_status
        self.initial_rating = self.rating

    def save(self, *args, **kwargs):
        account_status_changed = (
            self.pk and self.account_status != self.initial_account_status
        )

        # Sync rating changes to profile's classical rating
        rating_changed = self.pk and self.rating != self.initial_rating
        if rating_changed and self.rating is not None and self.profile is not None:
            if "perfs" not in self.profile:
                self.profile["perfs"] = {}
            if "classical" not in self.profile["perfs"]:
                self.profile["perfs"]["classical"] = {}
            self.profile["perfs"]["classical"]["rating"] = self.rating

        super(Player, self).save(*args, **kwargs)
        if account_status_changed:
            signals.player_account_status_changed.send(
                Player,
                instance=self,
                old_value=self.initial_account_status,
                new_value=self.account_status,
            )

    def update_profile(self, user_meta):
        classical = user_meta.get("perfs", {}).get("classical")
        if classical is not None:
            self.rating = classical["rating"]
            self.games_played = classical["games"]
        is_closed = user_meta.get("disabled", False)
        is_tosViolation = user_meta.get("tosViolation", False)
        self.account_status = (
            "closed" if is_closed else "tos_violation" if is_tosViolation else "normal"
        )

        # profile is used to get rating data which should not be updated anymore once an account is closed.
        if not is_closed:
            self.profile = user_meta
        self.save()

    def update_fide_profile(self, fide_meta):
        self.fide_profile = fide_meta
        if not self.gender:
            fide_gender = (fide_meta or {}).get("gender")
            if fide_gender == "M":
                self.gender = "male"
            elif fide_gender == "F":
                self.gender = "female"
        self.save()

    def profile_update_after(self) -> datetime:
        # lichess gives us "seenAt" in miliseconds as the last time the user was online
        # thus, the profile was last updated *after* this seenAt.
        seenAt = (self.profile or {}).get("seenAt")
        if seenAt is not None:
            return datetime.utcfromtimestamp(seenAt / 1000)
        return None

    @classmethod
    def get_or_create(cls, lichess_username):
        player, _ = Player.objects.get_or_create(
            lichess_username__iexact=lichess_username,
            defaults={"lichess_username": lichess_username},
        )
        return player

    @classmethod
    def link_slack_account(cls, lichess_username, slack_user_id):
        player = Player.get_or_create(lichess_username)
        if player.slack_user_id == slack_user_id:
            # No change needed
            return False
        with reversion.create_revision():
            reversion.set_comment("Link slack account")
            player.slack_user_id = slack_user_id
            player.save()
            signals.slack_account_linked.send(
                sender=cls,
                lichess_username=lichess_username,
                slack_user_id=slack_user_id,
            )
            return True

    def is_available_for(self, round_):
        return not PlayerAvailability.objects.filter(
            round=round_, player=self, is_available=False
        ).exists()

    def _is_fide_rating_type(self, league):
        return bool(league) and is_fide_rating_type(league.rating_type)

    def _fide_rating_key(self, league):
        if league.rating_type == "fide":
            profile = self.fide_profile or {}
            for key in FIDE_RATING_FALLBACK_KEYS:
                if profile.get(key) is not None:
                    return key
            return FIDE_RATING_FALLBACK_KEYS[0]
        return league.rating_type.removeprefix("fide_")

    def rating_for(self, league):
        if self._is_fide_rating_type(league):
            return (self.fide_profile or {}).get(
                self._fide_rating_key(league), FIDE_RATING_DEFAULT
            )
        if league:
            if self.profile is None:
                return 0
            return (
                self.profile.get("perfs", {})
                .get(league.rating_type, {})
                .get("rating", 0)
            )
        return self.rating

    def games_played_for(self, league):
        if self._is_fide_rating_type(league):
            return 0
        if league:
            if self.profile is None:
                return None
            return (
                self.profile.get("perfs", {}).get(league.rating_type, {}).get("games")
            )

        return self.games_played  # classical

    def provisional_for(self, league):
        if self._is_fide_rating_type(league):
            return False
        if self.profile is None:
            return True
        perf = self.profile.get("perfs", {}).get(league.rating_type)
        if perf is None:
            return True
        return perf.get("prov", False)

    @property
    def timezone_str(self):
        if self.timezone_offset is None:
            return "?"
        seconds = self.timezone_offset.total_seconds()
        sign = "-" if seconds < 0 else "+"
        hours = abs(seconds) / 3600
        minutes = (abs(seconds) % 3600) / 60
        return "UTC%s%02d:%02d" % (sign, hours, minutes)

    def get_season_prizes(self, league):
        return SeasonPrize.objects.filter(
            season__league=league, seasonprizewinner__player=self
        ).order_by("rank", "-season")

    def agreed_to_tos(self):
        now = timezone.now()
        # Update
        me = Player.objects.filter(pk=self.pk)
        me.update(date_last_agreed_to_tos=now)
        me.filter(date_first_agreed_to_tos__isnull=True).update(
            date_first_agreed_to_tos=now
        )

    def get_access_token(self):
        if self.oauth_token is None:
            return None
        return self.oauth_token.access_token

    def token_valid(self):
        if self.oauth_token is None:
            return False
        return self.oauth_token.is_valid()

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
    zen_mode = models.BooleanField(default=False)


# -------------------------------------------------------------------------------
class LeagueModerator(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    is_active = models.BooleanField(default=True)
    send_contact_emails = models.BooleanField(default=True)

    class Meta:
        unique_together = ("league", "player")

    def __str__(self):
        return "%s - %s" % (self.league, self.player.lichess_username)


ROUND_CHANGE_OPTIONS = (
    ("register", "Register"),
    ("withdraw", "Withdraw"),
    ("half-point-bye", "Half-Point Bye"),
)


# -------------------------------------------------------------------------------
class PlayerLateRegistration(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    retroactive_byes = models.PositiveIntegerField(default=0)
    late_join_points = ScoreField(default=0)

    class Meta:
        unique_together = ("round", "player")

    def perform_registration(self):
        with transaction.atomic():
            # Set the SeasonPlayer as active
            sp, _ = SeasonPlayer.objects.get_or_create(
                season=self.round.season, player=self.player
            )
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
                    white=self.player
                ) | round_.loneplayerpairing_set.filter(black=self.player)
                byes = round_.playerbye_set.filter(player=self.player)
                if pairings.count() == 0 and byes.count() == 0:
                    PlayerBye.objects.create(
                        round=round_, player=self.player, type="half-point-bye"
                    )

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
            raise ValidationError(
                "Player late registrations can only be created for lone leagues"
            )

    def __str__(self):
        return "%s - %s" % (self.round, self.player)


# -------------------------------------------------------------------------------
class PlayerWithdrawal(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("round", "player")

    def perform_withdrawal(self):
        with transaction.atomic():
            # Set the SeasonPlayer as inactive
            sp, _ = SeasonPlayer.objects.get_or_create(
                season=self.round.season, player=self.player
            )
            sp.is_active = False
            sp.save()

            # Delete pairings and give opponents byes
            for pairing in self.round.loneplayerpairing_set.filter(white=self.player):
                PlayerBye.objects.create(
                    round=self.round,
                    player=pairing.black,
                    type="full-point-pairing-bye",
                )
                pairing.delete()
            for pairing in self.round.loneplayerpairing_set.filter(black=self.player):
                PlayerBye.objects.create(
                    round=self.round,
                    player=pairing.white,
                    type="full-point-pairing-bye",
                )
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
            raise ValidationError(
                "Player withdrawals can only be created for lone leagues"
            )

    def __str__(self):
        return "%s - %s" % (self.round, self.player)


BYE_TYPE_OPTIONS = (
    ("full-point-pairing-bye", "Full-Point Bye (Pairing)"),
    ("full-point-bye", "Full-Point Bye"),
    ("half-point-bye", "Half-Point Bye"),
    ("zero-point-bye", "Zero-Point Bye"),
)


# -------------------------------------------------------------------------------
class PlayerBye(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=31, choices=BYE_TYPE_OPTIONS)
    player_rank = models.PositiveIntegerField(blank=True, null=True)
    player_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = ("round", "player")

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
        if rank_dict is None:
            rank_dict = lone_player_pairing_rank_dict(self.round.season)
        self.player_rank = rank_dict.get(self.player_id, None)

    def score(self):
        if self.type == "full-point-bye" or self.type == "full-point-pairing-bye":
            return 1
        elif self.type == "half-point-bye":
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
        if (
            round_changed or player_changed or type_changed
        ) and self.round.is_completed:
            self.round.season.calculate_scores()

    def delete(self, *args, **kwargs):
        round_ = self.round
        super(PlayerBye, self).delete(*args, **kwargs)
        if round_.is_completed:
            round_.season.calculate_scores()

    def clean(self):
        if self.round_id and self.round.season.league.is_team_league():
            raise ValidationError("Player byes can only be created for lone leagues")


# -------------------------------------------------------------------------------
class Team(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    number = models.PositiveIntegerField(verbose_name="team number")
    name = models.CharField(max_length=255, verbose_name="team name")
    slack_channel = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)

    seed_rating = models.PositiveIntegerField(blank=True, null=True)

    # Captain-provided team information
    company_name = models.CharField(max_length=255, verbose_name="Organisation name")
    company_address = models.TextField(
        blank=True, verbose_name="Physical address"
    )
    team_contact_email = models.EmailField(
        blank=True, verbose_name="Team contact email"
    )
    team_contact_number = PhoneNumberField(
        blank=True, verbose_name="Team contact number"
    )

    class Meta:
        unique_together = (("season", "number"), ("season", "name"))
        ordering = ("season__is_completed", "-season__start_date")

    def get_teamscore(self):
        try:
            return self.teamscore
        except TeamScore.DoesNotExist:
            return TeamScore.objects.create(team=self)

    def boards(self):
        team_members = self.teammember_set.all()
        return [
            (n, find(team_members, board_number=n))
            for n in Season.objects.get(pk=self.season_id).board_number_list()
        ]

    def average_rating(self):
        n = 0
        total = 0.0
        for _, board in self.boards():
            if board is not None:
                rating = board.player.rating_for(self.season.league)
                if rating is not None:
                    n += 1
                    total += rating
        return total / n if n > 0 else None

    def get_mean(self):
        return self.average_rating()

    def captain(self):
        return self.teammember_set.filter(is_captain=True).first()

    def get_teampairing(self, round_):
        return (
            round_.teampairing_set.filter(white_team=self)
            | round_.teampairing_set.filter(black_team=self)
        ).first()

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

    def get_upcoming_round(self):
        """Get the next upcoming round for this team (including currently active rounds)"""
        return (
            Round.objects.filter(
                season=self.season, is_completed=False, start_date__isnull=False
            )
            .order_by("start_date")
            .first()
        )

    @property
    def open_board_numbers(self):
        """Get list of board numbers without assigned players"""
        assigned_boards = set(
            self.teammember_set.values_list("board_number", flat=True)
        )
        return [n for n in range(1, self.season.boards + 1) if n not in assigned_boards]

    def __str__(self):
        return "%s - %s" % (self.season, self.name)


BOARD_NUMBER_OPTIONS = (
    (1, "1"),
    (2, "2"),
    (3, "3"),
    (4, "4"),
    (5, "5"),
    (6, "6"),
    (7, "7"),
    (8, "8"),
    (9, "9"),
    (10, "10"),
    (11, "11"),
    (12, "12"),
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
        unique_together = ("team", "board_number")

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
        if (
            self.team_id
            and self.player_id
            and not SeasonPlayer.objects.filter(
                season=self.team.season, player=self.player
            ).exists()
        ):
            raise ValidationError("Team member must be a player in the season")

    def __str__(self):
        return "%s%s" % (
            self.player,
            " (C)" if self.is_captain else " (V)" if self.is_vice_captain else "",
        )


# -------------------------------------------------------------------------------
class TeamBye(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    type = models.CharField(max_length=31, choices=BYE_TYPE_OPTIONS)

    class Meta:
        unique_together = ("round", "team")

    def score(self):
        if self.type == "full-point-pairing-bye":
            return 1
        else:
            return 0

    def __str__(self):
        return "%s - %s" % (self.round, self.team)


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
    buchholz = ScoreField(default=0)

    def match_points_display(self):
        return str(self.match_points)

    def game_points_display(self):
        return "%g" % self.game_points

    def head_to_head_display(self):
        return str(self.head_to_head)

    def games_won_display(self):
        return str(self.games_won)

    def sb_score_display(self):
        return "%g" % self.sb_score

    def buchholz_display(self):
        return "%g" % self.buchholz

    def get_tiebreak_display(self, tiebreak_name):
        """Get display value for a specific tiebreak"""
        display_methods = {
            "game_points": self.game_points_display,
            "head_to_head": self.head_to_head_display,
            "games_won": self.games_won_display,
            "sonneborn_berger": self.sb_score_display,
            "buchholz": self.buchholz_display,
            # All extended SB variants use the same sb_score field
            "eggsb": self.sb_score_display,
            "emmsb": self.sb_score_display,
            "emgsb": self.sb_score_display,
            "egmsb": self.sb_score_display,
        }
        method = display_methods.get(tiebreak_name)
        return method() if method else ""

    def pairing_sort_key(self):
        # Get the league's configured tiebreaks
        league = self.team.season.league
        tiebreaks = league.get_team_tiebreaks()

        # Build the sort key based on configured tiebreaks
        sort_key = [
            self.playoff_score,
            self.match_points,
        ]  # Always sort by playoff score and match points first

        tiebreak_values = {
            "game_points": self.game_points,
            "head_to_head": self.head_to_head,
            "games_won": self.games_won,
            "sonneborn_berger": self.sb_score,
            "eggsb": self.sb_score,  # All SB variants use the same field
            "emmsb": self.sb_score,
            "emgsb": self.sb_score,
            "egmsb": self.sb_score,
            "buchholz": self.buchholz,
        }

        # Add configured tiebreaks in order
        for tiebreak in tiebreaks:
            if tiebreak in tiebreak_values:
                sort_key.append(tiebreak_values[tiebreak])

        # Always use seed rating as final tiebreak
        sort_key.append(self.team.seed_rating)

        return tuple(sort_key)

    def intermediate_standings_sort_key(self):
        """Sort key for intermediate standings (same as pairing sort key for teams)."""
        return self.pairing_sort_key()

    def final_standings_sort_key(self):
        """Sort key for final standings (same as pairing sort key for teams)."""
        return self.pairing_sort_key()

    def round_scores(self):
        white_pairings = self.team.pairings_as_white.all()
        black_pairings = self.team.pairings_as_black.all()
        team_byes = self.team.teambye_set.all()
        for round_ in Round.objects.filter(season_id=self.team.season_id).order_by(
            "number"
        ):
            if round_ is None or not round_.is_completed:
                yield None, None, None, False
                continue
            points = None
            opp_points = None
            is_bye = False

            # Check for team bye first
            team_bye = find(team_byes, round_id=round_.id)
            if team_bye is not None:
                points = team_bye.score()
                opp_points = None
                is_bye = True
            else:
                # Check for regular pairings
                white_pairing = find(white_pairings, round_id=round_.id)
                black_pairing = find(black_pairings, round_id=round_.id)
                if white_pairing is not None:
                    points = white_pairing.white_points
                    opp_points = white_pairing.black_points
                if black_pairing is not None:
                    points = black_pairing.black_points
                    opp_points = black_pairing.white_points

            yield points, opp_points, round_.number, is_bye

    def cross_scores(self, sorted_teams=None):
        if sorted_teams is None:
            sorted_teams = Team.objects.filter(season_id=self.team.season_id).order_by(
                "number"
            )
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
        return self.pairing_sort_key() < other.pairing_sort_key()


# -------------------------------------------------------------------------------
class TeamPairing(_BaseModel):
    white_team = models.ForeignKey(
        Team, related_name="pairings_as_white", on_delete=models.CASCADE
    )
    black_team = models.ForeignKey(
        Team, related_name="pairings_as_black", on_delete=models.CASCADE
    )
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    pairing_order = models.PositiveIntegerField()

    white_points = ScoreField(default=0)
    white_wins = models.PositiveIntegerField(default=0)
    black_points = ScoreField(default=0)
    black_wins = models.PositiveIntegerField(default=0)

    # Knockout-specific fields
    manual_tiebreak_value = models.FloatField(
        blank=True,
        null=True,
        help_text="Manual tiebreak value set by arbiter (+ve = white wins, -ve = black wins)",
    )

    # For knockout advancement tracking
    advances_winner_to_round = models.ForeignKey(
        "Round",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="advancement_sources",
        help_text="Round that the winner of this pairing advances to",
    )

    class Meta:
        unique_together = ("white_team", "black_team", "round")

    def __init__(self, *args, **kwargs):
        super(TeamPairing, self).__init__(*args, **kwargs)
        self.initial_white_points = self.white_points
        self.initial_black_points = self.black_points

    def save(self, *args, **kwargs):
        points_changed = (
            self.pk is None
            or self.white_points != self.initial_white_points
            or self.black_points != self.initial_black_points
        )
        super(TeamPairing, self).save(*args, **kwargs)
        if points_changed and self.round.is_completed:
            self.round.season.calculate_scores()

    def clean(self):
        if (
            self.white_team_id
            and self.black_team_id
            and self.white_team.season != self.round.season
            or self.black_team.season != self.round.season
        ):
            raise ValidationError("Round and team seasons must match")

    def refresh_points(self):
        """Refresh team points using the same logic as tournament_core calculations.

        Uses the single source of truth for team pairing score calculation.
        """
        from heltour.tournament.db_to_structure import calculate_team_pairing_scores

        self.white_points, self.black_points, self.white_wins, self.black_wins = (
            calculate_team_pairing_scores(self)
        )

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
    rf"^(https?://)?([a-z]+\.)?{settings.LICHESS_NAME}\.{settings.LICHESS_TOPLEVEL}/([A-Za-z0-9]{{8}})([A-Za-z0-9]{{4}})?([/#\?].*)?$"
)
game_link_validator = RegexValidator(game_link_regex)


def get_gameid_from_gamelink(gamelink):
    if gamelink is None or gamelink == "":
        return None
    match = game_link_regex.match(gamelink)
    if match is None:
        return None
    return match.group(3)


def get_gamelink_from_gameid(gameid):
    return f"{settings.LICHESS_DOMAIN}{gameid}"


def normalize_gamelink(gamelink):
    if gamelink == "":
        return gamelink, True
    gameid = get_gameid_from_gamelink(gamelink)
    if gameid is None:
        return gamelink, False
    return get_gamelink_from_gameid(gameid), True


RESULT_OPTIONS = (
    ("1-0", "1-0"),
    ("1/2-1/2", "\u00bd-\u00bd"),
    ("0-1", "0-1"),
    ("1X-0F", "1X-0F"),
    ("1/2Z-1/2Z", "\u00bdZ-\u00bdZ"),
    ("0F-1X", "0F-1X"),
    ("0F-0F", "0F-0F"),
)

TV_STATE_OPTIONS = (
    ("default", "Default"),
    ("hide", "Hide"),
    ("has_moves", "Has Moves"),
)


# -------------------------------------------------------------------------------
class PlayerPairing(_BaseModel):
    white = models.ForeignKey(
        Player,
        blank=True,
        null=True,
        related_name="pairings_as_white",
        on_delete=models.CASCADE,
    )
    black = models.ForeignKey(
        Player,
        blank=True,
        null=True,
        related_name="pairings_as_black",
        on_delete=models.CASCADE,
    )
    white_rating = models.PositiveIntegerField(blank=True, null=True)
    black_rating = models.PositiveIntegerField(blank=True, null=True)

    result = models.CharField(max_length=16, blank=True, choices=RESULT_OPTIONS)
    game_link = models.URLField(
        max_length=1024, blank=True, validators=[game_link_validator]
    )
    scheduled_time = models.DateTimeField(blank=True, null=True)
    # *_confirmed: whether the player confirmed the scheduled time, so we may start games automatically.
    white_confirmed = models.BooleanField(default=False)
    black_confirmed = models.BooleanField(default=False)
    # whether we added the game to a croadcast
    broadcasted = models.BooleanField(default=False)

    colors_reversed = models.BooleanField(default=False)

    # We do not want to mark players as unresponsive if their opponents got assigned after round start
    date_player_changed = models.DateTimeField(blank=True, null=True)

    tv_state = models.CharField(
        max_length=31, default="default", choices=TV_STATE_OPTIONS
    )

    def __init__(self, *args, **kwargs):
        super(PlayerPairing, self).__init__(*args, **kwargs)
        self.initial_result = "" if self.pk is None else self.result
        self.initial_white_id = None if self.pk is None else self.white_id
        self.initial_black_id = None if self.pk is None else self.black_id
        self.initial_game_link = "" if self.pk is None else self.game_link
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
            return "?"
        if self.white_rating:
            return "%s (%d)" % (self.white.lichess_username, self.white_rating)
        else:
            return self.white

    def get_white_access_token(self):
        return self.white.get_access_token()

    def get_black_access_token(self):
        return self.black.get_access_token()

    def get_white_oauth_token(self):
        return self.white.oauth_token

    def get_black_oauth_token(self):
        return self.black.oauth_token

    def tokens_valid(self):
        return self.white.token_valid() and self.black.token_valid()

    def black_display(self):
        if not self.black:
            return "?"
        if self.black_rating:
            return "%s (%d)" % (self.black.lichess_username, self.black_rating)
        else:
            return self.black

    def white_score(self):
        if self.result == "1-0" or self.result == "1X-0F":
            return 1 if not self.colors_reversed else 0
        elif self.result == "0-1" or self.result == "0F-1X" or self.result == "0F-0F":
            return 0 if not self.colors_reversed else 1
        elif self.result == "1/2-1/2" or self.result == "1/2Z-1/2Z":
            return 0.5
        return None

    def black_score(self):
        if self.result == "0-1" or self.result == "0F-1X":
            return 1 if not self.colors_reversed else 0
        elif self.result == "1-0" or self.result == "1X-0F" or self.result == "0F-0F":
            return 0 if not self.colors_reversed else 1
        elif self.result == "1/2-1/2" or self.result == "1/2Z-1/2Z":
            return 0.5
        return None

    def result_display(self):
        if not self.result:
            return ""
        result = self.result.replace("1/2", "\u00bd")
        if self.colors_reversed:
            result += "*"
        return result

    def game_played(self):
        return self.result in ("1-0", "1/2-1/2", "0-1")

    def game_id(self):
        return get_gameid_from_gamelink(self.game_link)

    def get_round(self):
        if hasattr(self, "teamplayerpairing"):
            return self.teamplayerpairing.team_pairing.round
        if hasattr(self, "loneplayerpairing"):
            return self.loneplayerpairing.round
        return None

    def get_league(self):
        if hasattr(self, "teamplayerpairing"):
            return self.teamplayerpairing.team_pairing.round.get_league()
        if hasattr(self, "loneplayerpairing"):
            return self.loneplayerpairing.round.get_league()
        return None

    def get_player_presence(self, player):
        presence = self.playerpresence_set.filter(player=player).first()
        if not presence:
            presence = PlayerPresence.objects.create(
                pairing=self, player=player, round=self.get_round()
            )
        return presence

    def pairing_changed_after_round_start(self):
        if self.date_player_changed is None:
            return False
        else:
            return self.date_player_changed > self.get_round().start_date

    def __str__(self):
        return "%s - %s" % (self.white_display(), self.black_display())

    def update_available_upon_schedule(self, player_id):
        # set players available if game gets scheduled and they are unavailable,
        # do not set a player with a red card available, though.
        if not SeasonPlayer.objects.filter(
            player__id=player_id, season=self.get_round().season, games_missed__gte=2
        ).exists():
            PlayerAvailability.objects.filter(
                player__id=player_id, round=self.get_round()
            ).update(is_available=True)

    def save(self, *args, **kwargs):
        result_changed = self.result != self.initial_result
        white_changed = self.white_id != self.initial_white_id
        black_changed = self.black_id != self.initial_black_id
        game_link_changed = self.game_link != self.initial_game_link
        scheduled_time_changed = self.scheduled_time != self.initial_scheduled_time

        if game_link_changed:
            self.game_link, _ = normalize_gamelink(self.game_link)
            self.tv_state = "default"
        if white_changed or black_changed or game_link_changed:
            self.white_rating = None
            self.black_rating = None

        # we only want to set date_player_changed if a player was changed after the initial creation of the pairing
        if (white_changed and self.initial_white_id is not None) or (
            black_changed and self.initial_black_id is not None
        ):
            self.date_player_changed = timezone.now()

        # We also want the players to confirm (again) if the scheduled time changes.
        if scheduled_time_changed:
            self.white_confirmed = False
            self.black_confirmed = False

        super(PlayerPairing, self).save(*args, **kwargs)

        if hasattr(self, "teamplayerpairing") and result_changed:
            self.teamplayerpairing.team_pairing.refresh_points()
            self.teamplayerpairing.team_pairing.save()
        if hasattr(self, "loneplayerpairing"):
            lpp = LonePlayerPairing.objects.nocache().get(pk=self.loneplayerpairing.pk)
            if result_changed and lpp.round.is_completed:
                lpp.round.season.calculate_scores()
            # If the players for a PlayerPairing in the current round are edited, then we can update the player ranks
            if (
                (white_changed or black_changed)
                and lpp.round.publish_pairings
                and not lpp.round.is_completed
            ):
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
            result_is_forfeit(self.result) or result_is_forfeit(self.initial_result)
        ):
            signals.pairing_forfeit_changed.send(sender=self.__class__, instance=self)
        # Update scheduled notifications based on the scheduled time
        if scheduled_time_changed:
            league = self.get_round().season.league
            # Calling the save method triggers the logic to recreate notifications
            white_setting = PlayerNotificationSetting.get_or_default(
                player_id=self.white_id, type="before_game_time", league=league
            )
            white_setting.save()
            black_setting = PlayerNotificationSetting.get_or_default(
                player_id=self.black_id, type="before_game_time", league=league
            )
            black_setting.save()
            if white_changed and self.initial_white_id:
                old_white_setting = PlayerNotificationSetting.get_or_default(
                    player_id=self.initial_white_id,
                    type="before_game_time",
                    league=league,
                )
                old_white_setting.save()
            if black_changed and self.initial_black_id:
                old_black_setting = PlayerNotificationSetting.get_or_default(
                    player_id=self.initial_black_id,
                    type="before_game_time",
                    league=league,
                )
                old_black_setting.save()
            self.update_available_upon_schedule(self.white_id)
            self.update_available_upon_schedule(self.black_id)
            signals.notify_players_game_scheduled.send(
                sender=self.__class__, round_=self.get_round(), pairing=self
            )

    def delete(self, *args, **kwargs):
        team_pairing = None
        round_ = None
        if hasattr(self, "teamplayerpairing"):
            team_pairing = self.teamplayerpairing.team_pairing
        if hasattr(self, "loneplayerpairing"):
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
    return result.endswith(("X", "F", "Z"))


# -------------------------------------------------------------------------------
class TeamPlayerPairing(PlayerPairing):
    team_pairing = models.ForeignKey(TeamPairing, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    class Meta:
        unique_together = ("team_pairing", "board_number")

    def white_team(self):
        return (
            self.team_pairing.white_team
            if self.board_number % 2 == 1
            else self.team_pairing.black_team
        )

    def black_team(self):
        return (
            self.team_pairing.black_team
            if self.board_number % 2 == 1
            else self.team_pairing.white_team
        )

    def white_team_player(self):
        return self.white if self.board_number % 2 == 1 else self.black

    def black_team_player(self):
        return self.black if self.board_number % 2 == 1 else self.white

    def white_team_rating(self, league=None):
        return (
            self.white_rating_display(league)
            if self.board_number % 2 == 1
            else self.black_rating_display(league)
        )

    def black_team_rating(self, league=None):
        return (
            self.black_rating_display(league)
            if self.board_number % 2 == 1
            else self.white_rating_display(league)
        )

    def white_team_color(self):
        return "white" if self.board_number % 2 == 1 else "black"

    def black_team_color(self):
        return "black" if self.board_number % 2 == 1 else "white"

    def white_team_score(self):
        return self.white_score() if self.board_number % 2 == 1 else self.black_score()

    def white_team_score_str(self):
        return format_score(self.white_team_score(), self.game_played())

    def black_team_score(self):
        return self.black_score() if self.board_number % 2 == 1 else self.white_score()

    def black_team_score_str(self):
        return format_score(self.black_team_score(), self.game_played())

    def white_team_match_score(self):
        return (
            self.team_pairing.white_points
            if self.board_number % 2 == 1
            else self.team_pairing.black_points
        )

    def black_team_match_score(self):
        return (
            self.team_pairing.black_points
            if self.board_number % 2 == 1
            else self.team_pairing.white_points
        )

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
        if rank_dict is None:
            rank_dict = lone_player_pairing_rank_dict(self.round.season)
        self.white_rank = rank_dict.get(self.white_id, None)
        self.black_rank = rank_dict.get(self.black_id, None)


REGISTRATION_STATUS_OPTIONS = (
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
)

ALTERNATE_PREFERENCE_OPTIONS = (
    ("alternate", "Alternate"),
    ("full_time", "Full Time"),
    ("either", "Either is fine for me."),
)


# -------------------------------------------------------------------------------
class InviteCode(_BaseModel):
    """Invite codes for controlled league registration"""

    league = models.ForeignKey(
        "League", on_delete=models.CASCADE, related_name="invite_codes"
    )
    season = models.ForeignKey(
        "Season", on_delete=models.CASCADE, related_name="invite_codes"
    )
    code = models.CharField(max_length=50, unique=True, db_index=True)
    code_type = models.CharField(
        max_length=20,
        choices=[
            ("captain", "Captain - Creates new team"),
            ("team_member", "Team Member - Joins existing team"),
        ],
        default="captain",
        help_text="Type of registration this code enables",
    )

    # For team member codes
    team = models.ForeignKey(
        "Team",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="invite_codes",
        help_text="Team that members will join (for team_member codes)",
    )

    # Usage tracking
    used_by = models.ForeignKey(
        "Player",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_invite_codes",
    )
    used_at = models.DateTimeField(null=True, blank=True)

    # Creation tracking
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_invite_codes",
    )
    created_by_captain = models.ForeignKey(
        "Player",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="captain_created_invite_codes",
        help_text="Captain who created this invite code",
    )
    notes = models.TextField(
        blank=True, help_text="Internal notes about this invite code"
    )

    class Meta:
        unique_together = [["league", "season", "code"]]
        indexes = [
            models.Index(fields=["league", "season", "used_by"]),
            models.Index(fields=["created_by_captain"]),
        ]

    def __str__(self):
        status = "Used" if self.used_by else "Available"
        type_label = (
            "Captain"
            if self.code_type == "captain"
            else f"Team Member ({self.team.name if self.team else 'No team'})"
        )
        return f"{self.code} - {type_label} - {status}"

    def is_available(self):
        """Check if this code can still be used"""
        return self.used_by is None

    def mark_used(self, player):
        """Mark this code as used by a player"""
        if not self.is_available():
            raise ValidationError("This invite code has already been used")
        self.used_by = player
        self.used_at = timezone.now()
        self.save()

    def save(self, *args, **kwargs):
        # Ensure code is uppercase for consistency
        self.code = self.code.upper()

        # Validate team member codes have a team
        if self.code_type == "team_member" and not self.team:
            raise ValidationError("Team member codes must be associated with a team")

        super().save(*args, **kwargs)

    @classmethod
    def get_by_code(cls, code, league, season):
        """Get an invite code by its code value (case-insensitive)"""
        return cls.objects.filter(
            league=league, season=season, code__iexact=code.strip()
        ).first()

    @classmethod
    def generate_code(cls):
        """Generate a cryptographically secure invite code"""
        # Dictionary words for readability
        words = [
            "CHESS",
            "KNIGHT",
            "BISHOP",
            "QUEEN",
            "KING",
            "ROOK",
            "PAWN",
            "CHECK",
            "MATE",
            "CASTLE",
            "FORK",
            "PIN",
            "SKEWER",
            "GAMBIT",
            "ENDGAME",
            "OPENING",
            "TACTICS",
            "BLITZ",
            "RAPID",
            "BULLET",
        ]

        # Generate: WORD1-WORD2-XXXXXXXX
        import random

        word1 = random.choice(words)
        word2 = random.choice([w for w in words if w != word1])
        suffix = get_random_string(
            8, allowed_chars="ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        )

        return f"{word1}-{word2}-{suffix}"

    @classmethod
    def create_batch(
        cls, league, season, count, created_by=None, code_type="captain", team=None
    ):
        """Create a batch of invite codes"""
        if count < 1 or count > 10000:
            raise ValidationError("Count must be between 1 and 10,000")

        codes_to_create = []
        attempts = 0
        max_attempts = count * 10  # Allow for some collisions

        while len(codes_to_create) < count and attempts < max_attempts:
            attempts += 1
            code = cls.generate_code()

            # Check if code already exists
            if not cls.objects.filter(code=code).exists():
                codes_to_create.append(
                    cls(
                        league=league,
                        season=season,
                        code=code,
                        code_type=code_type,
                        team=team,
                        created_by=created_by,
                        notes=f"Batch created on {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}",
                    )
                )

        if len(codes_to_create) < count:
            raise ValidationError(
                f"Could only generate {len(codes_to_create)} unique codes"
            )

        return cls.objects.bulk_create(codes_to_create)


# -------------------------------------------------------------------------------
class Registration(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    status = models.CharField(
        max_length=255, choices=REGISTRATION_STATUS_OPTIONS, default="pending"
    )
    status_changed_by = models.CharField(blank=True, max_length=255)
    status_changed_date = models.DateTimeField(blank=True, null=True)
    player = models.ForeignKey(to=Player, on_delete=models.CASCADE, null=True)
    email = models.EmailField(max_length=255, blank=True)
    has_played_20_games = models.BooleanField(default=True)
    can_commit = models.BooleanField()
    friends = models.CharField(blank=True, max_length=1023)
    avoid = models.CharField(blank=True, max_length=1023)
    agreed_to_rules = models.BooleanField()
    agreed_to_tos = models.BooleanField()
    alternate_preference = models.CharField(
        blank=True, max_length=255, choices=ALTERNATE_PREFERENCE_OPTIONS
    )
    section_preference = models.ForeignKey(
        Section, on_delete=models.SET_NULL, blank=True, null=True
    )
    weeks_unavailable = models.CharField(blank=True, max_length=255)
    invite_code_used = models.ForeignKey(
        InviteCode,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="registrations",
    )

    validation_status = models.CharField(
        max_length=10,
        choices=ValidationStatus.choices,
        default=ValidationStatus.OK,
        db_index=True,
    )
    validation_issues = models.JSONField(default=list, blank=True)

    # Additional registration information
    fide_id = models.CharField(max_length=20, blank=True, verbose_name="FIDE ID")
    regional_rating = models.CharField(
        max_length=20, blank=True, verbose_name="Regional Rating"
    )
    first_name = models.CharField(max_length=100, blank=True, verbose_name="First Name")
    last_name = models.CharField(max_length=100, blank=True, verbose_name="Family Name")

    gender = models.CharField(
        max_length=50, blank=True, choices=GENDER_CHOICES, verbose_name="Gender"
    )

    date_of_birth = models.DateField(
        blank=True, null=True, verbose_name="Date of birth"
    )
    nationality = CountryField(blank=True)
    corporate_email = models.EmailField(
        blank=True, verbose_name="Corporate email address"
    )
    personal_email = models.EmailField(
        blank=True, verbose_name="Personal email address"
    )
    contact_number = PhoneNumberField(blank=True, verbose_name="Contact number")

    def __str__(self):
        return "%s" % (self.lichess_username)

    def previous_registrations(self):
        return Registration.objects.filter(
            player=self.player, date_created__lt=self.date_created
        )

    def other_seasons(self):
        return SeasonPlayer.objects.filter(player=self.player).exclude(
            season=self.season
        )

    @property
    def lichess_username(self):
        return self.player.lichess_username

    @property
    def rating(self):
        return self.player.rating_for(league=self.season.league)

    PredefinedListResult = namedtuple(
        "PredefinedListResult", ["username_match", "fide_match", "detail"]
    )

    def predefined_list_check(self) -> PredefinedListResult:
        player_map = self.season.parse_predefined_player_list()
        fide_map = self.season.predefined_fide_to_username()
        username = self.lichess_username.lower()
        fide_id = self.fide_id.strip()
        username_match = username in player_map

        if username_match:
            fide_match = fide_id != "" and fide_id == player_map[username]
            if fide_match:
                return self.PredefinedListResult(
                    username_match=True,
                    fide_match=True,
                    detail="Player matches predefined list",
                )
            return self.PredefinedListResult(
                username_match=True,
                fide_match=False,
                detail="Known player, FIDE ID does not match list",
            )

        fide_in_list = fide_id != "" and fide_id in fide_map
        if fide_in_list:
            owner = fide_map[fide_id]
            return self.PredefinedListResult(
                username_match=False,
                fide_match=True,
                detail=f"FIDE ID {fide_id} belongs to {owner} in predefined list",
            )
        return self.PredefinedListResult(
            username_match=False,
            fide_match=False,
            detail="Not in predefined list",
        )

    def _check_has_rating(self) -> list[dict]:
        if self.rating == 0:
            return [
                {
                    "code": "no_rating",
                    "severity": "error",
                    "message": "Player has no rating",
                }
            ]
        return []

    def _check_account_status(self) -> list[dict]:
        if self.player.account_status != "normal":
            return [
                {
                    "code": "account_not_normal",
                    "severity": "error",
                    "message": f"Account status is {self.player.account_status}",
                }
            ]
        return []

    def _check_predefined_list_username(self) -> list[dict]:
        check = self.predefined_list_check()
        if not check.username_match:
            return [
                {
                    "code": "not_in_predefined_list",
                    "severity": "warning",
                    "message": "Username not in predefined list",
                }
            ]
        return []

    def _check_predefined_list_fide_id(self) -> list[dict]:
        fide_id = self.fide_id.strip()
        if not fide_id:
            return [
                {
                    "code": "fide_id_not_in_predefined_list",
                    "severity": "warning",
                    "message": "No FIDE ID provided",
                }
            ]
        fide_map = self.season.predefined_fide_to_username()
        if fide_id not in fide_map:
            return [
                {
                    "code": "fide_id_not_in_predefined_list",
                    "severity": "warning",
                    "message": f"FIDE ID {fide_id} not in predefined list",
                }
            ]
        issues: list[dict] = []
        duplicate_count = (
            Registration.objects.filter(season=self.season, fide_id=fide_id)
            .exclude(pk=self.pk)
            .count()
        )
        if duplicate_count > 0:
            issues.append(
                {
                    "code": "fide_id_duplicate",
                    "severity": "warning",
                    "message": f"FIDE ID {fide_id} is also used by {duplicate_count} other registration(s)",
                }
            )
        return issues

    def _check_predefined_list_pairing(self) -> list[dict]:
        check = self.predefined_list_check()
        if not check.username_match and check.fide_match:
            return [
                {
                    "code": "fide_id_wrong_player",
                    "severity": "error",
                    "message": check.detail,
                }
            ]
        if check.username_match and not check.fide_match:
            return [
                {
                    "code": "predefined_fide_mismatch",
                    "severity": "warning",
                    "message": check.detail,
                }
            ]
        return []

    def _check_not_provisional(self) -> list[dict]:
        if self.player.provisional_for(league=self.season.league):
            return [
                {
                    "code": "provisional_rating",
                    "severity": "warning",
                    "message": "Player has a provisional rating",
                }
            ]
        return []

    def _check_agreed_to_rules(self) -> list[dict]:
        if not self.agreed_to_rules:
            return [
                {
                    "code": "rules_not_agreed",
                    "severity": "warning",
                    "message": "Player has not agreed to rules",
                }
            ]
        return []

    def _check_agreed_to_tos(self) -> list[dict]:
        if not self.agreed_to_tos:
            return [
                {
                    "code": "tos_not_agreed",
                    "severity": "warning",
                    "message": "Player has not agreed to terms of service",
                }
            ]
        return []

    VALIDATION_RULES: ClassVar[
        list[tuple[str, Callable[["Registration"], list[dict]]]]
    ] = [
        ("validate_has_rating", _check_has_rating),
        ("validate_account_status", _check_account_status),
        ("validate_predefined_list_contains_username", _check_predefined_list_username),
        ("validate_predefined_list_contains_fide_id", _check_predefined_list_fide_id),
        ("validate_predefined_list_contains_username_fide_id_together", _check_predefined_list_pairing),
        ("validate_not_provisional", _check_not_provisional),
        ("validate_agreed_to_rules", _check_agreed_to_rules),
        ("validate_agreed_to_tos", _check_agreed_to_tos),
    ]

    def compute_validation(self) -> tuple[ValidationStatus, list[dict]]:
        issues: list[dict] = []
        for season_flag, check_fn in self.VALIDATION_RULES:
            if getattr(self.season, season_flag):
                issues.extend(check_fn(self))

        has_error = any(i["severity"] == "error" for i in issues)
        has_warning = any(i["severity"] == "warning" for i in issues)
        if has_error:
            status = ValidationStatus.ERROR
        elif has_warning:
            status = ValidationStatus.WARNING
        else:
            status = ValidationStatus.OK
        return status, issues

    def refresh_validation(self) -> None:
        self.validation_status, self.validation_issues = self.compute_validation()
        self.save(update_fields=["validation_status", "validation_issues"])

    @property
    def validation_ok(self) -> bool:
        return self.validation_status != ValidationStatus.ERROR

    @property
    def validation_warning(self) -> bool:
        return self.validation_status == ValidationStatus.WARNING

    @classmethod
    def can_register(cls, user, season):
        if not season or not season.registration_open:
            return False
        return not cls.was_rejected(user, season)

    @classmethod
    def was_rejected(cls, user, season):
        reg = cls.get_latest_registration(user, season)
        return reg and reg.status == "rejected"

    @classmethod
    def get_latest_registration(cls, user, season):
        return (
            cls.objects.filter(
                player__lichess_username__iexact=user.username, season=season
            )
            .order_by("-date_created")
            .first()
        )

    @classmethod
    def is_registered(cls, user, season):
        return cls.objects.filter(
            player__lichess_username__iexact=user.username, season=season
        ).exists()


# -------------------------------------------------------------------------------
class SeasonPlayer(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    registration = models.ForeignKey(
        Registration, on_delete=models.SET_NULL, blank=True, null=True
    )
    is_active = models.BooleanField(default=True)

    games_missed = models.PositiveIntegerField(default=0)
    unresponsive = models.BooleanField(default=False)
    seed_rating = models.PositiveIntegerField(blank=True, null=True)
    final_rating = models.PositiveIntegerField(blank=True, null=True)

    class Meta:
        unique_together = ("season", "player")

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
            PlayerAvailability.objects.update_or_create(
                round=r, player=self.player, defaults={"is_available": False}
            )

    def has_scheduled_game_in_round(self, round):
        pairingModel = TeamPlayerPairing.objects.filter(team_pairing__round=round)
        if not self.season.league.is_team_league():
            pairingModel = LonePlayerPairing.objects.filter(round=round)

        return pairingModel.filter(
            (Q(white=self.player) | Q(black=self.player))
            & Q(scheduled_time__isnull=False)  #
        ).exists()

    def player_rating_display(self, league=None):
        if self.final_rating is not None:
            return self.final_rating
        else:
            if league is None:
                league = self.season.league
            return self.player.rating_for(league)

    def save(self, *args, **kwargs):
        unresponsive_changed = (
            self.pk is None or self.unresponsive != self.initial_unresponsive
        )
        player_changed = self.pk is None or self.player_id != self.initial_player_id

        if player_changed:
            self.player_rating = None

        if unresponsive_changed and self.unresponsive and hasattr(self, "alternate"):
            alt = self.alternate
            current_date = timezone.now()
            if (
                alt.priority_date_override is None
                or alt.priority_date_override < current_date
            ):
                alt.priority_date_override = current_date
                alt.save()

        if self.games_missed >= 2 and self.initial_games_missed < 2:
            self._set_unavailable_for_season()

        super(SeasonPlayer, self).save(*args, **kwargs)

    def seed_rating_display(self, league=None):
        if self.seed_rating is not None:
            return self.seed_rating
        else:
            if league is None:
                league = self.season.league
            return self.player.rating_for(league)

    @classmethod
    def withdraw_from_team_season(cls, round, player):
        # We can only set players inactive that are not part of a team.
        if not TeamMember.objects.filter(
            player=player, team__season=round.season
        ).exists():
            cls.objects.filter(season=round.season, player=player).update(
                is_active=False
            )

        sp = SeasonPlayer.objects.get(season=round.season, player=player)
        sp._set_unavailable_for_season(skip_current=True)
        add_system_comment(sp, "player withdrawn: %s" % round)

    @property
    def card_color(self):
        if self.games_missed >= 2:
            return "red"
        elif self.games_missed == 1:
            return "yellow"
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
    # Vestigial — kept for backwards compatibility, no longer populated
    tiebreak1 = ScoreField(default=0)
    tiebreak2 = ScoreField(default=0)
    tiebreak3 = ScoreField(default=0)
    tiebreak4 = ScoreField(default=0)
    # Named tiebreak fields (FIDE-standard)
    head_to_head = ScoreField(default=0)
    buchholz_cut1 = ScoreField(default=0)
    buchholz = ScoreField(default=0)
    games_won = models.PositiveIntegerField(default=0)
    games_with_black = models.PositiveIntegerField(default=0)
    sonneborn_berger = ScoreField(default=0)
    acceleration_group = models.PositiveIntegerField(default=0)

    perf_rating = models.PositiveIntegerField(blank=True, null=True)

    def round_scores(
        self,
        rounds,
        player_number_dict,
        white_pairings_dict,
        black_pairings_dict,
        byes_dict,
        include_current=False,
    ):
        white_pairings = white_pairings_dict.get(self.season_player.player, [])
        black_pairings = black_pairings_dict.get(self.season_player.player, [])
        byes = byes_dict.get(self.season_player.player, [])
        cumul_score = 0.0
        for round_ in rounds:
            if not round_.is_completed and (
                not include_current or not round_.publish_pairings
            ):
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
                    color = "W"
                    result_type = (
                        "W"
                        if score == 1
                        else "D"
                        if score == 0.5
                        else "L"
                        if score == 0
                        else "F"
                    )
                else:
                    # Special result
                    result_type = (
                        "X"
                        if score == 1
                        else "Z"
                        if score == 0.5
                        else "F"
                        if score == 0
                        else ""
                    )
            elif black_pairing is not None and black_pairing.white is not None:
                opponent = black_pairing.white
                score = black_pairing.black_score()
                if black_pairing.game_played() or score is None:
                    # Normal result
                    color = "B"
                    result_type = (
                        "W"
                        if score == 1
                        else "D"
                        if score == 0.5
                        else "L"
                        if score == 0
                        else "F"
                    )
                else:
                    # Special result
                    result_type = (
                        "X"
                        if score == 1
                        else "Z"
                        if score == 0.5
                        else "F"
                        if score == 0
                        else ""
                    )
            elif bye is not None:
                score = bye.score()
                result_type = "B" if score == 1 else "H" if score == 0.5 else "U"
            else:
                score = 0
                result_type = "U"

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

    def get_tiebreak_value(self, name):
        field_map = {
            "head_to_head": self.head_to_head,
            "buchholz_cut1": self.buchholz_cut1,
            "buchholz": self.buchholz,
            "games_won": self.games_won,
            "games_with_black": self.games_with_black,
            "sonneborn_berger": self.sonneborn_berger,
        }
        return field_map.get(name, 0)

    def get_tiebreak_display(self, tiebreak_name):
        value = self.get_tiebreak_value(tiebreak_name)
        if isinstance(value, float):
            return "%g" % value
        return str(value)

    def _tiebreak_sort_values(self):
        league = self.season_player.season.league
        return [self.get_tiebreak_value(tb) for tb in league.get_lone_tiebreaks()]

    def pairing_sort_key(self):
        sort_key = [self.points + self.late_join_points]
        sort_key.extend(self._tiebreak_sort_values())
        sort_key.append(self.season_player.player_rating_display() or 0)
        return tuple(sort_key)

    def intermediate_standings_sort_key(self):
        sort_key = [self.points + self.late_join_points]
        sort_key.extend(self._tiebreak_sort_values())
        sort_key.append(self.season_player.player_rating_display() or 0)
        return tuple(sort_key)

    def final_standings_sort_key(self):
        sort_key = [self.points]
        sort_key.extend(self._tiebreak_sort_values())
        sort_key.append(self.season_player.player_rating_display() or 0)
        return tuple(sort_key)

    def __str__(self):
        return "%s" % (self.season_player)


def lone_player_pairing_rank_dict(season):
    raw_player_scores = (
        LonePlayerScore.objects.filter(season_player__season=season)
        .select_related("season_player__season__league", "season_player__player")
        .nocache()
    )
    player_scores = list(
        enumerate(
            sorted(raw_player_scores, key=lambda s: s.pairing_sort_key(), reverse=True),
            1,
        )
    )
    return {p.season_player.player_id: n for n, p in player_scores}


# -------------------------------------------------------------------------------
class PlayerAvailability(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    is_available = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "player availabilities"

    def __str__(self):
        return "%s" % self.player


ALTERNATE_STATUS_OPTIONS = (
    ("waiting", "Waiting"),
    ("contacted", "Contacted"),
    ("accepted", "Accepted"),
    ("declined", "Declined"),
    ("unresponsive", "Unresponsive"),
)


# -------------------------------------------------------------------------------
class Alternate(_BaseModel):
    season_player = models.OneToOneField(SeasonPlayer, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)
    priority_date_override = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        blank=True, default="waiting", max_length=31, choices=ALTERNATE_STATUS_OPTIONS
    )
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
        season_player_changed = (
            self.pk is None or self.season_player_id != self.initial_season_player_id
        )
        status_changed = self.pk is None or self.status != self.initial_status
        if season_player_changed:
            self.player_rating = None
        if status_changed and self.status == "unresponsive":
            current_date = timezone.now()
            if (
                self.priority_date_override is None
                or self.priority_date_override < current_date
            ):
                self.priority_date_override = current_date
        super(Alternate, self).save(*args, **kwargs)

    def update_board_number(self):
        season = self.season_player.season
        player = self.season_player.player
        buckets = AlternateBucket.objects.filter(season=season)
        if (
            len(buckets) == season.boards
            and player.rating_for(season.league) is not None
        ):
            for b in buckets:
                if b.contains(player.rating_for(season.league)):
                    self.board_number = b.board_number
                    self.save()

    def priority_date(self):
        return self.priority_date_and_reason()[0]

    def priority_date_and_reason(self):
        if self.priority_date_override is not None:
            return max(
                (self.priority_date_override, "Was unresponsive"),
                self._priority_date_without_override(),
            )
        return self._priority_date_without_override()

    def _priority_date_without_override(self):
        most_recent_assign = (
            AlternateAssignment.objects.filter(
                team__season_id=self.season_player.season_id,
                player_id=self.season_player.player_id,
            )
            .order_by("-round__start_date")
            .first()
        )

        if most_recent_assign is not None:
            round_date = most_recent_assign.round.end_date
            if round_date is not None:
                return (round_date, "Assigned game")

        if self.season_player.registration is not None:
            return (self.season_player.registration.date_created, "Registered")

        return (self.date_created, "Made alternate")

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

    replaced_player = models.ForeignKey(
        Player,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="alternate_replacements",
    )

    class Meta:
        unique_together = ("round", "team", "board_number")

    def __init__(self, *args, **kwargs):
        super(AlternateAssignment, self).__init__(*args, **kwargs)
        self.initial_player_id = self.player_id
        self.initial_team_id = self.team_id
        self.initial_board_number = self.board_number

    def clean(self):
        if (
            self.round_id
            and self.team_id
            and self.round.season_id != self.team.season_id
        ):
            raise ValidationError("Round and team seasons must match")
        if (
            self.team_id
            and self.player_id
            and not SeasonPlayer.objects.filter(
                season=self.team.season, player=self.player
            ).exists()
        ):
            raise ValidationError("Assigned player must be a player in the season")

    def save(self, *args, **kwargs):
        if self.replaced_player is None:
            tm = TeamMember.objects.filter(
                team=self.team, board_number=self.board_number
            ).first()
            if tm is not None:
                self.replaced_player = tm.player

        super(AlternateAssignment, self).save(*args, **kwargs)

        # Find and update any current pairings
        white_pairing = self.team.pairings_as_white.filter(round=self.round).first()
        if white_pairing is not None:
            pairing = (
                white_pairing.teamplayerpairing_set.filter(
                    board_number=self.board_number
                )
                .nocache()
                .first()
            )
            if pairing is not None:
                if self.board_number % 2 == 1:
                    pairing.white = self.player
                else:
                    pairing.black = self.player
                pairing.save()
        black_pairing = self.team.pairings_as_black.filter(round=self.round).first()
        if black_pairing is not None:
            pairing = (
                black_pairing.teamplayerpairing_set.filter(
                    board_number=self.board_number
                )
                .nocache()
                .first()
            )
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
        unique_together = ("season", "board_number")

    def contains(self, rating):
        if rating is None:
            return self.min_rating is None
        return (self.min_rating is None or rating > self.min_rating) and (
            self.max_rating is None or rating <= self.max_rating
        )

    def __str__(self):
        return "Board %d (%s, %s]" % (
            self.board_number,
            self.min_rating,
            self.max_rating,
        )


def create_api_token(length: int = 32) -> str:
    return get_random_string(length=length)


ALTERNATE_SEARCH_STATUS_OPTIONS = (
    ("started", "Started"),
    ("all_contacted", "All alternates contacted"),
    ("completed", "Completed"),
    ("cancelled", "Cancelled"),
    ("failed", "Failed"),
)


# -------------------------------------------------------------------------------
class AlternateSearch(_BaseModel):
    round = models.ForeignKey(Round, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    board_number = models.PositiveIntegerField(choices=BOARD_NUMBER_OPTIONS)

    is_active = models.BooleanField(default=True)
    status = models.CharField(
        blank=True, max_length=31, choices=ALTERNATE_SEARCH_STATUS_OPTIONS
    )
    last_alternate_contact_date = models.DateTimeField(blank=True, null=True)

    class Meta:
        unique_together = ("round", "team", "board_number")

    def clean(self):
        if (
            self.round_id
            and self.team_id
            and self.round.season_id != self.team.season_id
        ):
            raise ValidationError("Round and team seasons must match")

    def still_needs_alternate(self):
        if self.round.publish_pairings:
            team_pairing = self.team.get_teampairing(self.round)
            player_pairing = (
                TeamPlayerPairing.objects.filter(
                    team_pairing=team_pairing,
                    board_number=self.board_number,
                    result="",
                    game_link="",
                )
                .nocache()
                .first()
            )
            return player_pairing is not None and (
                player_pairing.white_team() == self.team
                and (
                    not player_pairing.white
                    or not player_pairing.white.is_available_for(self.round)
                )
                or player_pairing.black_team() == self.team
                and (
                    not player_pairing.black
                    or not player_pairing.black.is_available_for(self.round)
                )
            )
        else:
            player = None
            aa = AlternateAssignment.objects.filter(
                round=self.round, team=self.team, board_number=self.board_number
            ).first()
            if aa is not None:
                player = aa.player
            else:
                team_member = TeamMember.objects.filter(
                    team=self.team, board_number=self.board_number
                ).first()
                if team_member is not None:
                    player = team_member.player
            return player is not None and not player.is_available_for(self.round)

    def __str__(self):
        return "%s - %s - Board %d" % (self.round, self.team.name, self.board_number)


# -------------------------------------------------------------------------------
class AlternatesManagerSetting(_BaseModel):
    league = models.OneToOneField(League, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True)
    contact_interval = models.DurationField(
        default=timedelta(hours=8),
        help_text="How long before the next alternate will be contacted during the round.",
    )
    unresponsive_interval = models.DurationField(
        default=timedelta(hours=24),
        help_text="How long after being contacted until an alternate will be marked as unresponsive.",
    )
    rating_flex = models.PositiveIntegerField(
        default=0,
        help_text="How far out of a board's rating range an alternate can be if it helps alternate balance.",
    )

    contact_before_round_start = models.BooleanField(
        default=True,
        help_text="If we should search for alternates before the pairings are published. Has no effect for round 1.",
    )
    contact_offset_before_round_start = models.DurationField(
        default=timedelta(hours=48),
        help_text="How long before the round starts we should start searching for alternates. Also ends the previous round searches early.",
    )
    contact_interval_before_round_start = models.DurationField(
        default=timedelta(hours=12),
        help_text="How long before the next alternate will be contacted, if the round hasn't started yet.",
    )

    def clean(self):
        if self.league_id and self.league.competitor_type != "team":
            raise ValidationError(
                "Alternates manager settings can only be created for team leagues"
            )

    def __str__(self):
        return "%s" % (self.league)


# -------------------------------------------------------------------------------
class SeasonPrize(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    rank = models.PositiveIntegerField()
    max_rating = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ("season", "rank", "max_rating")

    def __str__(self):
        if self.max_rating is not None:
            return "%s - U%d #%d" % (self.season, self.max_rating, self.rank)
        else:
            return "%s - #%d" % (self.season, self.rank)


# -------------------------------------------------------------------------------
class SeasonPrizeWinner(_BaseModel):
    season_prize = models.ForeignKey(SeasonPrize, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("season_prize", "player")

    def __str__(self):
        return "%s - %s" % (self.season_prize, self.player)


# -------------------------------------------------------------------------------
class GameNomination(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    nominating_player = models.ForeignKey(Player, on_delete=models.CASCADE)
    game_link = models.URLField(validators=[game_link_validator])
    pairing = models.ForeignKey(
        PlayerPairing, blank=True, null=True, on_delete=models.SET_NULL
    )

    def __str__(self):
        return "%s - %s" % (self.season, self.nominating_player)


# -------------------------------------------------------------------------------
class GameSelection(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    game_link = models.URLField(validators=[game_link_validator])
    pairing = models.ForeignKey(
        PlayerPairing, blank=True, null=True, on_delete=models.SET_NULL
    )

    class Meta:
        unique_together = ("season", "game_link")

    def __str__(self):
        return "%s - %s" % (self.season, self.game_link)


class AvailableTime(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    time = models.DateTimeField()


# -------------------------------------------------------------------------------
class NavItem(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    parent = models.ForeignKey("self", blank=True, null=True, on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    text = models.CharField(max_length=255)
    path = models.CharField(max_length=1023, blank=True)
    league_relative = models.BooleanField(default=False)
    season_relative = models.BooleanField(default=False)
    append_separator = models.BooleanField(default=False)

    def __str__(self):
        return "%s - %s" % (self.league, self.text)


# -------------------------------------------------------------------------------
class ApiKey(_BaseModel):
    name = models.CharField(max_length=255, unique=True)
    secret_token = models.CharField(
        max_length=255, unique=True, default=create_api_token
    )

    def __str__(self):
        return self.name


# -------------------------------------------------------------------------------
class PrivateUrlAuth(_BaseModel):
    # Note: Could separate the one-time-URL and timed-auth portions into separate models at some point in the future
    authenticated_user = models.CharField(
        max_length=255, validators=[username_validator]
    )
    secret_token = models.CharField(
        max_length=255, unique=True, default=create_api_token
    )
    expires = models.DateTimeField()
    used = models.BooleanField(default=False)

    def is_expired(self):
        return self.expires < timezone.now()

    def __str__(self):
        return self.authenticated_user


# -------------------------------------------------------------------------------
class LoginToken(_BaseModel):
    lichess_username = models.CharField(
        max_length=255, blank=True, validators=[username_validator]
    )
    username_hint = models.CharField(max_length=255, blank=True)
    slack_user_id = models.CharField(max_length=255, blank=True)
    secret_token = models.CharField(
        max_length=255, unique=True, default=create_api_token
    )
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
    allow_editors = models.BooleanField(
        default=False, verbose_name="Allow designated editors"
    )
    owner = models.ForeignKey(
        User, limit_choices_to=models.Q(is_staff=True), on_delete=models.PROTECT
    )

    def owned_by(self, user):
        return self.owner == user

    def __str__(self):
        return self.name


LEAGUE_DOCUMENT_TYPES = (
    ("faq", "FAQ"),
    ("rules", "Rules"),
    ("intro", "Intro"),
    ("slack-welcome", "Slack Welcome"),
)


# -------------------------------------------------------------------------------
class LeagueDocument(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    document = models.OneToOneField(Document, on_delete=models.CASCADE)
    tag = models.SlugField(
        help_text="The document will be accessible at /{league_tag}/document/{document_tag}/"
    )
    type = models.CharField(blank=True, max_length=255, choices=LEAGUE_DOCUMENT_TYPES)

    class Meta:
        unique_together = ("league", "tag")

    def clean(self):
        if SeasonDocument.objects.filter(document_id=self.document_id):
            raise ValidationError("Document already belongs to a season")

    def __str__(self):
        return self.document.name


SEASON_DOCUMENT_TYPES = (("links", "Links"),)


# -------------------------------------------------------------------------------
class SeasonDocument(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    document = models.OneToOneField(Document, on_delete=models.CASCADE)
    tag = models.SlugField(
        help_text="The document will be accessible at /{league_tag}/season/{season_tag}/document/{document_tag}/"
    )
    type = models.CharField(blank=True, max_length=255, choices=SEASON_DOCUMENT_TYPES)

    class Meta:
        unique_together = ("season", "tag")

    def clean(self):
        if LeagueDocument.objects.filter(document_id=self.document_id):
            raise ValidationError("Document already belongs to a league")

    def __str__(self):
        return self.document.name


LEAGUE_CHANNEL_TYPES = (
    ("mod", "Mods"),
    ("captains", "Captains"),
    ("scheduling", "Scheduling"),
    ("games", "Games"),
)


# -------------------------------------------------------------------------------
class LeagueChannel(_BaseModel):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=LEAGUE_CHANNEL_TYPES)
    slack_channel = models.CharField(max_length=255)
    slack_channel_id = models.CharField(max_length=255, blank=True)
    send_messages = models.BooleanField(default=True)

    class Meta:
        unique_together = ("league", "slack_channel", "type")

    def channel_link(self):
        if not self.slack_channel_id:
            return self.slack_channel
        return "<%s%s|%s>" % (
            self.slack_channel[0],
            self.slack_channel_id,
            self.slack_channel[1:],
        )

    def __str__(self):
        return "%s - %s" % (self.league, self.get_type_display())


SCHEDULED_EVENT_TYPES = (
    ("notify_mods_unscheduled", "Notify mods of unscheduled games"),
    ("notify_mods_no_result", "Notify mods of games without results"),
    ("notify_mods_pending_regs", "Notify mods of pending registrations"),
    ("start_round_transition", "Start round transition"),
    ("notify_players_unscheduled", "Notify players of unscheduled games"),
    ("notify_players_game_time", "Notify players of their game time"),
    ("automod_unresponsive", "Auto-mod unresponsive players"),
    ("automod_noshow", "Auto-mod no-shows"),
)

SCHEDULED_EVENT_RELATIVE_TO = (
    ("round_start", "Round start"),
    ("round_end", "Round end"),
    ("game_scheduled_time", "Game scheduled time"),
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
        return "%s" % (self.get_type_display())

    def run(self, obj):
        self.last_run = timezone.now()
        self.save()

        if self.type == "notify_mods_unscheduled" and isinstance(obj, Round):
            signals.notify_mods_unscheduled.send(sender=self.__class__, round_=obj)
        elif self.type == "notify_mods_no_result" and isinstance(obj, Round):
            signals.notify_mods_no_result.send(sender=self.__class__, round_=obj)
        elif self.type == "notify_mods_pending_regs" and isinstance(obj, Round):
            signals.notify_mods_pending_regs.send(sender=self.__class__, round_=obj)
        elif self.type == "start_round_transition" and isinstance(obj, Round):
            signals.do_round_transition.send(sender=self.__class__, round_id=obj.pk)
        elif self.type == "notify_players_unscheduled" and isinstance(obj, Round):
            signals.notify_players_unscheduled.send(sender=self.__class__, round_=obj)
        elif self.type == "notify_players_game_time" and isinstance(obj, PlayerPairing):
            signals.notify_players_game_time.send(sender=self.__class__, pairing=obj)
        elif self.type == "automod_unresponsive" and isinstance(obj, Round):
            signals.automod_unresponsive.send(sender=self.__class__, round_=obj)
        elif self.type == "automod_noshow" and isinstance(obj, PlayerPairing):
            signals.automod_noshow.send(sender=self.__class__, pairing=obj)

    def clean(self):
        if self.league_id and self.season_id and self.season.league != self.league:
            raise ValidationError("League and season must be compatible")


PLAYER_NOTIFICATION_TYPES = (
    ("round_started", "Round started"),
    ("before_game_time", "Before game time"),
    ("game_scheduled", "Game was scheduled"),
    ("game_started", "Game started"),
    ("game_time", "Game time"),
    ("unscheduled_game", "Unscheduled game"),
    ("game_warning", "Game warning"),
    ("alternate_needed", "Alternate needed"),
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
        unique_together = ("player", "type", "league")

    def __str__(self):
        return "%s - %s" % (self.player, self.get_type_display())

    def save(self, *args, **kwargs):
        super(PlayerNotificationSetting, self).save(*args, **kwargs)
        if self.type == "before_game_time":
            # Rebuild scheduled notifications based on offset
            self.schedulednotification_set.all().delete()
            upcoming_pairings = self.player.pairings.filter(
                scheduled_time__gt=timezone.now()
            )
            upcoming_pairings = upcoming_pairings.filter(
                teamplayerpairing__team_pairing__round__season__league=self.league
            ) | upcoming_pairings.filter(
                loneplayerpairing__round__season__league=self.league
            )
            for p in upcoming_pairings:
                notification_time = p.scheduled_time - self.offset
                ScheduledNotification.objects.create(
                    setting=self, pairing=p, notification_time=notification_time
                )

    @classmethod
    def get_or_default(cls, **kwargs):
        obj = PlayerNotificationSetting.objects.filter(**kwargs).first()
        if obj is not None:
            return obj
        # Return (but don't create) the default setting based on the type
        obj = PlayerNotificationSetting(**kwargs)
        type_ = kwargs.get("type")
        if type_ == "before_game_time" and obj.offset is not None:
            del kwargs["offset"]
            has_other_offset = PlayerNotificationSetting.objects.filter(
                **kwargs
            ).exists()
            if has_other_offset or obj.offset != timedelta(minutes=60):
                # Non-default offset, so leave everything disabled
                return obj
        obj.enable_lichess_mail = type_ in (
            "round_started",
            "game_warning",
            "alternate_needed",
        )
        obj.enable_slack_im = type_ in (
            "round_started",
            "game_scheduled",
            "game_started",
            "before_game_time",
            "game_time",
            "unscheduled_game",
            "alternate_needed",
        )
        obj.enable_slack_mpim = type_ in (
            "round_started",
            "game_scheduled",
            "game_started",
            "before_game_time",
            "game_time",
            "unscheduled_game",
        )
        if type_ == "before_game_time":
            obj.offset = timedelta(minutes=60)
        return obj

    def clean(self):
        if self.type in ("before_game_time",):
            if self.offset is None:
                raise ValidationError("Offset is required for this type")
        else:
            if self.offset is not None:
                raise ValidationError("Offset is not applicable for this type")


# -------------------------------------------------------------------------------
class PlayerPresence(_BaseModel):
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    pairing = models.ForeignKey(PlayerPairing, on_delete=models.CASCADE)
    round = models.ForeignKey(Round, on_delete=models.CASCADE)

    first_msg_time = models.DateTimeField(null=True, blank=True)
    last_msg_time = models.DateTimeField(null=True, blank=True)
    online_for_game = models.BooleanField(default=False)

    def __str__(self):
        return "%s" % (self.player)


PLAYER_WARNING_TYPE_OPTIONS = (
    ("unresponsive", "unresponsive"),
    ("card_unresponsive", "card for unresponsive"),
    ("card_noshow", "card for no-show"),
)


# -------------------------------------------------------------------------------
class PlayerWarning(_BaseModel):
    round = models.ForeignKey(Round, null=True, blank=True, on_delete=models.CASCADE)
    player = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=PLAYER_WARNING_TYPE_OPTIONS)

    class Meta:
        unique_together = ("round", "player", "type")

    def __str__(self):
        return "%s - %s" % (self.player.lichess_username, self.get_type_display())


# -------------------------------------------------------------------------------
class ScheduledNotification(_BaseModel):
    setting = models.ForeignKey(PlayerNotificationSetting, on_delete=models.CASCADE)
    pairing = models.ForeignKey(PlayerPairing, on_delete=models.CASCADE)
    notification_time = models.DateTimeField()

    def __str__(self):
        return "%s" % (self.setting)

    def save(self, *args, **kwargs):
        if self.notification_time < timezone.now():
            if self.pk:
                self.delete()
        else:
            super(ScheduledNotification, self).save(*args, **kwargs)

    def run(self):
        try:
            if self.setting.type == "before_game_time":
                pairing = PlayerPairing.objects.nocache().get(pk=self.pairing_id)
                if pairing.scheduled_time is not None:
                    signals.before_game_time.send(
                        sender=self.__class__,
                        player=self.setting.player,
                        pairing=pairing,
                        offset=self.setting.offset,
                    )
        except Exception:
            logger.exception("Error running scheduled notification")
        self.delete()

    def clean(self):
        if self.setting.offset is None:
            raise ValidationError("Setting must have an offset")


# -------------------------------------------------------------------------------
class FcmSub(_BaseModel):
    slack_user_id = models.CharField(max_length=31)
    reg_id = models.CharField(max_length=4096, unique=True)


MOD_REQUEST_STATUS_OPTIONS = (
    ("pending", "Pending"),
    ("approved", "Approved"),
    ("rejected", "Rejected"),
)

MOD_REQUEST_TYPE_OPTIONS = (
    ("withdraw", "Withdraw"),
    ("reregister", "Re-register"),
    ("appeal_late_response", "Appeal late response"),
    ("appeal_noshow", "Appeal no-show"),
    ("appeal_draw_scheduling", "Appeal scheduling draw"),
    ("claim_win_noshow", "Claim a forfeit win (no-show)"),
    ("claim_win_effort", "Claim a forfeit win (insufficient effort)"),
    ("claim_draw_scheduling", "Claim a scheduling draw"),
    ("claim_loss", "Claim a forfeit loss"),
    ("request_continuation", "Request continuation"),
)

# A plain string literal won't work as a Django signal sender since it will have a unique object reference
# By using a common dict we can make sure we're working with the same object (using `intern` would also work)
# This also has the advantage that typos will create a KeyError instead of silently failing
MOD_REQUEST_SENDER = {a: a for a, _ in MOD_REQUEST_TYPE_OPTIONS}


# -------------------------------------------------------------------------------
class ModRequest(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    round = models.ForeignKey(Round, null=True, blank=True, on_delete=models.CASCADE)
    pairing = models.ForeignKey(
        PlayerPairing, null=True, blank=True, on_delete=models.CASCADE
    )
    requester = models.ForeignKey(Player, on_delete=models.CASCADE)
    type = models.CharField(max_length=255, choices=MOD_REQUEST_TYPE_OPTIONS)
    status = models.CharField(max_length=31, choices=MOD_REQUEST_STATUS_OPTIONS)
    status_changed_by = models.CharField(blank=True, max_length=255)
    status_changed_date = models.DateTimeField(blank=True, null=True)

    notes = models.TextField(blank=True)
    # TODO: Multiple screenshot support?
    screenshot = models.ImageField(
        upload_to="screenshots/%Y/%m/%d/", null=True, blank=True
    )
    response = models.TextField(blank=True)

    def approve(self, user="System", response=""):
        with reversion.create_revision():
            reversion.set_comment(f"Mod request approved by {user}")
            self.status = "approved"
            self.status_changed_by = user
            self.status_changed_date = timezone.now()
            self.response = response
            self.save()
        signals.mod_request_approved.send(
            sender=MOD_REQUEST_SENDER[self.type], instance=self
        )

    def reject(self, user="System", response=""):
        with reversion.create_revision():
            reversion.set_comment(f"Mod request rejected by {user}")
            self.status = "rejected"
            self.status_changed_by = user
            self.status_changed_date = timezone.now()
            self.response = response
            self.save()
        signals.mod_request_rejected.send(
            sender=MOD_REQUEST_SENDER[self.type], instance=self, response=response
        )

    def clean(self):
        pass
        # TODO: This validation isn't working because type is not populated in the form.

    #         if not self.screenshot and self.type in ('appeal_late_response', 'claim_win_noshow', 'claim_win_effort', 'claim_draw_scheduling'):
    #             raise ValidationError('Screenshot is required')

    def __str__(self):
        return "%s - %s" % (self.requester.lichess_username, self.get_type_display())


class Broadcast(_BaseModel):
    season = models.ForeignKey(Season, on_delete=models.CASCADE)
    lichess_id = models.SlugField(blank=True, max_length=10)
    first_board = models.PositiveSmallIntegerField(default=1)

    class Meta:
        unique_together = ["season", "first_board"]
        ordering = ["season", "first_board"]

    def __str__(self) -> str:
        return f"BC {self.season} B{self.first_board}"


class BroadcastRound(_BaseModel):
    round_id = models.ForeignKey(Round, on_delete=models.CASCADE)
    lichess_id = models.SlugField(blank=True, max_length=10)
    broadcast = models.ForeignKey(Broadcast, on_delete=models.CASCADE)

    class Meta:
        unique_together = ["broadcast", "round_id"]
        ordering = ["broadcast", "round_id"]

    @property
    def first_board(self) -> int:
        return self.broadcast.first_board

    # last_board is a round property, because it may change with additional players signing up
    @property
    def last_board(self) -> int:
        nextbc = (
            Broadcast.objects.filter(
                season=self.broadcast.season, first_board__gt=self.first_board
            )
            .order_by("first_board")
            .first()
        )
        if nextbc is not None:
            return nextbc.first_board - 1
        if self.round_id.is_team_league():
            return TeamPlayerPairing.objects.filter(
                team_pairing__round=self.round_id
            ).count()
        else:
            return LonePlayerPairing.objects.filter(round=self.round_id).count()

    def __str__(self) -> str:
        return f"BCR {self.round_id} B{self.first_board}"


class Announcement(_BaseModel):
    """Site-wide announcements that can be shown on specific paths"""

    ANNOUNCEMENT_STATUS_CHOICES = [
        ("info", "Info"),
        ("warning", "Warning"),
        ("danger", "Danger"),
        ("success", "Success"),
    ]

    text = RichTextUploadingField(
        help_text="Announcement text. Supports rich text formatting.",
        verbose_name="Announcement Text",
    )

    status = models.CharField(
        max_length=10,
        choices=ANNOUNCEMENT_STATUS_CHOICES,
        default="info",
        help_text="Bootstrap alert style for the announcement",
        verbose_name="Status",
    )

    start_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When this announcement should start showing. Leave empty to show immediately.",
        verbose_name="Start Date",
    )

    end_date = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When this announcement should stop showing. Leave empty to show indefinitely.",
        verbose_name="End Date",
    )

    path_prefix = models.CharField(
        max_length=255,
        default="/",
        help_text="Path prefix to show announcement on. '/' means all pages. '/tournament/' would show on tournament pages only.",
        verbose_name="Path Prefix",
    )

    is_active = models.BooleanField(
        default=True,
        help_text="Whether this announcement is active",
        verbose_name="Active",
    )

    class Meta:
        ordering = ["-start_date"]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self):
        if self.start_date:
            return f"Announcement #{self.id} ({self.status}) - {self.start_date.strftime('%Y-%m-%d')}"
        else:
            return f"Announcement #{self.id} ({self.status}) - Always active"

    def get_text_preview(self):
        """Return truncated plain text version of the announcement"""
        from django.utils.html import strip_tags
        from django.utils.text import Truncator

        plain_text = strip_tags(self.text)
        return Truncator(plain_text).chars(80, truncate="...")

    get_text_preview.short_description = "Message Preview"

    @classmethod
    def get_active_for_path(cls, path):
        """Get all active announcements for a given path"""
        from django.utils import timezone

        now = timezone.now()

        # Build date filters: start_date is null OR start_date <= now
        # AND end_date is null OR end_date >= now
        from django.db.models import Q

        date_filter = Q(Q(start_date__isnull=True) | Q(start_date__lte=now)) & Q(
            Q(end_date__isnull=True) | Q(end_date__gte=now)
        )

        announcements = cls.objects.filter(is_active=True).filter(date_filter).nocache()

        # Filter by path prefix
        matching_announcements = []
        for announcement in announcements:
            # Check if current path matches the announcement's path prefix
            if path.startswith(announcement.path_prefix):
                matching_announcements.append(announcement)

        return matching_announcements


# -------------------------------------------------------------------------------
class KnockoutBracket(_BaseModel):
    season = models.OneToOneField(Season, on_delete=models.CASCADE)
    bracket_size = models.PositiveIntegerField(
        help_text="Total number of teams in knockout bracket (must be power of 2)"
    )
    seeding_style = models.CharField(
        max_length=16, choices=KNOCKOUT_SEEDING_OPTIONS, default="traditional"
    )
    games_per_match = models.PositiveIntegerField(
        default=1, help_text="Number of games each team pair plays before elimination"
    )
    matches_per_stage = models.PositiveIntegerField(
        default=1,
        help_text="Number of matches each team pair plays per stage (1=single elimination, 2=return matches, etc.)",
    )
    is_completed = models.BooleanField(default=False)

    def clean(self):
        from django.core.exceptions import ValidationError

        # Validate power of 2
        if self.bracket_size and not (
            self.bracket_size > 1 and (self.bracket_size & (self.bracket_size - 1)) == 0
        ):
            raise ValidationError("Bracket size must be a power of 2")

    def __str__(self):
        return f"{self.season} - {self.bracket_size} team knockout"


# -------------------------------------------------------------------------------
class KnockoutSeeding(_BaseModel):
    bracket = models.ForeignKey(KnockoutBracket, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    seed_number = models.PositiveIntegerField(help_text="1-indexed seed position")
    is_manual_seed = models.BooleanField(
        default=False, help_text="True if seeding was set manually vs automatically"
    )

    class Meta:
        unique_together = [("bracket", "team"), ("bracket", "seed_number")]
        ordering = ["seed_number"]

    def __str__(self):
        return f"Seed #{self.seed_number}: {self.team.name}"


# -------------------------------------------------------------------------------
class KnockoutAdvancement(_BaseModel):
    """Track team advancement through knockout rounds"""

    bracket = models.ForeignKey(KnockoutBracket, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    from_stage = models.CharField(max_length=32)  # e.g., "semifinals"
    to_stage = models.CharField(max_length=32)  # e.g., "finals"
    source_pairing = models.ForeignKey(
        TeamPairing,
        on_delete=models.CASCADE,
        help_text="The pairing that determined this advancement",
    )
    advanced_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("bracket", "team", "to_stage")]

    def __str__(self):
        return f"{self.team.name}: {self.from_stage} → {self.to_stage}"


# -------------------------------------------------------------------------------
class TeamMultiMatchProgress(_BaseModel):
    """Track progress of teams through multi-match knockout stages"""

    bracket = models.ForeignKey(KnockoutBracket, on_delete=models.CASCADE)
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    round_number = models.PositiveIntegerField(
        help_text="Round number in knockout bracket"
    )
    stage_name = models.CharField(
        max_length=32, help_text="Stage name (e.g., 'semifinals', 'finals')"
    )
    opponent_team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="multi_match_opponent_progress",
        help_text="The team this team is paired against",
    )
    original_pairing_order = models.PositiveIntegerField(
        help_text="Original pairing order within the stage (1, 2, 3, 4, ...)"
    )
    matches_completed = models.PositiveIntegerField(
        default=0, help_text="Number of matches completed by this team pair"
    )
    total_matches_required = models.PositiveIntegerField(
        help_text="Total matches this team pair must complete before elimination"
    )
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("bracket", "team", "round_number")]
        indexes = [
            models.Index(fields=["bracket", "round_number", "original_pairing_order"]),
            models.Index(fields=["bracket", "round_number", "matches_completed"]),
        ]

    @property
    def is_stage_complete_for_pair(self):
        """Check if this team pair has completed all required matches"""
        return self.matches_completed >= self.total_matches_required

    @property
    def current_match_number(self):
        """Get the current match number this team pair is on"""
        return min(self.matches_completed + 1, self.total_matches_required)

    def __str__(self):
        return f"{self.team.name} vs {self.opponent_team.name} ({self.stage_name}): {self.matches_completed}/{self.total_matches_required}"
