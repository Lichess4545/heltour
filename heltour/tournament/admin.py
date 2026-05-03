import json
import re
import time
from collections import defaultdict
from typing import ClassVar
from datetime import timedelta
from smtplib import SMTPException
from urllib.parse import quote as urlquote

import reversion
from django.contrib import admin, messages
from django.contrib.admin.filters import (
    FieldListFilter,
    RelatedFieldListFilter,
    SimpleListFilter,
)
from django.contrib.contenttypes.models import ContentType
from django.core import mail
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.mail.message import EmailMultiAlternatives
from django.db import transaction
from django.db.models import Max, Q
from django.db.models.query import Prefetch
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.forms.models import ModelForm
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django_comments.models import Comment
from reversion.admin import VersionAdmin

from django.conf import settings
from heltour.tournament import (
    forms,
    lichessapi,
    pairinggen,
    signals,
    simulation,
    slackapi,
    spreadsheet,
    teamgen,
)
from heltour.tournament.models import (
    Alternate,
    AlternateAssignment,
    AlternateBucket,
    AlternateSearch,
    AlternatesManagerSetting,
    Announcement,
    ApiKey,
    AvailableTime,
    Broadcast,
    BroadcastRound,
    Document,
    GameNomination,
    GameSelection,
    InviteCode,
    KnockoutAdvancement,
    KnockoutBracket,
    KnockoutSeeding,
    League,
    LeagueChannel,
    LeagueDocument,
    LeagueModerator,
    LeagueSetting,
    LoginToken,
    LonePlayerPairing,
    LonePlayerScore,
    ModRequest,
    NavItem,
    Player,
    PlayerAvailability,
    PlayerBye,
    PlayerLateRegistration,
    PlayerNotificationSetting,
    PlayerPairing,
    PlayerPresence,
    PlayerPresenceEvent,
    PlayerWarning,
    PlayerWithdrawal,
    PrivateUrlAuth,
    Registration,
    RegistrationMode,
    Round,
    ValidationStatus,
    ScheduledEvent,
    ScheduledNotification,
    Season,
    SeasonDocument,
    SeasonPlayer,
    SeasonPrize,
    SeasonPrizeWinner,
    Section,
    SectionGroup,
    Team,
    TeamBye,
    TeamMember,
    TeamMultiMatchProgress,
    TeamPairing,
    TeamPlayerPairing,
    TeamScore,
    find,
    get_gameid_from_gamelink,
    getnestedattr,
    logger,
    normalize_gamelink,
)
from heltour.tournament.team_rating_utils import team_rating_range, team_rating_variance
from heltour.tournament.workflows import (
    ApproveRegistrationWorkflow,
    MoveLateRegWorkflow,
    RefreshLateRegWorkflow,
    RoundTransitionWorkflow,
    UpdateBoardOrderWorkflow,
)

# Customize which sections are visible
# admin.site.register(Comment)
# admin.site.unregister(Site)


def redirect_with_params(*args, **kwargs):
    params = kwargs.pop("params")
    response = redirect(*args, **kwargs)
    response["Location"] += params
    return response


class PreconditionError(ValueError):
    """Raised when a function/method precondition is violated.

    This exception should be raised at the beginning of a function when
    input validation fails or required conditions are not met.
    """

    pass


def require(condition, error_msg):
    if not condition:
        raise PreconditionError(error_msg)


@receiver(post_save, sender=Comment, dispatch_uid="heltour.tournament.admin")
def comment_saved(instance, created, **kwargs):
    if not created:
        return
    model = instance.content_type.model_class()
    model_admin = admin.site._registry.get(model)
    if model_admin is None or not hasattr(model_admin, "get_league_id"):
        return
    league_id = model_admin.get_league_id(instance.content_object)
    if league_id is None:
        return
    league = League.objects.get(pk=league_id)
    signals.league_comment.send(sender=comment_saved, league=league, comment=instance)


@receiver(
    post_save,
    sender=Registration,
    dispatch_uid="heltour.tournament.admin.registration_auto_approval",
)
def registration_saved(instance, created, **kwargs):
    """Auto-approve registrations with valid invite codes in invite-only leagues"""
    if not created:
        return

    # Check if this is a new approved registration with an invite code
    if (
        instance.status == "approved"
        and instance.invite_code_used
        and instance.season.league.registration_mode == RegistrationMode.INVITE_ONLY
    ):
        # Import here to avoid circular imports
        from heltour.tournament.workflows import (
            create_team_with_captain,
            add_player_to_team,
        )

        # Create SeasonPlayer
        season_player, _ = SeasonPlayer.objects.get_or_create(
            season=instance.season,
            player=instance.player,
            defaults={"is_active": True, "registration": instance},
        )

        # Handle team creation/assignment based on invite code type
        invite_code = instance.invite_code_used
        if invite_code.code_type == "captain":
            create_team_with_captain(instance.player, instance.season)
        elif invite_code.code_type == "team_member" and invite_code.team:
            add_player_to_team(instance.player, invite_code.team)

        # Email sending would happen here if the template existed
        # TODO: Add email template and enable email sending


# -------------------------------------------------------------------------------
class _BaseAdmin(VersionAdmin):
    change_form_template = "tournament/admin/change_form_with_comments.html"
    history_latest_first = True

    league_id_field = None
    league_competitor_type = None

    def has_assigned_perm(self, user, perm_type):
        return (
            "tournament.%s_%s" % (perm_type, self.opts.model_name)
            in user.get_all_permissions()
        )

    def has_dox(self, user):
        return user.has_perm("tournament.dox")

    def remove_email_if_no_dox(self, user, fields):
        if self.has_dox(user):
            return fields
        return [f for f in fields if f != "email"]

    def get_league_id(self, obj):
        if self.league_id_field is None:
            return None
        return getnestedattr(obj, self.league_id_field)

    def has_league_perm(self, user, action, obj):
        if self.league_id_field is None:
            return False
        authorized_leagues = self.authorized_leagues(user)
        if self.league_competitor_type is not None and all(
            (
                League.objects.get(pk=pk).competitor_type != self.league_competitor_type
                for pk in authorized_leagues
            )
        ):
            return False
        if obj is None:
            return bool(authorized_leagues)
        else:
            return self.get_league_id(obj) in authorized_leagues

    def get_queryset(self, request):
        queryset = super(_BaseAdmin, self).get_queryset(request)
        if self.has_assigned_perm(request.user, "change"):
            return queryset
        if self.league_id_field is None:
            return queryset.none()
        return queryset.filter(
            **{self.league_id_field + "__in": self.authorized_leagues(request.user)}
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        kwargs["queryset"] = admin.site._registry[db_field.related_model].get_queryset(
            request
        )
        return super(_BaseAdmin, self).formfield_for_foreignkey(
            db_field, request, **kwargs
        )

    def has_add_permission(self, request):
        if self.has_assigned_perm(request.user, "add"):
            return True
        return self.has_league_perm(request.user, "add", None)

    def has_change_permission(self, request, obj=None):
        if self.has_assigned_perm(request.user, "change"):
            return True
        return self.has_league_perm(request.user, "change", obj)

    def has_delete_permission(self, request, obj=None):
        if self.has_assigned_perm(request.user, "delete"):
            return True
        return self.has_league_perm(request.user, "delete", obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super(_BaseAdmin, self).get_form(request, obj, **kwargs)

        def clean(form):
            super(ModelForm, form).clean()
            self.clean_form(request, form)

        form.clean = clean
        return form

    def clean_form(self, request, form):
        if form.instance.pk is None and self.has_assigned_perm(request.user, "add"):
            return
        if form.instance.pk is not None and self.has_assigned_perm(
            request.user, "change"
        ):
            return
        if self.league_id_field is None:
            raise ValidationError("No permission to save this object")
        # Since we have cleaned_data dict instead of a model instance, we have to
        # pre-process the league id access a bit
        parts = self.league_id_field.split("__", 1)
        if len(parts) == 1:
            if parts[0] == "id":
                league_id = form.cleaned_data["id"]
            else:
                if parts[0][-3:] != "_id":
                    raise ValueError("Invalid league id field on modeladmin")
                league = form.cleaned_data.get(parts[0][:-3])
                if league is None:
                    return
                league_id = league.id
        else:
            league_id = getnestedattr(form.cleaned_data[parts[0]], parts[1])
        if league_id not in self.authorized_leagues(request.user):
            raise ValidationError("No permission to save objects for this league")

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context["related_objects_for_comments"] = (
            self.related_objects_for_comments(request, object_id)
        )
        return super(_BaseAdmin, self).change_view(
            request, object_id, form_url, extra_context=extra_context
        )

    def related_objects_for_comments(self, request, object_id):
        return []

    def authorized_leagues(self, user):
        return [
            lm["league_id"]
            for lm in LeagueModerator.objects.filter(
                player__lichess_username__iexact=user.username
            ).values("league_id")
        ]


# -------------------------------------------------------------------------------
class LeagueRestrictedListFilter(RelatedFieldListFilter):
    def field_choices(self, field, request, model_admin):
        if not isinstance(model_admin, _BaseAdmin) or model_admin.has_assigned_perm(
            request.user, "change"
        ):
            return field.get_choices(include_blank=False)
        league_id_field = admin.site._registry[field.related_model].league_id_field
        league_filter = {
            league_id_field + "__in": model_admin.authorized_leagues(request.user)
        }
        return field.get_choices(include_blank=False, limit_choices_to=league_filter)


FieldListFilter.register(
    lambda f: f.remote_field, LeagueRestrictedListFilter, take_priority=True
)


# -------------------------------------------------------------------------------
@admin.register(League)
class LeagueAdmin(_BaseAdmin):
    actions = ["import_season", "export_forfeit_data"]
    league_id_field = "id"

    fieldsets = (
        (
            "Basic Information",
            {"fields": ("name", "tag", "description", "theme", "display_order")},
        ),
        (
            "League Settings",
            {
                "fields": (
                    "time_control",
                    "rating_type",
                    "competitor_type",
                    "pairing_type",
                    "is_active",
                    "is_default",
                    "enable_notifications",
                    "skip_slack_invites",
                )
            },
        ),
        (
            "Registration Settings",
            {
                "fields": (
                    "registration_mode",
                    "email_required",
                    "show_provisional_warning",
                    "ask_availability",
                )
            },
        ),
        (
            "Personal Information Settings",
            {
                "fields": (
                    "require_name",
                    "require_personal_email",
                    "require_gender",
                    "require_date_of_birth",
                    "require_nationality",
                ),
                "description": "Configure which personal information fields are required during registration.",
            },
        ),
        (
            "Corporate/Organizational Information Settings",
            {
                "fields": (
                    "organisation_label",
                    "require_corporate_email",
                    "require_contact_number",
                ),
                "description": "Configure organisation-related field labels and requirements. Set organisation_label to customize terminology (e.g., 'Company', 'University').",
            },
        ),
        (
            "Chess Federation Information Settings",
            {
                "fields": (
                    "require_fide_id",
                    "require_regional_rating",
                    "regional_rating_name",
                    "show_fide_names",
                ),
                "description": "Configure chess federation ID and rating requirements. Set regional_rating_name (e.g., 'USCF', 'ECF', 'CFC') when require_regional_rating is enabled.",
            },
        ),
        (
            "Team Tiebreak Configuration",
            {
                "fields": (
                    "team_tiebreak_1",
                    "team_tiebreak_2",
                    "team_tiebreak_3",
                    "team_tiebreak_4",
                    "team_tiebreak_5",
                    "team_tiebreak_6",
                    "team_tiebreak_7",
                ),
                "description": "Configure the tiebreak order for team tournaments. Match points is always the primary sort criterion.",
            },
        ),
        (
            "Lone Tiebreak Configuration",
            {
                "fields": (
                    "lone_tiebreak_1",
                    "lone_tiebreak_2",
                    "lone_tiebreak_3",
                    "lone_tiebreak_4",
                    "lone_tiebreak_5",
                ),
                "description": "Configure the tiebreak order for individual tournaments. Points is always the primary sort criterion.",
            },
        ),
    )

    def has_add_permission(self, request):
        return self.has_assigned_perm(request.user, "add")

    def has_delete_permission(self, request, obj=None):
        return self.has_assigned_perm(request.user, "delete")

    def get_readonly_fields(self, request, obj=None):
        if self.has_assigned_perm(request.user, "change"):
            return ()
        return (
            "competitor_type",
            "tag",
            "theme",
            "display_order",
            "description",
            "is_active",
            "is_default",
            "enable_notifications",
            "registration_mode",
            "email_required",
            "show_provisional_warning",
            "ask_availability",
            "team_tiebreak_1",
            "team_tiebreak_2",
            "team_tiebreak_3",
            "team_tiebreak_4",
            "team_tiebreak_5",
            "team_tiebreak_6",
            "team_tiebreak_7",
            "lone_tiebreak_1",
            "lone_tiebreak_2",
            "lone_tiebreak_3",
            "lone_tiebreak_4",
            "lone_tiebreak_5",
        )

    def get_urls(self):
        urls = super(LeagueAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/import_season/",
                self.admin_site.admin_view(self.import_season_view),
                name="import_season",
            ),
            path(
                "<int:object_id>/export_forfeit_data/",
                self.admin_site.admin_view(self.export_forfeit_data_view),
                name="export_forfeit_data",
            ),
        ]
        return my_urls + urls

    def import_season(self, request, queryset):
        return redirect("admin:import_season", object_id=queryset[0].pk)

    def export_forfeit_data(self, request, queryset):
        return redirect("admin:export_forfeit_data", object_id=queryset[0].pk)

    def import_season_view(self, request, object_id):
        league = get_object_or_404(League, pk=object_id)
        if not request.user.has_perm("tournament.change_league", league):
            raise PermissionDenied

        if request.method == "POST":
            form = forms.ImportSeasonForm(request.POST)
            if form.is_valid():
                try:
                    if league.competitor_type == "team":
                        spreadsheet.import_team_season(
                            league,
                            form.cleaned_data["spreadsheet_url"],
                            form.cleaned_data["season_name"],
                            form.cleaned_data["season_tag"],
                            form.cleaned_data["rosters_only"],
                            form.cleaned_data["exclude_live_pairings"],
                        )
                        self.message_user(request, "Season imported.")
                    elif league.competitor_type == "individual":
                        spreadsheet.import_lonewolf_season(
                            league,
                            form.cleaned_data["spreadsheet_url"],
                            form.cleaned_data["season_name"],
                            form.cleaned_data["season_tag"],
                            form.cleaned_data["rosters_only"],
                            form.cleaned_data["exclude_live_pairings"],
                        )
                        self.message_user(request, "Season imported.")
                    else:
                        self.message_user(
                            request,
                            "League competitor type not supported for spreadsheet import",
                        )
                except spreadsheet.SpreadsheetNotFound:
                    self.message_user(
                        request,
                        "Spreadsheet not found. The service account may not have edit permissions.",
                        messages.ERROR,
                    )
                return redirect("admin:tournament_league_changelist")
        else:
            form = forms.ImportSeasonForm()

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": league,
            "title": "Import season",
            "form": form,
        }

        return render(request, "tournament/admin/import_season.html", context)

    def export_forfeit_data_view(self, request, object_id):
        league = get_object_or_404(League, pk=object_id)
        if not request.user.has_perm("tournament.change_league", league):
            raise PermissionDenied

        pairings = (
            LonePlayerPairing.objects.exclude(result="")
            .exclude(white=None)
            .exclude(black=None)
            .filter(round__season__league=league)
            .order_by("round__start_date")
            .select_related("white", "black", "round")
            .nocache()
        )
        rows = []

        for p in pairings:
            rows.append(
                {
                    "forfeit": (
                        "BOTH"
                        if p.result == "0F-0F"
                        else (
                            "SELF"
                            if p.result == "0F-1X"
                            else (
                                "DRAW"
                                if p.result == "1/2Z-1/2Z"
                                else "OPP"
                                if p.result == "1X-0F"
                                else "NO"
                            )
                        )
                    ),
                    "average_rating": (
                        p.white_rating_display(league) + p.black_rating_display(league)
                    )
                    / 2,
                    "rating_delta": abs(
                        p.white_rating_display(league) - p.black_rating_display(league)
                    ),
                    "timezone_delta": "TODO",
                    "round_joined": "TODO",
                    "player_games_played": "TODO",
                    "player_games_forfeited": "TODO",
                    "player_byes": "TODO",
                    "player_seasons_participated": "TODO",
                    "player_team_seasons_participated": "TODO",
                    "player_games_on_lichess": p.white.games_played,
                    "round_start_date": p.round.start_date,
                }
            )
            rows.append(
                {
                    "forfeit": (
                        "BOTH"
                        if p.result == "0F-0F"
                        else (
                            "SELF"
                            if p.result == "1X-0F"
                            else (
                                "DRAW"
                                if p.result == "1/2Z-1/2Z"
                                else "OPP"
                                if p.result == "0F-1X"
                                else "NO"
                            )
                        )
                    ),
                    "average_rating": (
                        p.white_rating_display(league) + p.black_rating_display(league)
                    )
                    / 2,
                    "rating_delta": abs(
                        p.white_rating_display(league) - p.black_rating_display(league)
                    ),
                    "timezone_delta": "TODO",
                    "round_joined": "TODO",
                    "player_games_played": "TODO",
                    "player_games_forfeited": "TODO",
                    "player_byes": "TODO",
                    "player_seasons_participated": "TODO",
                    "player_team_seasons_participated": "TODO",
                    "player_games_on_lichess": p.black.games_played,
                    "round_start_date": p.round.start_date,
                }
            )

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": league,
            "title": "Export forfeit data",
            "rows": rows,
        }

        return render(request, "tournament/admin/export_forfeit_data.html", context)


# -------------------------------------------------------------------------------
@admin.register(LeagueSetting)
class LeagueSettingAdmin(_BaseAdmin):
    list_display = ("__str__",)
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(SectionGroup)
class SectionGroupAdmin(_BaseAdmin):
    list_display = ("__str__", "league")
    search_fields = ("name",)
    list_filter = ("league",)
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(Section)
class SectionAdmin(_BaseAdmin):
    list_display = ("__str__", "season", "min_rating", "max_rating")
    search_fields = ("name", "season__name")
    list_filter = ("season__league",)
    league_id_field = "season__league_id"


# -------------------------------------------------------------------------------
@admin.register(Season)
class SeasonAdmin(_BaseAdmin):
    list_display = (
        "__str__",
        "league",
    )
    list_display_links = ("__str__",)
    list_filter = ("league",)
    actions = [
        "update_board_order_by_rating",
        "force_alternate_board_update",
        "recalculate_scores",
        "verify_data",
        "review_nominated_games",
        "bulk_email",
        "team_spam",
        "mod_report",
        "manage_players",
        "round_transition",
        "simulate_tournament",
        "create_broadcast",
        "update_broadcast",
        "generate_invite_codes",
    ]
    league_id_field = "league_id"

    def get_urls(self):
        urls = super(SeasonAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/manage_players/",
                self.admin_site.admin_view(self.manage_players_view),
                name="manage_players",
            ),
            path(
                "<int:object_id>/create_teams/",
                self.admin_site.admin_view(self.create_teams_view),
                name="create_teams",
            ),
            path(
                "<int:object_id>/player_info/<slug:player_name>/",
                self.admin_site.admin_view(self.player_info_view),
                name="edit_rosters_player_info",
            ),
            path(
                "<int:object_id>/round_transition/",
                self.admin_site.admin_view(self.round_transition_view),
                name="round_transition",
            ),
            path(
                "<int:object_id>/review_nominated_games/",
                self.admin_site.admin_view(self.review_nominated_games_view),
                name="review_nominated_games",
            ),
            path(
                "<int:object_id>/review_nominated_games/select/<int:nom_id>/",
                self.admin_site.admin_view(self.review_nominated_games_select_view),
                name="review_nominated_games_select",
            ),
            path(
                "<int:object_id>/review_nominated_games/deselect/<int:sel_id>/",
                self.admin_site.admin_view(self.review_nominated_games_deselect_view),
                name="review_nominated_games_deselect",
            ),
            path(
                "<int:object_id>/review_nominated_games/pgn/",
                self.admin_site.admin_view(self.review_nominated_games_pgn_view),
                name="review_nominated_games_pgn",
            ),
            path(
                "<int:object_id>/bulk_email/",
                self.admin_site.admin_view(self.bulk_email_view),
                name="bulk_email",
            ),
            path(
                "<int:object_id>/team_spam/",
                self.admin_site.admin_view(self.team_spam_view),
                name="team_spam",
            ),
            path(
                "<int:object_id>/mod_report/",
                self.admin_site.admin_view(self.mod_report_view),
                name="mod_report",
            ),
            path(
                "<int:object_id>/generate_invite_codes/",
                self.admin_site.admin_view(self.generate_invite_codes_view),
                name="generate_invite_codes",
            ),
            path(
                "<int:object_id>/pre_round_report/",
                self.admin_site.admin_view(self.pre_round_report_view),
                name="pre_round_report",
            ),
            path(
                "<int:object_id>/export_players/",
                self.admin_site.admin_view(self.export_players_view),
                name="export_players",
            ),
        ]
        return my_urls + urls

    def create_broadcast(self, request, queryset):
        try:
            require(len(queryset) == 1, "Can only create one broadcast at a time.")
            season = queryset[0]
            require(
                season.create_broadcast,
                "create_broadcast is not set for this season.",
            )
            require(
                season.get_broadcast_id() == "",
                "A broadcast for this season already exists.",
            )
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return

        signals.do_create_broadcast.send(sender=self.__class__, season_id=season.pk)
        self.message_user(request, "Trying to create broadcast.", messages.INFO)

    def update_broadcast(self, request, queryset):
        try:
            require(
                len(queryset) == 1,
                "Can only update one broadcast at a time.",
            )
            season = queryset[0]
            require(
                season.get_broadcast_id() != "",
                "Could not find broadcast to update, create one first.",
            )
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return

        signals.do_update_broadcast.send(sender=self.__class__, season_id=season.pk)
        self.message_user(request, "Updating broadcast.", messages.INFO)

    def simulate_tournament(self, request, queryset):
        if not request.user.is_superuser:
            raise PermissionDenied
        if not settings.DEBUG and not settings.STAGING:
            self.message_user(
                request,
                "Results can't be simulated in a live environment",
                messages.ERROR,
            )
            return
        if queryset.count() > 1:
            self.message_user(
                request,
                "Results can only be simulated one season at a time",
                messages.ERROR,
            )
            return
        season = queryset[0]
        simulation.simulate_season(season)
        self.message_user(request, "Simulation complete.", messages.INFO)
        return redirect("admin:tournament_season_changelist")

    def recalculate_scores(self, request, queryset):
        for season in queryset:
            if season.league.competitor_type == "team":
                for team_pairing in TeamPairing.objects.filter(round__season=season):
                    team_pairing.refresh_points()
                    team_pairing.save()
            season.calculate_scores()
        self.message_user(request, "Scores recalculated.", messages.INFO)

    def verify_data(self, request, queryset):
        for season in queryset:
            # Ensure SeasonPlayer objects exist for all paired players
            if season.league.competitor_type == "team":
                pairings = TeamPlayerPairing.objects.filter(
                    team_pairing__round__season=season
                )
            else:
                pairings = LonePlayerPairing.objects.filter(round__season=season)
            for p in pairings:
                SeasonPlayer.objects.get_or_create(season=season, player=p.white)
                SeasonPlayer.objects.get_or_create(season=season, player=p.black)
            # Normalize all gamelinks
            bad_gamelinks = 0
            for p in pairings:
                old = p.game_link
                p.game_link, ok = normalize_gamelink(old)
                if not ok:
                    bad_gamelinks += 1
                if p.game_link != old:
                    p.save()
            if bad_gamelinks > 0:
                self.message_user(
                    request,
                    "%d bad gamelinks for %s." % (bad_gamelinks, season.name),
                    messages.WARNING,
                )
        self.message_user(request, "Data verified.", messages.INFO)

    def review_nominated_games(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Nominated games can only be reviewed one season at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:review_nominated_games", object_id=queryset[0].pk)

    def review_nominated_games_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm(
            "tournament.review_nominated_games", season.league
        ):
            raise PermissionDenied

        selections = GameSelection.objects.filter(season=season).order_by(
            "pairing__teamplayerpairing__board_number"
        )
        nominations = GameNomination.objects.filter(season=season).order_by(
            "pairing__teamplayerpairing__board_number", "date_created"
        )

        selected_links = set((s.game_link for s in selections))

        link_counts = {}
        link_to_nom = {}
        first_nominations = []
        for n in nominations:
            value = link_counts.get(n.game_link, 0)
            if value == 0:
                first_nominations.append(n)
                link_to_nom[n.game_link] = n
            link_counts[n.game_link] = value + 1

        selections = [
            (link_counts.get(s.game_link, 0), s, link_to_nom.get(s.game_link, None))
            for s in selections
        ]
        nominations = [
            (link_counts.get(n.game_link, 0), n)
            for n in first_nominations
            if n.game_link not in selected_links
        ]

        if season.nominations_open:
            self.message_user(
                request,
                "Nominations are still open. You should edit the season and close nominations before reviewing.",
                messages.WARNING,
            )

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Review nominated games",
            "selections": selections,
            "nominations": nominations,
            "is_team": season.league.competitor_type == "team",
        }

        return render(request, "tournament/admin/review_nominated_games.html", context)

    def review_nominated_games_select_view(self, request, object_id, nom_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm(
            "tournament.review_nominated_games", season.league
        ):
            raise PermissionDenied
        nom = get_object_or_404(GameNomination, pk=nom_id)

        GameSelection.objects.get_or_create(
            season=season, game_link=nom.game_link, defaults={"pairing": nom.pairing}
        )

        return redirect("admin:review_nominated_games", object_id=object_id)

    def review_nominated_games_deselect_view(self, request, object_id, sel_id):
        gs = GameSelection.objects.filter(pk=sel_id).first()
        if gs is not None:
            if not request.user.has_perm(
                "tournament.review_nominated_games", gs.season.league
            ):
                raise PermissionDenied
            gs.delete()

        return redirect("admin:review_nominated_games", object_id=object_id)

    def review_nominated_games_pgn_view(self, request, object_id):
        gamelink = request.GET.get("gamelink")
        gameid = get_gameid_from_gamelink(gamelink)
        pgn = lichessapi.get_pgn_with_cache(gameid, priority=10)

        # Strip most tags for "blind" review
        pgn = re.sub(r'\[[^R]\w+ ".*"\]\n', "", pgn)

        return HttpResponse(pgn)

    def round_transition(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Rounds can only be transitioned one season at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:round_transition", object_id=queryset[0].pk)

    def round_transition_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.generate_pairings", season.league):
            raise PermissionDenied

        workflow = RoundTransitionWorkflow(season)

        round_to_close = workflow.round_to_close
        round_to_open = workflow.round_to_open
        season_to_close = workflow.season_to_close

        if request.method == "POST":
            form = forms.RoundTransitionForm(
                season.league.competitor_type == "team",
                round_to_close,
                round_to_open,
                season_to_close,
                request.POST,
            )
            if form.is_valid():
                complete_round = (
                    "round_to_close" in form.cleaned_data
                    and form.cleaned_data["round_to_close"] == round_to_close.number
                    and form.cleaned_data["complete_round"]
                )
                complete_season = (
                    "complete_season" in form.cleaned_data
                    and form.cleaned_data["complete_season"]
                )
                update_board_order = (
                    "round_to_open" in form.cleaned_data
                    and form.cleaned_data["round_to_open"] == round_to_open.number
                    and "update_board_order" in form.cleaned_data
                    and form.cleaned_data["update_board_order"]
                )
                generate_pairings = (
                    "round_to_open" in form.cleaned_data
                    and form.cleaned_data["round_to_open"] == round_to_open.number
                    and form.cleaned_data["generate_pairings"]
                )
                auto_assign_forfeits = (
                    "round_to_open" in form.cleaned_data
                    and form.cleaned_data["round_to_open"] == round_to_open.number
                    and form.cleaned_data.get("auto_assign_forfeits", False)
                )
                publish_immediately = (
                    "round_to_open" in form.cleaned_data
                    and form.cleaned_data["round_to_open"] == round_to_open.number
                    and form.cleaned_data.get("publish_immediately", False)
                )

                msg_list = workflow.run(
                    complete_round=complete_round,
                    complete_season=complete_season,
                    update_board_order=update_board_order,
                    generate_pairings=generate_pairings,
                    auto_assign_forfeits=auto_assign_forfeits,
                    publish_immediately=publish_immediately,
                )

                for text, level in msg_list:
                    self.message_user(request, text, level)

                if generate_pairings:
                    return redirect("admin:review_pairings", round_to_open.pk)
                else:
                    return redirect("admin:tournament_season_changelist")
        else:
            form = forms.RoundTransitionForm(
                season.league.competitor_type == "team",
                round_to_close,
                round_to_open,
                season_to_close,
            )

        for text, level in workflow.warnings:
            self.message_user(request, text, level)

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Round transition",
            "form": form,
        }

        return render(request, "tournament/admin/round_transition.html", context)

    def bulk_email(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request, "Emails can only be sent one season at a time.", messages.ERROR
            )
            return
        return redirect("admin:bulk_email", object_id=queryset[0].pk)

    def generate_invite_codes(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Invite codes can only be generated for one season at a time.",
                messages.ERROR,
            )
            return
        season = queryset[0]
        if season.league.registration_mode != RegistrationMode.INVITE_ONLY:
            self.message_user(
                request,
                f"{season.league.name} is not configured for invite-only registration.",
                messages.ERROR,
            )
            return
        return redirect("admin:generate_invite_codes", object_id=season.pk)

    def bulk_email_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.bulk_email", season.league):
            raise PermissionDenied

        if request.method == "POST":
            form = forms.BulkEmailForm(season.seasonplayer_set.count(), request.POST)
            if form.is_valid() and form.cleaned_data["confirm_send"]:
                season_players = season.seasonplayer_set.all()
                email_addresses = {
                    sp.player.email for sp in season_players if sp.player.email != ""
                }
                email_messages = []
                for addr in email_addresses:
                    message = EmailMultiAlternatives(
                        form.cleaned_data["subject"],
                        form.cleaned_data["text_content"],
                        settings.DEFAULT_FROM_EMAIL,
                        [addr],
                    )
                    message.attach_alternative(
                        form.cleaned_data["html_content"], "text/html"
                    )
                    email_messages.append(message)
                conn = mail.get_connection()
                conn.open()
                conn.send_messages(email_messages)
                conn.close()
                self.message_user(
                    request,
                    "Emails sent to %d players." % len(season_players),
                    messages.INFO,
                )
                return redirect("admin:tournament_season_changelist")
        else:
            form = forms.BulkEmailForm(season.seasonplayer_set.count())

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Bulk email",
            "form": form,
        }

        return render(request, "tournament/admin/bulk_email.html", context)

    def team_spam(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Team spam can only be sent one season at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:team_spam", object_id=queryset[0].pk)

    def team_spam_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.bulk_email", season.league):
            raise PermissionDenied

        if request.method == "POST":
            form = forms.TeamSpamForm(season, request.POST)
            if form.is_valid() and form.cleaned_data["confirm_send"]:
                teams = season.team_set.all()
                for t in teams:
                    if t.slack_channel:
                        slackapi.send_message(
                            t.slack_channel, form.cleaned_data["text"]
                        )
                        time.sleep(1)
                self.message_user(
                    request, "Spam sent to %d teams." % len(teams), messages.INFO
                )
                return redirect("admin:tournament_season_changelist")
        else:
            form = forms.TeamSpamForm(season)

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Team spam",
            "form": form,
        }

        return render(request, "tournament/admin/team_spam.html", context)

    def generate_invite_codes_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.change_season", season.league):
            raise PermissionDenied

        if season.league.registration_mode != RegistrationMode.INVITE_ONLY:
            messages.error(
                request,
                f"{season.league.name} is not configured for invite-only registration.",
            )
            return redirect("admin:tournament_season_changelist")

        # Get existing invite codes statistics
        existing_codes = InviteCode.objects.filter(league=season.league, season=season)
        captain_codes = existing_codes.filter(code_type="captain")
        team_codes = existing_codes.filter(code_type="team_member")

        stats = {
            "total": existing_codes.count(),
            "captain_codes": {
                "total": captain_codes.count(),
                "used": captain_codes.filter(used_by__isnull=False).count(),
                "available": captain_codes.filter(used_by__isnull=True).count(),
            },
            "team_codes": {
                "total": team_codes.count(),
                "used": team_codes.filter(used_by__isnull=False).count(),
                "available": team_codes.filter(used_by__isnull=True).count(),
            },
        }

        if request.method == "POST":
            try:
                count = int(request.POST.get("count", 0))
                code_type = request.POST.get("code_type", "captain")

                if count < 1 or count > 10000:
                    messages.error(request, "Count must be between 1 and 10,000")
                else:
                    codes = InviteCode.create_batch(
                        league=season.league,
                        season=season,
                        count=count,
                        created_by=request.user,
                        code_type=code_type,
                    )
                    messages.success(
                        request,
                        f"Successfully generated {len(codes)} {code_type} invite codes.",
                    )
                    return redirect("admin:tournament_invitecode_changelist")

            except Exception as e:
                messages.error(request, f"Error generating codes: {str(e)}")

        context = {
            "season": season,
            "stats": stats,
            "title": f"Generate Invite Codes - {season}",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
        }

        return render(request, "tournament/admin/generate_invite_codes.html", context)

    def mod_report(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Can only generate mod report one season at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:mod_report", object_id=queryset[0].pk)

    def mod_report_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.change_season", season.league):
            raise PermissionDenied

        season_players = season.seasonplayer_set.select_related("player").nocache()
        players = []
        for sp in season_players:
            games = (
                PlayerPairing.objects.filter(white=sp.player)
                | PlayerPairing.objects.filter(black=sp.player)
            ).nocache()
            game_count = games.count()
            players.append(
                (game_count, sp.player.games_played, sp.player.lichess_username)
            )

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Mod report",
            "players": sorted(players),
        }

        return render(request, "tournament/admin/mod_report.html", context)

    def pre_round_report(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Can only generate pre-round report one season at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:pre_round_report", object_id=queryset[0].pk)

    def pre_round_report_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.change_season", season.league):
            raise PermissionDenied

        last_round = (
            Round.objects.filter(
                season=season, publish_pairings=True, is_completed=False
            )
            .order_by("number")
            .first()
        )
        next_round = (
            Round.objects.filter(
                season=season, publish_pairings=False, is_completed=False
            )
            .order_by("number")
            .first()
        )

        season_players = season.seasonplayer_set.select_related("player").nocache()
        active_players = {sp.player for sp in season_players if sp.is_active}
        withdrawn_players = {
            wd.player for wd in PlayerWithdrawal.objects.filter(round=next_round)
        }
        continuation_players = {
            mr.requester
            for mr in ModRequest.objects.filter(
                round=next_round, type="request_continuation", status="approved"
            )
        }
        red_cards = {
            sp.player for sp in season_players if sp.is_active and sp.games_missed >= 2
        } - withdrawn_players

        missing_withdrawals = None
        pairings_wo_results = None

        pending_regs = [
            (reg.lichess_username, reg)
            for reg in Registration.objects.filter(season=season, status="pending")
        ]

        bad_player_status = [
            p
            for p in (active_players - withdrawn_players)
            if p.account_status != "normal"
        ]

        latereg_list = PlayerLateRegistration.objects.filter(round=next_round)
        not_on_slack = [
            (lr.player, lr, (timezone.now() - lr.date_created).days)
            for lr in latereg_list
            if not lr.player.slack_user_id
        ]
        not_on_slack += [(p, None, None) for p in active_players if not p.slack_user_id]

        pending_mod_reqs = ModRequest.objects.filter(season=season, status="pending")

        if last_round is not None:
            players_with_0f = set()
            for p in last_round.pairings:
                if p.result != "" and not p.game_played():
                    if p.black_score() == 0:
                        players_with_0f.add(p.black)
                    if p.white_score() == 0:
                        players_with_0f.add(p.white)
            missing_withdrawals = sorted(
                (players_with_0f & active_players)
                - withdrawn_players
                - continuation_players
            )

            def text_class(p):
                if p.game_link != "":
                    return "text-approved"
                if p.scheduled_time and p.scheduled_time < timezone.now() - timedelta(
                    hours=1
                ):
                    return "text-rejected"
                return ""

            pairings_wo_results = [
                (p, text_class(p))
                for p in last_round.pairings.order_by(
                    "loneplayerpairing__pairing_order"
                ).filter(result="")
            ]

        ct_pairing = ContentType.objects.get_for_model(PlayerPairing)
        ct_season_player = ContentType.objects.get_for_model(SeasonPlayer)

        def with_round_info(player_list):
            """Annotates a player record with their pairing and comments"""
            if not player_list:
                return None
            retval = []

            for player in player_list:
                pairing = LonePlayerPairing.objects.filter(
                    Q(white=player) | Q(black=player), round=last_round
                ).first()
                season_player = SeasonPlayer.objects.get(player=player, season=season)
                comment_q = Q()
                if pairing is not None:
                    comment_q = comment_q | (
                        Q(content_type=ct_pairing) & Q(object_pk=pairing.pk)
                    )
                if season_player is not None:
                    comment_q = comment_q | (
                        Q(content_type=ct_season_player) & Q(object_pk=season_player.pk)
                    )
                comments = list(Comment.objects.filter(comment_q))
                retval.append((player, pairing, comments))
            return retval

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Pre-round report",
            "last_round": last_round,
            "next_round": next_round,
            "missing_withdrawals": with_round_info(missing_withdrawals),
            "red_cards": with_round_info(sorted(red_cards)),
            "bad_player_status": (
                sorted(bad_player_status) if bad_player_status is not None else None
            ),
            "not_on_slack": sorted(not_on_slack) if not_on_slack is not None else None,
            "pending_mod_reqs": pending_mod_reqs,
            "pending_regs": (
                sorted(pending_regs, key=lambda x: x[0].lower())
                if pending_regs is not None
                else None
            ),
            "pairings_wo_results": pairings_wo_results,
        }

        return render(request, "tournament/admin/pre_round_report.html", context)

    def export_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.change_season", season.league):
            raise PermissionDenied

        players = season.export_players()
        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "Export players",
            "players": json.dumps(players),
        }

        return render(request, "tournament/admin/export_players.html", context)

    def update_board_order_by_rating(self, request, queryset):
        try:
            for season in queryset.all():
                if not request.user.has_perm(
                    "tournament.manage_players", season.league
                ):
                    raise PermissionDenied
                UpdateBoardOrderWorkflow(season).run(alternates_only=False)
            self.message_user(request, "Board order updated.", messages.INFO)
        except IndexError:
            self.message_user(request, "Error updating board order.", messages.ERROR)

    def force_alternate_board_update(self, request, queryset):
        try:
            for season in queryset.all():
                if not request.user.has_perm(
                    "tournament.manage_players", season.league
                ):
                    raise PermissionDenied
                UpdateBoardOrderWorkflow(season).run(alternates_only=True)
            self.message_user(request, "Alternate order updated.", messages.INFO)
        except IndexError:
            self.message_user(
                request, "Error updating alternate order.", messages.ERROR
            )

    def manage_players(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Players can only be managed one season at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:manage_players", object_id=queryset[0].pk)

    def player_info_view(self, request, object_id, player_name):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.manage_players", season.league):
            raise PermissionDenied
        season_player = get_object_or_404(
            SeasonPlayer, season=season, player__lichess_username=player_name
        )
        player = season_player.player

        reg = season_player.registration
        if player.games_played is not None:
            has_played_20_games = not player.provisional_for(season.league)
        else:
            has_played_20_games = reg is not None and reg.has_played_20_games

        context = {
            "season_player": season_player,
            "league": season.league,
            "player": season_player.player,
            "reg": reg,
            "has_played_20_games": has_played_20_games,
        }

        return render(
            request, "tournament/admin/edit_rosters_player_info.html", context
        )

    def create_teams_view(self, request, object_id):
        def insert_teams(teams):
            for team_number, team in enumerate(teams, 1):
                team_instance = Team.objects.create(
                    season=season, number=team_number, name=f"Team {team_number}"
                )
                for board_number, board in enumerate(team.boards, 1):
                    player = Player.objects.get(lichess_username=board.name)
                    TeamMember.objects.create(
                        team=team_instance, player=player, board_number=board_number
                    )

        def insert_alternates(alts_split):
            for board_number, board in enumerate(alts_split, 1):
                for player in board:
                    season_player = SeasonPlayer.objects.get(
                        season=season, player__lichess_username__iexact=player.name
                    )
                    Alternate.objects.create(
                        season_player=season_player, board_number=board_number
                    )

        season = get_object_or_404(Season, pk=object_id)
        season_started = Round.objects.filter(
            season=season, publish_pairings=True
        ).exists()
        if season_started:
            return HttpResponse(status=400)
        team_count = Team.objects.filter(season=season).count()
        if request.method == "POST":
            form = forms.CreateTeamsForm(team_count, request.POST)
            if form.is_valid():
                player_data = [p for p in season.export_players() if p["date_created"]]
                league = teamgen.get_best_league(
                    player_data,
                    season.boards,
                    form.cleaned_data["balance"],
                    form.cleaned_data["count"],
                )

                with reversion.create_revision():
                    reversion.set_user(request.user)
                    reversion.set_comment("Create teams")

                    Team.objects.filter(season=season).delete()
                    insert_teams(league["teams"])

                    Alternate.objects.filter(season_player__season=season).delete()
                    insert_alternates(league["alts_split"])

                return redirect("admin:manage_players", object_id)

        else:
            form = forms.CreateTeamsForm(team_count)

        context = {
            "opts": self.model._meta,
            "season": season,
            "form": form,
            "season_started": season_started,
        }
        return render(request, "tournament/admin/create_teams.html", context)

    def manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        if not request.user.has_perm("tournament.manage_players", season.league):
            raise PermissionDenied
        if season.league.competitor_type == "team":
            return self.team_manage_players_view(request, object_id)
        else:
            return self.lone_manage_players_view(request, object_id)

    def team_manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)
        league = season.league
        teams_locked = Round.objects.filter(
            season=season, publish_pairings=True
        ).exists()

        if request.method == "POST":
            form = forms.EditRostersForm(request.POST)
            if form.is_valid():
                changes = json.loads(form.cleaned_data["changes"])
                has_error = False

                # Group changes by team
                changes_by_team_number = defaultdict(list)
                nonteam_changes = []
                for change in changes:
                    if "team_number" in change:
                        changes_by_team_number[change["team_number"]].append(change)
                    else:
                        nonteam_changes.append(change)

                for _, team_changes in list(changes_by_team_number.items()):
                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        change_descriptions = []
                        for change in team_changes:
                            try:
                                if change["action"] == "change-member":
                                    team_num = change["team_number"]
                                    team = Team.objects.get(
                                        season=season, number=team_num
                                    )

                                    board_num = change["board_number"]
                                    player_info = change["player"]

                                    teammember = TeamMember.objects.filter(
                                        team=team, board_number=board_num
                                    ).first()
                                    original_teammember = str(teammember)
                                    if teammember is None:
                                        teammember = TeamMember(
                                            team=team, board_number=board_num
                                        )
                                    if player_info is None:
                                        teammember.delete()
                                        teammember = None
                                    else:
                                        teammember.player = Player.objects.get(
                                            lichess_username=player_info["name"]
                                        )
                                        teammember.is_captain = player_info[
                                            "is_captain"
                                        ]
                                        teammember.is_vice_captain = player_info[
                                            "is_vice_captain"
                                        ]
                                        teammember.save()

                                    change_descriptions.append(
                                        'changed board %d from "%s" to "%s"'
                                        % (board_num, original_teammember, teammember)
                                    )

                                if (
                                    change["action"] == "change-team"
                                    and not teams_locked
                                ):
                                    team_num = change["team_number"]
                                    team = Team.objects.get(
                                        season=season, number=team_num
                                    )

                                    team_name = change["team_name"]
                                    team.name = team_name
                                    team.save()

                                    change_descriptions.append(
                                        'changed team name to "%s"' % team_name
                                    )

                                if (
                                    change["action"] == "create-team"
                                    and not teams_locked
                                ):
                                    model = change["model"]
                                    team = Team.objects.create(
                                        season=season,
                                        number=model["number"],
                                        name=model["name"],
                                    )

                                    for board_num, player_info in enumerate(
                                        model["boards"], 1
                                    ):
                                        if player_info is not None:
                                            player = Player.objects.get(
                                                lichess_username=player_info["name"]
                                            )
                                            is_captain = player_info["is_captain"]
                                            with reversion.create_revision():
                                                TeamMember.objects.create(
                                                    team=team,
                                                    player=player,
                                                    board_number=board_num,
                                                    is_captain=is_captain,
                                                )

                                    change_descriptions.append(
                                        'created team "%s"' % model["name"]
                                    )
                            except Exception:
                                has_error = True
                        reversion.set_comment(
                            "Edit rosters - %s." % ", ".join(change_descriptions)
                        )

                for change in nonteam_changes:
                    try:
                        if change["action"] == "create-alternate":
                            with reversion.create_revision():
                                reversion.set_user(request.user)
                                reversion.set_comment(
                                    "Edit rosters - created alternate."
                                )

                                board_num = change["board_number"]
                                season_player = SeasonPlayer.objects.get(
                                    season=season,
                                    player__lichess_username__iexact=change[
                                        "player_name"
                                    ],
                                )
                                (
                                    Alternate.objects.update_or_create(
                                        season_player=season_player,
                                        defaults={"board_number": board_num},
                                    )
                                )

                        if change["action"] == "delete-alternate":
                            with reversion.create_revision():
                                reversion.set_user(request.user)
                                reversion.set_comment(
                                    "Edit rosters - deleted alternate."
                                )

                                board_num = change["board_number"]
                                season_player = SeasonPlayer.objects.get(
                                    season=season,
                                    player__lichess_username__iexact=change[
                                        "player_name"
                                    ],
                                )
                                alt = Alternate.objects.filter(
                                    season_player=season_player, board_number=board_num
                                ).first()
                                if alt is not None:
                                    alt.delete()

                    except Exception:
                        has_error = True

                if has_error:
                    self.message_user(
                        request, "Some changes could not be saved.", messages.WARNING
                    )

                if "save_continue" in form.data:
                    return redirect("admin:manage_players", object_id)
                return redirect("admin:tournament_season_changelist")
        else:
            form = forms.EditRostersForm()

        if not season.boards:
            self.message_user(
                request,
                "Number of boards must be specified for %s" % season.name,
                messages.ERROR,
            )
            return redirect("admin:tournament_season_changelist")
        board_numbers = list(range(1, season.boards + 1))
        teams = list(
            Team.objects.filter(season=season)
            .order_by("number")
            .prefetch_related(
                Prefetch(
                    "teammember_set",
                    queryset=TeamMember.objects.select_related("player").nocache(),
                )
            )
            .nocache()
        )
        team_members = (
            TeamMember.objects.filter(team__season=season)
            .select_related("player")
            .nocache()
        )
        alternates = (
            Alternate.objects.filter(season_player__season=season)
            .select_related("season_player__player")
            .nocache()
        )
        alternates_by_board = [
            (
                n,
                sorted(
                    alternates.filter(board_number=n)
                    .select_related("season_player__registration")
                    .nocache(),
                    key=lambda alt: alt.priority_date(),
                ),
            )
            for n in board_numbers
        ]

        season_player_objs = (
            SeasonPlayer.objects.filter(season=season, is_active=True)
            .select_related("player", "registration")
            .nocache()
        )
        season_players = set(sp.player for sp in season_player_objs)
        team_players = set(tm.player for tm in team_members)
        alternate_players = set(alt.season_player.player for alt in alternates)
        old_alternates = season.last_season_alternates()

        alternate_buckets = list(AlternateBucket.objects.filter(season=season))
        unassigned_players = list(
            sorted(
                season_players - team_players - alternate_players,
                key=lambda p: p.rating_for(league),
                reverse=True,
            )
        )
        if len(alternate_buckets) == season.boards:
            # Sort unassigned players by alternate buckets
            unassigned_by_board = [
                (
                    n,
                    [
                        p
                        for p in unassigned_players
                        if find(alternate_buckets, board_number=n).contains(
                            p.rating_for(league)
                        )
                    ],
                )
                for n in board_numbers
            ]
        else:
            # Season doesn't have buckets yet. Sort by player soup
            sorted_players = list(
                sorted(
                    (p for p in season_players if p.rating_for(league) is not None),
                    key=lambda p: p.rating_for(league),
                    reverse=True,
                )
            )
            player_count = len(sorted_players)
            unassigned_by_board = [(n, []) for n in board_numbers]
            if player_count > 0:
                max_ratings = [
                    (
                        n,
                        sorted_players[
                            len(sorted_players) * (n - 1) // season.boards
                        ].rating_for(league),
                    )
                    for n in board_numbers
                ]
                for p in unassigned_players:
                    board_num = 1
                    for n, max_rating in max_ratings:
                        if p.rating_for(league) <= max_rating:
                            board_num = n
                        else:
                            break
                    unassigned_by_board[board_num - 1][1].append(p)

        if teams_locked:
            new_team_number = None
        elif len(teams) == 0:
            new_team_number = 1
        else:
            new_team_number = teams[-1].number + 1

        # Player highlights
        red_players = set()
        blue_players = set()
        green_players = set()
        purple_players = set()
        for sp in season_player_objs:
            reg = sp.registration
            if sp.player.provisional_for(league):
                red_players.add(sp.player)
            if not sp.player.slack_user_id:
                red_players.add(sp.player)
            if sp.games_missed >= 2:
                red_players.add(sp.player)
            if sp.player.account_status != "normal":
                red_players.add(sp.player)
            if reg is not None and reg.alternate_preference == "alternate":
                blue_players.add(sp.player)
            if reg is not None and reg.alternate_preference == "either":
                green_players.add(sp.player)
            if sp.player in old_alternates:
                purple_players.add(sp.player)

        season_started = Round.objects.filter(
            season=season, publish_pairings=True
        ).exists()

        context = {
            "season_started": season_started,
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "league": league,
            "original": season,
            "title": "Edit rosters",
            "form": form,
            "teams": teams,
            "teams_locked": teams_locked,
            "new_team_number": new_team_number,
            "alternates_by_board": alternates_by_board,
            "unassigned_by_board": unassigned_by_board,
            "board_numbers": board_numbers,
            "board_count": season.boards,
            "red_players": red_players,
            "blue_players": blue_players,
            "green_players": green_players,
            "purple_players": purple_players,
        }
        if teams:
            context.update(
                {
                    "team_rating_variance": team_rating_variance(teams),
                    "team_rating_range": team_rating_range(teams),
                }
            )
        return render(request, "tournament/admin/edit_rosters.html", context)

    def lone_manage_players_view(self, request, object_id):
        season = get_object_or_404(Season, pk=object_id)

        active_players = SeasonPlayer.objects.filter(
            season=season, is_active=True
        ).order_by("player__lichess_username")
        inactive_players = SeasonPlayer.objects.filter(
            season=season, is_active=False
        ).order_by("player__lichess_username")

        projected_active = {sp.player for sp in active_players}

        def get_data(r):
            regs = r.playerlateregistration_set.order_by("player__lichess_username")
            wds = r.playerwithdrawal_set.order_by("player__lichess_username")

            if not r.publish_pairings:
                for reg in regs:
                    projected_active.add(reg.player)
                for wd in wds:
                    try:
                        projected_active.remove(wd.player)
                    except KeyError:
                        pass

            byes = r.playerbye_set.order_by("player__lichess_username")
            players_with_byes = {b.player for b in byes}

            def show(avail):
                return (
                    avail.player in projected_active
                    and avail.player not in players_with_byes
                )

            unavailables = [
                avail
                for avail in r.playeravailability_set.filter(
                    is_available=False
                ).order_by("player__lichess_username")
                if show(avail)
            ]

            return r, regs, wds, byes, unavailables

        rounds = Round.objects.filter(season=season, is_completed=False).order_by(
            "number"
        )
        round_data = [get_data(r) for r in rounds]

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": season,
            "title": "",
            "active_players": active_players,
            "inactive_players": inactive_players,
            "round_data": round_data,
            "league": season.league,
        }

        return render(request, "tournament/admin/manage_lone_players.html", context)


@admin.register(Round)
class RoundAdmin(_BaseAdmin):
    list_display = (
        "__str__",
        "season",
        "get_league",
        "knockout_stage",
        "is_knockout_multi_round",
    )
    list_filter = (
        "season",
        "season__league",
        "knockout_stage",
        "is_knockout_multi_round",
    )
    actions = [
        "generate_pairings",
        "simulate_results",
        "create_broadcast_round",
        "update_broadcast_round",
        "start_games",
        "start_clocks",
        "validate_tokens",
        "advance_knockout_tournament_action",
    ]
    league_id_field = "season__league_id"
    search_fields = ["season__tag"]

    fieldsets = (
        (
            "Round Details",
            {"fields": ("season", "number", "start_date", "end_date", "bulk_id")},
        ),
        (
            "Status",
            {"fields": ("publish_pairings", "is_completed")},
        ),
        (
            "Knockout Settings",
            {
                "fields": (
                    "knockout_stage",
                    "is_knockout_multi_round",
                    "knockout_multi_round_group",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        # Use select_related to fetch season and league in a single query
        return qs.select_related("season", "season__league")

    def get_league(self, obj):
        return obj.season.league

    get_league.short_description = "League"
    get_league.admin_order_field = "season__league"

    def get_urls(self):
        urls = super(RoundAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/generate_pairings/",
                self.admin_site.admin_view(self.generate_pairings_view),
                name="generate_pairings",
            ),
            path(
                "<int:object_id>/review_pairings/",
                self.admin_site.admin_view(self.review_pairings_view),
                name="review_pairings",
            ),
        ]
        return my_urls + urls

    def create_broadcast_round(self, request, queryset):
        try:
            require(
                len(queryset) == 1,
                "Can only create one broadcast round at a time.",
            )
            round_ = queryset[0]
            require(
                round_.get_broadcast_id() != "",
                "Could not find broadcast for season, create it first.",
            )
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return

        signals.do_create_broadcast_round.send(
            sender=self.__class__, round_id=round_.pk
        )
        self.message_user(request, "Trying to create broadcast round.", messages.INFO)

    def update_broadcast_round(self, request, queryset):
        try:
            require(
                len(queryset) == 1, "Can only update one broadcast round at a time."
            )
            round_ = queryset[0]
            require(
                round_.get_broadcast_id() != "",
                "Could not find broadcast for season, create one first.",
            )
            bcrid = round_.get_broadcast_round_id()
            require(
                bcrid != "",
                "Could not find broadcast round to update, create one first.",
            )
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return

        signals.do_update_broadcast_round.send(
            sender=self.__class__, round_id=round_.pk
        )
        self.message_user(request, "Updating broadcast round.", messages.INFO)

    def generate_pairings(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Pairings can only be generated one round at a time",
                messages.ERROR,
            )
            return
        return redirect("admin:generate_pairings", object_id=queryset[0].pk)

    def simulate_results(self, request, queryset):
        if not settings.DEBUG and not settings.STAGING:
            self.message_user(
                request,
                "Results can't be simulated in a live environment",
                messages.ERROR,
            )
            return
        if queryset.count() > 1:
            self.message_user(
                request,
                "Results can only be simulated one round at a time",
                messages.ERROR,
            )
            return
        round_ = queryset[0]
        simulation.simulate_round(round_)
        self.message_user(request, "Simulation complete.", messages.INFO)
        return redirect("admin:tournament_round_changelist")

    def start_games(self, request, queryset):
        try:
            require(len(queryset) == 1, "Can only start games one round at a time.")
            round_ = queryset[0]
            require(
                not round_.is_player_scheduled_league(),
                "Attempting to start games for a scheduling league."
                " Change league setting first.",
            )
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return
        self.message_user(request, "Attempting to start games.", messages.INFO)
        signals.do_start_unscheduled_games.send(sender=request.user, round_id=round_.pk)

    def start_clocks(self, request, queryset):
        try:
            require(
                len(queryset) == 1,
                "Starting the clock for more than one round at a time is currently not possible.",
            )
            round_ = queryset[0]
            require(
                not round_.is_player_scheduled_league(),
                "This round is part of a league where players schedule themselves.\n"
                "Change the 'scheduling' league setting to enable starting clocks.",
            )
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return
        self.message_user(request, "Attempting to start clocks.", messages.INFO)
        signals.do_start_clocks.send(sender=request.user, round_id=round_.pk)

    def validate_tokens(self, request, queryset):
        try:
            require(
                len(queryset) == 1,
                "Can only validate tokens for one round at a time.",
            )
            round_ = queryset[0]
        except PreconditionError as e:
            self.message_user(request, str(e), messages.ERROR)
            return
        signals.do_validate_season_tokens.send(
            sender=request.user, season_id=round_.season_id
        )
        self.message_user(
            request,
            "Token validation started. Check the dashboard for results.",
            messages.INFO,
        )

    validate_tokens.short_description = "Validate player OAuth tokens"

    def advance_knockout_tournament_action(self, request, queryset):
        """Advance knockout tournament to next round based on current round results."""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one round to advance from.",
                messages.ERROR,
            )
            return

        round_ = queryset.first()

        # Check if this is a knockout tournament
        if round_.season.league.pairing_type not in [
            "knockout-single",
            "knockout-multi",
        ]:
            self.message_user(
                request,
                f"Round {round_} is not part of a knockout tournament.",
                messages.ERROR,
            )
            return

        # Check if round is completed
        if not round_.is_completed:
            self.message_user(
                request,
                f"Round {round_} is not marked as completed. Complete the round first.",
                messages.ERROR,
            )
            return

        try:
            # Import here to avoid circular imports
            from heltour.tournament.pairinggen import advance_knockout_tournament

            next_round = advance_knockout_tournament(round_)

            if next_round:
                self.message_user(
                    request,
                    f"Successfully advanced to round {next_round.number} "
                    f"({next_round.knockout_stage}). "
                    f"Pairings have been generated.",
                    messages.SUCCESS,
                )
            else:
                self.message_user(
                    request,
                    f"Tournament complete! {round_.knockout_stage} was the final round.",
                    messages.SUCCESS,
                )

                # Mark bracket as completed
                try:
                    from heltour.tournament.models import KnockoutBracket

                    bracket = KnockoutBracket.objects.get(season=round_.season)
                    bracket.is_completed = True
                    bracket.save()
                except KnockoutBracket.DoesNotExist:
                    pass

        except Exception as e:
            self.message_user(
                request,
                f"Error advancing knockout tournament: {str(e)}",
                messages.ERROR,
            )

    advance_knockout_tournament_action.short_description = (
        "Advance knockout tournament to next round"
    )

    def generate_pairings_view(self, request, object_id):
        round_ = get_object_or_404(Round, pk=object_id)
        if not request.user.has_perm(
            "tournament.generate_pairings", round_.season.league
        ):
            raise PermissionDenied

        if request.method == "POST":
            form = forms.GeneratePairingsForm(request.POST)
            if form.is_valid():
                try:
                    if form.cleaned_data["run_in_background"]:
                        signals.do_generate_pairings.send(
                            sender=self.__class__,
                            round_id=round_.pk,
                            overwrite=form.cleaned_data["overwrite_existing"],
                            auto_assign_forfeits=form.cleaned_data.get(
                                "auto_assign_forfeits", False
                            ),
                            publish_immediately=form.cleaned_data.get(
                                "publish_immediately", False
                            ),
                        )
                        self.message_user(
                            request, "Generating pairings in background.", messages.INFO
                        )
                        return redirect("admin:review_pairings", object_id)
                    else:
                        pairinggen.generate_pairings(
                            round_, overwrite=form.cleaned_data["overwrite_existing"]
                        )

                        # Handle automatic forfeit assignment
                        forfeit_count = 0
                        if form.cleaned_data.get("auto_assign_forfeits", False):
                            forfeit_count = pairinggen.assign_automatic_forfeits(round_)
                            if forfeit_count > 0:
                                self.message_user(
                                    request,
                                    f"Assigned {forfeit_count} automatic forfeit results.",
                                    messages.INFO,
                                )

                        # Handle immediate publishing
                        publish_immediately = form.cleaned_data.get(
                            "publish_immediately", False
                        )

                        with reversion.create_revision():
                            reversion.set_user(request.user)
                            reversion.set_comment("Generated pairings.")
                            round_.publish_pairings = publish_immediately
                            round_.save()

                        if publish_immediately:
                            self.message_user(
                                request,
                                "Pairings generated and published.",
                                messages.INFO,
                            )
                        else:
                            self.message_user(
                                request, "Pairings generated.", messages.INFO
                            )
                        return redirect("admin:review_pairings", object_id)
                except pairinggen.PairingsExistException:
                    if not round_.publish_pairings:
                        self.message_user(
                            request,
                            "Unpublished pairings already exist.",
                            messages.WARNING,
                        )
                        return redirect("admin:review_pairings", object_id)
                    self.message_user(
                        request,
                        "Pairings already exist for the selected round.",
                        messages.ERROR,
                    )
                except pairinggen.PairingHasResultException:
                    self.message_user(
                        request,
                        "Pairings with results can't be overwritten.",
                        messages.ERROR,
                    )
                except pairinggen.PairingGenerationException as e:
                    self.message_user(
                        request, "Error generating pairings. %s" % e, messages.ERROR
                    )
                return redirect("admin:generate_pairings", object_id=round_.pk)
        else:
            form = forms.GeneratePairingsForm()

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": round_,
            "title": "Generate pairings",
            "form": form,
        }

        return render(request, "tournament/admin/generate_pairings.html", context)

    def review_pairings_view(self, request, object_id):
        round_ = get_object_or_404(Round, pk=object_id)
        if not request.user.has_perm(
            "tournament.generate_pairings", round_.season.league
        ):
            raise PermissionDenied

        if request.method == "POST":
            form = forms.ReviewPairingsForm(request.POST)
            if form.is_valid():
                if "publish" in form.data:
                    signals.do_schedule_publish.send(
                        sender=self, round_id=round_.id, eta=timezone.now()
                    )
                    self.message_user(request, "Pairings published.", messages.INFO)
                elif "schedule" in form.data:
                    publish_time = max(round_.start_date, timezone.now())
                    signals.do_schedule_publish.send(
                        sender=self, round_id=round_.id, eta=publish_time
                    )
                    self.message_user(
                        request,
                        "Pairings scheduled to be published in %d minutes."
                        % ((publish_time - timezone.now()).total_seconds() / 60),
                        messages.INFO,
                    )
                elif "delete" in form.data:
                    try:
                        # Note: no reversion required for deleting things
                        pairinggen.delete_pairings(round_)
                        self.message_user(request, "Pairings deleted.", messages.INFO)
                    except pairinggen.PairingHasResultException:
                        self.message_user(
                            request,
                            "Pairings with results can't be deleted.",
                            messages.ERROR,
                        )
                return redirect("admin:tournament_round_changelist")
        else:
            form = forms.ReviewPairingsForm()

        if round_.season.league.competitor_type == "team":
            team_pairings = round_.teampairing_set.order_by("pairing_order")
            pairing_lists = [
                team_pairing.teamplayerpairing_set.order_by("board_number").nocache()
                for team_pairing in team_pairings
            ]
            context = {
                "has_permission": True,
                "opts": self.model._meta,
                "site_url": "/",
                "original": round_,
                "title": "Review pairings",
                "form": form,
                "pairing_lists": pairing_lists,
            }
            return render(
                request, "tournament/admin/review_team_pairings.html", context
            )
        else:
            pairings = round_.loneplayerpairing_set.order_by("pairing_order").nocache()
            byes = round_.playerbye_set.order_by(
                "type", "player_rank", "player__lichess_username"
            )
            next_pairing_order = 0
            for p in pairings:
                next_pairing_order = max(next_pairing_order, p.pairing_order + 1)

            # Find duplicate players
            player_refcounts = {}
            for p in pairings:
                player_refcounts[p.white] = player_refcounts.get(p.white, 0) + 1
                player_refcounts[p.black] = player_refcounts.get(p.black, 0) + 1
            for b in byes:
                player_refcounts[b.player] = player_refcounts.get(b.player, 0) + 1
            duplicate_players = {k for k, v in list(player_refcounts.items()) if v > 1}

            active_players = {
                sp.player
                for sp in SeasonPlayer.objects.filter(
                    season=round_.season, is_active=True
                )
            }

            def pairing_error(pairing):
                if not request.user.is_staff:
                    return None
                if pairing.white is None or pairing.black is None:
                    return "Missing player"
                if pairing.white in duplicate_players:
                    return "Duplicate player: %s" % pairing.white.lichess_username
                if pairing.black in duplicate_players:
                    return "Duplicate player: %s" % pairing.black.lichess_username
                if not round_.is_completed and pairing.white not in active_players:
                    return "Inactive player: %s" % pairing.white.lichess_username
                if not round_.is_completed and pairing.black not in active_players:
                    return "Inactive player: %s" % pairing.black.lichess_username
                return None

            def bye_error(bye):
                if not request.user.is_staff:
                    return None
                if bye.player in duplicate_players:
                    return "Duplicate player: %s" % bye.player.lichess_username
                if not round_.is_completed and bye.player not in active_players:
                    return "Inactive player: %s" % bye.player.lichess_username
                return None

            # Add errors
            pairings = [(p, pairing_error(p)) for p in pairings]
            byes = [(b, bye_error(b)) for b in byes]

            context = {
                "has_permission": True,
                "opts": self.model._meta,
                "site_url": "/",
                "original": round_,
                "title": "Review pairings",
                "form": form,
                "pairings": pairings,
                "byes": byes,
                "round_": round_,
                "league": round_.season.league,
                "next_pairing_order": next_pairing_order,
            }
            return render(
                request, "tournament/admin/review_lone_pairings.html", context
            )


# -------------------------------------------------------------------------------
@admin.register(PlayerLateRegistration)
class PlayerLateRegistrationAdmin(_BaseAdmin):
    list_display = ("__str__", "retroactive_byes", "late_join_points")
    search_fields = ("player__lichess_username",)
    list_filter = ("round__season", "round__number")
    raw_id_fields = ("round", "player")
    autocomplete_fields = ("round", "player")
    actions = ["refresh_fields", "move_to_next_round"]
    league_id_field = "round__season__league_id"
    league_competitor_type = "individual"

    def get_urls(self):
        urls = super(PlayerLateRegistrationAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/move_latereg/",
                self.admin_site.admin_view(self.move_latereg_view),
                name="move_latereg",
            ),
        ]
        return my_urls + urls

    def refresh_fields(self, request, queryset):
        for reg in queryset.all():
            wf = RefreshLateRegWorkflow(reg)
            wf.run()
        self.message_user(request, "Fields updated.", messages.INFO)
        return redirect("admin:tournament_playerlateregistration_changelist")

    def move_to_next_round(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Late registrations can only be moved one at a time.",
                messages.ERROR,
            )
            return
        return redirect("admin:move_latereg", object_id=queryset[0].pk)

    def move_latereg_view(self, request, object_id):
        reg = get_object_or_404(PlayerLateRegistration, pk=object_id)
        if not request.user.has_perm(
            "tournament.change_playerlateregistration", reg.round.season.league
        ):
            raise PermissionDenied

        workflow = MoveLateRegWorkflow(reg)

        if request.method == "POST":
            form = forms.MoveLateRegForm(request.POST, reg=reg)
            if form.is_valid():
                update_fields = form.cleaned_data["update_fields"]
                prev_round = form.cleaned_data["prev_round"]
                if prev_round == reg.round.number:
                    workflow.run(update_fields)
                    reg.refresh_from_db()
                    self.message_user(
                        request,
                        "Late reg moved to round %d." % (reg.round.number),
                        messages.INFO,
                    )
                return redirect("admin:tournament_playerlateregistration_changelist")
        else:
            form = forms.MoveLateRegForm(reg=reg)

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": reg,
            "title": "Move late registration",
            "form": form,
            "next_round": workflow.next_round,
        }

        return render(request, "tournament/admin/move_latereg.html", context)


# -------------------------------------------------------------------------------
@admin.register(PlayerWithdrawal)
class PlayerWithdrawalAdmin(_BaseAdmin):
    list_display = ("__str__",)
    search_fields = ("player__lichess_username",)
    list_filter = ("round__season", "round__number")
    raw_id_fields = ("round", "player")
    autocomplete_fields = ("round", "player")
    league_id_field = "round__season__league_id"
    league_competitor_type = "individual"


# -------------------------------------------------------------------------------
@admin.register(PlayerBye)
class PlayerByeAdmin(_BaseAdmin):
    list_display = ("__str__", "type")
    search_fields = ("player__lichess_username",)
    list_filter = ("round__season", "round__number", "type")
    raw_id_fields = ("round", "player")
    autocomplete_fields = ("round", "player")
    exclude = ("player_rating",)
    league_id_field = "round__season__league_id"
    league_competitor_type = "individual"


# -------------------------------------------------------------------------------
@admin.register(TeamBye)
class TeamByeAdmin(_BaseAdmin):
    list_display = ("__str__", "type")
    search_fields = ("team__name",)
    list_filter = ("round__season", "round__number", "type")
    raw_id_fields = ("round", "team")
    autocomplete_fields = ("round", "team")
    league_id_field = "round__season__league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(PlayerWarning)
class PlayerWarningAdmin(_BaseAdmin):
    list_display = ("__str__", "type")
    search_fields = ("player__lichess_username",)
    list_filter = ("round__season", "round__number", "type")
    raw_id_fields = ("round", "player")
    autocomplete_fields = ("round", "player")
    league_id_field = "round__season__league_id"
    league_competitor_type = "individual"


# -------------------------------------------------------------------------------
@admin.register(Player)
class PlayerAdmin(_BaseAdmin):
    # NOTE: because autocomplete_fields on other models reference this
    #       we have to define this one and the method below.
    search_fields = ["lichess_username", "slack_user_id"]
    list_filter = ("is_active",)
    readonly_fields = (
        "games_played",
        "slack_user_id",
        "timezone_offset",
        "account_status",
    )
    exclude = ("profile", "fide_profile", "oauth_token")
    actions = ["update_selected_player_ratings"]

    def get_fields(self, request, obj=None):
        return self.remove_email_if_no_dox(
            request.user, super().get_fields(request, obj)
        )

    def get_search_fields(self, request):
        return self.remove_email_if_no_dox(request.user, self.search_fields + ["email"])

    def has_delete_permission(self, request, obj=None):
        # Don't let unprivileged users delete players
        return self.has_assigned_perm(request.user, "delete")

    def get_readonly_fields(self, request, obj=None):
        fields = []
        if not request.user.has_perm("tournament.change_player_details"):
            fields += ("lichess_username", "email", "is_active")
        fields += ["games_played"]
        if not request.user.has_perm("tournament.link_slack"):
            fields += ["slack_user_id"]
        fields += ["timezone_offset", "account_status"]
        return fields

    def update_selected_player_ratings(self, request, queryset):
        #         try:
        usernames = [p.lichess_username for p in queryset.all()]
        for user_meta in lichessapi.enumerate_user_metas(usernames, priority=1):
            p = Player.objects.get(lichess_username__iexact=user_meta["id"])
            p.update_profile(user_meta)
        self.message_user(request, "Rating(s) updated", messages.INFO)

    #         except:
    #             self.message_user(request, 'Error updating rating(s) from lichess API', messages.ERROR)

    def related_objects_for_comments(self, request, object_id):
        sps = (
            SeasonPlayer.objects.filter(
                player_id=object_id,
                season__league_id__in=self.authorized_leagues(request.user),
            )
            .select_related("season")
            .nocache()
        )
        return [(sp.season.name, sp) for sp in sps]


# -------------------------------------------------------------------------------
@admin.register(LeagueModerator)
class LeagueModeratorAdmin(_BaseAdmin):
    list_display = ("__str__", "is_active", "send_contact_emails")
    search_fields = ("player__lichess_username",)
    list_filter = ("league",)
    raw_id_fields = ("player",)
    autocomplete_fields = ("player",)
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
class TeamMemberInline(admin.TabularInline):
    model = TeamMember
    extra = 0
    ordering = ("board_number",)
    raw_id_fields = ("player",)
    autocomplete_fields = ("player",)
    exclude = ("player_rating",)


# -------------------------------------------------------------------------------
@admin.register(Team)
class TeamAdmin(_BaseAdmin):
    list_display = ("name", "season", "manage_link")
    search_fields = ("name",)
    list_filter = ("season",)
    inlines = [TeamMemberInline]
    actions = [
        "update_board_order_by_rating",
        "create_slack_channels",
        "generate_team_invite_codes",
        "copy_teams_to_new_season",
        "move_teams_to_new_season",
    ]
    league_id_field = "season__league_id"
    league_competitor_type = "team"

    def manage_link(self, obj):
        url = reverse(
            "by_league:by_season:team_manage",
            args=[obj.season.league.tag, obj.season.tag, obj.number],
        )
        return format_html('<a href="{}" target="_blank">Manage</a>', url)

    manage_link.short_description = "Manage"

    def update_board_order_by_rating(self, request, queryset):
        for team in queryset.all():
            if not request.user.has_perm(
                "tournament.manage_players", team.season.league
            ):
                raise PermissionDenied
            members = team.teammember_set.order_by("-player__rating")
            for i in range(len(members)):
                members[i].board_number = i + 1
                members[i].save()
        self.message_user(request, "Board order updated", messages.INFO)

    def create_slack_channels(self, request, queryset):
        team_ids = []
        skipped = 0
        for team in queryset.select_related("season").nocache():
            if not team.season.is_active or team.season.is_completed:
                self.message_user(
                    request,
                    "The team season must be active and not completed in order to create channels.",
                    messages.ERROR,
                )
                return
            if len(team.season.tag) > 3:
                self.message_user(
                    request,
                    "The team season tag is too long to create a channel.",
                    messages.ERROR,
                )
                return
            if team.slack_channel == "":
                team_ids.append(team.pk)
            else:
                skipped += 1
        signals.do_create_team_channel.send(sender=self, team_ids=team_ids)
        self.message_user(
            request,
            "Creating %d channels. %d skipped." % (len(team_ids), skipped),
            messages.INFO,
        )

    def generate_team_invite_codes(self, request, queryset):
        if queryset.count() > 1:
            self.message_user(
                request,
                "Invite codes can only be generated for one team at a time.",
                messages.ERROR,
            )
            return
        team = queryset[0]
        if team.season.league.registration_mode != RegistrationMode.INVITE_ONLY:
            self.message_user(
                request,
                f"{team.season.league.name} is not configured for invite-only registration.",
                messages.ERROR,
            )
            return
        return redirect("admin:generate_team_invite_codes", object_id=team.pk)

    def copy_teams_to_new_season(self, request, queryset):
        team_ids = [str(team.id) for team in queryset]
        from django.urls import reverse
        from urllib.parse import urlencode

        base_url = reverse("admin:copy_teams_to_season")
        query_string = urlencode({"team_ids": ",".join(team_ids)})
        return redirect(f"{base_url}?{query_string}")

    def move_teams_to_new_season(self, request, queryset):
        team_ids = [str(team.id) for team in queryset]
        from django.urls import reverse
        from urllib.parse import urlencode

        base_url = reverse("admin:move_teams_to_season")
        query_string = urlencode({"team_ids": ",".join(team_ids)})
        return redirect(f"{base_url}?{query_string}")

    def get_urls(self):
        urls = super(TeamAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/generate_team_invite_codes/",
                self.admin_site.admin_view(self.generate_team_invite_codes_view),
                name="generate_team_invite_codes",
            ),
            path(
                "copy_teams_to_season/",
                self.admin_site.admin_view(self.copy_teams_to_season_view),
                name="copy_teams_to_season",
            ),
            path(
                "move_teams_to_season/",
                self.admin_site.admin_view(self.move_teams_to_season_view),
                name="move_teams_to_season",
            ),
        ]
        return my_urls + urls

    def generate_team_invite_codes_view(self, request, object_id):
        team = get_object_or_404(Team, pk=object_id)

        # Check if user is captain of this team
        is_captain = TeamMember.objects.filter(
            team=team,
            player__lichess_username__iexact=request.user.username,
            is_captain=True,
        ).exists()

        if not is_captain and not request.user.has_perm(
            "tournament.change_team", team.season.league
        ):
            raise PermissionDenied

        # Get existing team invite codes
        existing_codes = InviteCode.objects.filter(
            league=team.season.league,
            season=team.season,
            code_type="team_member",
            team=team,
        )

        stats = {
            "total": existing_codes.count(),
            "used": existing_codes.filter(used_by__isnull=False).count(),
            "available": existing_codes.filter(used_by__isnull=True).count(),
        }

        # Calculate maximum allowed codes (2x board count)
        max_boards = team.season.boards
        max_codes = max_boards * 2
        remaining_allowed = max(0, max_codes - existing_codes.count())

        if request.method == "POST":
            try:
                count = int(request.POST.get("count", 0))

                if count < 1:
                    messages.error(request, "Count must be at least 1")
                elif count > remaining_allowed:
                    messages.error(
                        request,
                        f"You can only generate {remaining_allowed} more codes (maximum {max_codes} total)",
                    )
                else:
                    codes = InviteCode.create_batch(
                        league=team.season.league,
                        season=team.season,
                        count=count,
                        created_by=request.user,
                        code_type="team_member",
                        team=team,
                    )
                    messages.success(
                        request,
                        f"Successfully generated {len(codes)} team member invite codes.",
                    )
                    return redirect("admin:tournament_invitecode_changelist")

            except Exception as e:
                messages.error(request, f"Error generating codes: {str(e)}")

        context = {
            "team": team,
            "stats": stats,
            "max_codes": max_codes,
            "remaining_allowed": remaining_allowed,
            "title": f"Generate Team Member Invite Codes - {team.name}",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
        }

        return render(
            request, "tournament/admin/generate_team_invite_codes.html", context
        )

    def copy_teams_to_season_view(self, request):
        team_ids_param = request.GET.get("team_ids", "")
        if not team_ids_param:
            messages.error(request, "No teams selected")
            return redirect("admin:tournament_team_changelist")

        try:
            team_ids = [
                int(id.strip()) for id in team_ids_param.split(",") if id.strip()
            ]
        except ValueError:
            messages.error(request, "Invalid team IDs")
            return redirect("admin:tournament_team_changelist")

        teams = Team.objects.filter(id__in=team_ids).select_related(
            "season", "season__league"
        )
        if not teams.exists():
            messages.error(request, "No valid teams found")
            return redirect("admin:tournament_team_changelist")

        # Get compatible seasons (team leagues with same number of boards)
        source_boards = teams.first().season.boards
        available_seasons = Season.objects.filter(
            league__competitor_type="team", boards=source_boards
        ).order_by("-start_date")

        if request.method == "POST":
            target_season_id = request.POST.get("target_season")
            if not target_season_id:
                messages.error(request, "Please select a target season")
            else:
                try:
                    target_season = Season.objects.get(
                        id=target_season_id,
                        league__competitor_type="team",
                        boards=source_boards,
                    )

                    # Check permission for target season
                    if not request.user.has_perm(
                        "tournament.manage_players", target_season.league
                    ):
                        raise PermissionDenied(
                            "You don't have permission to manage teams in the target season"
                        )

                    copied_count = self._copy_teams(teams, target_season, request.user)
                    messages.success(
                        request,
                        f"Successfully copied {copied_count} teams to {target_season}",
                    )
                    return redirect("admin:tournament_team_changelist")
                except Season.DoesNotExist:
                    messages.error(request, "Invalid target season")
                except PermissionDenied as e:
                    messages.error(request, str(e))
                except Exception as e:
                    messages.error(request, f"Error copying teams: {str(e)}")

        context = {
            "teams": teams,
            "available_seasons": available_seasons,
            "title": "Copy Teams to New Season",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
        }

        return render(request, "tournament/admin/copy_teams_to_season.html", context)

    def _copy_teams(self, teams, target_season, user):
        copied_count = 0

        for original_team in teams:
            # Find the next available team number in the target season
            max_number = (
                Team.objects.filter(season=target_season).aggregate(Max("number"))[
                    "number__max"
                ]
                or 0
            )
            next_number = max_number + 1

            # Ensure team name is unique in the target season
            team_name = original_team.name
            existing_names = set(
                Team.objects.filter(season=target_season).values_list("name", flat=True)
            )
            if team_name in existing_names:
                counter = 2
                while f"{team_name} ({counter})" in existing_names:
                    counter += 1
                team_name = f"{team_name} ({counter})"

            # Create new team
            new_team = Team.objects.create(
                season=target_season,
                number=next_number,
                name=team_name,
                company_name=original_team.company_name,
                company_address=original_team.company_address,
                team_contact_email=original_team.team_contact_email,
                team_contact_number=original_team.team_contact_number,
                seed_rating=original_team.seed_rating,  # Copy seed rating
                is_active=True,
                # Note: slack_channel is left blank
            )

            # Create TeamScore object (required for standings display)
            TeamScore.objects.create(team=new_team)

            # Copy team members
            original_members = original_team.teammember_set.all()
            for original_member in original_members:
                # Check if player is registered for the target season
                season_player, created = SeasonPlayer.objects.get_or_create(
                    season=target_season, player=original_member.player
                )

                TeamMember.objects.create(
                    team=new_team,
                    player=original_member.player,
                    board_number=original_member.board_number,
                    is_captain=original_member.is_captain,
                    is_vice_captain=original_member.is_vice_captain,
                    # player_rating will be set automatically
                )

            copied_count += 1

        return copied_count

    def _team_move_blockers(self, team):
        """Return a list of human-readable reasons this team can't be moved.

        A team is movable only if its current season has no progressing
        data attached: no pairings, byes, alt assignments/searches, knockout
        records, multi-match progress, invite codes, or non-zero standings.
        """
        blockers = []
        pairing_count = TeamPairing.objects.filter(
            Q(white_team=team) | Q(black_team=team)
        ).count()
        if pairing_count:
            blockers.append(f"{pairing_count} team pairing(s)")
        bye_count = TeamBye.objects.filter(team=team).count()
        if bye_count:
            blockers.append(f"{bye_count} team bye(s)")
        alt_assignment_count = AlternateAssignment.objects.filter(team=team).count()
        if alt_assignment_count:
            blockers.append(f"{alt_assignment_count} alternate assignment(s)")
        alt_search_count = AlternateSearch.objects.filter(team=team).count()
        if alt_search_count:
            blockers.append(f"{alt_search_count} alternate search(es)")
        seeding_count = KnockoutSeeding.objects.filter(team=team).count()
        if seeding_count:
            blockers.append(f"{seeding_count} knockout seeding(s)")
        advancement_count = KnockoutAdvancement.objects.filter(team=team).count()
        if advancement_count:
            blockers.append(f"{advancement_count} knockout advancement(s)")
        progress_count = TeamMultiMatchProgress.objects.filter(team=team).count()
        if progress_count:
            blockers.append(f"{progress_count} multi-match progress record(s)")
        try:
            score = team.teamscore
            if (
                score.match_count
                or score.match_points
                or score.game_points
                or score.playoff_score
                or score.head_to_head
                or score.games_won
                or score.sb_score
                or score.buchholz
            ):
                blockers.append("non-zero team score")
        except TeamScore.DoesNotExist:
            pass
        return blockers

    def move_teams_to_season_view(self, request):
        team_ids_param = request.GET.get("team_ids", "")
        if not team_ids_param:
            messages.error(request, "No teams selected")
            return redirect("admin:tournament_team_changelist")

        try:
            team_ids = [
                int(id.strip()) for id in team_ids_param.split(",") if id.strip()
            ]
        except ValueError:
            messages.error(request, "Invalid team IDs")
            return redirect("admin:tournament_team_changelist")

        teams = Team.objects.filter(id__in=team_ids).select_related(
            "season", "season__league"
        )
        if not teams.exists():
            messages.error(request, "No valid teams found")
            return redirect("admin:tournament_team_changelist")

        team_blockers = {team.id: self._team_move_blockers(team) for team in teams}
        any_blocked = any(team_blockers[team.id] for team in teams)

        source_boards = teams.first().season.boards
        source_season_ids = {team.season_id for team in teams}
        available_seasons = (
            Season.objects.filter(
                league__competitor_type="team", boards=source_boards
            )
            .exclude(id__in=source_season_ids)
            .order_by("-start_date")
        )

        if request.method == "POST":
            if any_blocked:
                messages.error(
                    request,
                    "One or more selected teams have data that prevents moving. "
                    "Use Copy instead, or remove the blocking data first.",
                )
            else:
                target_season_id = request.POST.get("target_season")
                if not target_season_id:
                    messages.error(request, "Please select a target season")
                else:
                    try:
                        target_season = Season.objects.get(
                            id=target_season_id,
                            league__competitor_type="team",
                            boards=source_boards,
                        )
                        if target_season.id in source_season_ids:
                            raise ValueError(
                                "Target season must differ from the source season"
                            )

                        for team in teams:
                            if not request.user.has_perm(
                                "tournament.manage_players", team.season.league
                            ):
                                raise PermissionDenied(
                                    f"You don't have permission to manage teams in {team.season.league}"
                                )
                        if not request.user.has_perm(
                            "tournament.manage_players", target_season.league
                        ):
                            raise PermissionDenied(
                                "You don't have permission to manage teams in the target season"
                            )

                        moved_count = self._move_teams(
                            teams, target_season, request.user
                        )
                        messages.success(
                            request,
                            f"Successfully moved {moved_count} teams to {target_season}",
                        )
                        return redirect("admin:tournament_team_changelist")
                    except Season.DoesNotExist:
                        messages.error(request, "Invalid target season")
                    except PermissionDenied as e:
                        messages.error(request, str(e))
                    except ValueError as e:
                        messages.error(request, str(e))
                    except Exception as e:
                        messages.error(request, f"Error moving teams: {str(e)}")

        teams_with_blockers = [
            {"team": team, "blockers": team_blockers[team.id]} for team in teams
        ]
        context = {
            "teams_with_blockers": teams_with_blockers,
            "any_blocked": any_blocked,
            "available_seasons": available_seasons,
            "title": "Move Teams to New Season",
            "opts": self.model._meta,
            "app_label": self.model._meta.app_label,
        }

        return render(request, "tournament/admin/move_teams_to_season.html", context)

    def _move_teams(self, teams, target_season, user):
        moved_count = 0

        with transaction.atomic():
            for team in teams:
                blockers = self._team_move_blockers(team)
                if blockers:
                    raise ValueError(
                        f"Team '{team.name}' cannot be moved: {', '.join(blockers)}"
                    )

                max_number = (
                    Team.objects.filter(season=target_season)
                    .exclude(pk=team.pk)
                    .aggregate(Max("number"))["number__max"]
                    or 0
                )
                next_number = max_number + 1

                team_name = team.name
                existing_names = set(
                    Team.objects.filter(season=target_season)
                    .exclude(pk=team.pk)
                    .values_list("name", flat=True)
                )
                if team_name in existing_names:
                    counter = 2
                    while f"{team_name} ({counter})" in existing_names:
                        counter += 1
                    team_name = f"{team_name} ({counter})"

                for member in team.teammember_set.all():
                    SeasonPlayer.objects.get_or_create(
                        season=target_season, player=member.player
                    )

                team.season = target_season
                team.number = next_number
                team.name = team_name
                team.slack_channel = ""
                team.save()

                # Team invite codes are per-team; repoint them to the
                # target season/league so they stay valid post-move.
                InviteCode.objects.filter(team=team).update(
                    league=target_season.league,
                    season=target_season,
                )

                moved_count += 1

        return moved_count


# -------------------------------------------------------------------------------
@admin.register(TeamMember)
class TeamMemberAdmin(_BaseAdmin):
    list_display = ("__str__", "team")
    search_fields = ("team__name", "player__lichess_username")
    list_filter = ("team__season",)
    raw_id_fields = ("player",)
    autocomplete_fields = ("player",)
    exclude = ("player_rating",)
    league_id_field = "team__season__league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(TeamScore)
class TeamScoreAdmin(_BaseAdmin):
    list_display = ("team", "match_points", "game_points")
    search_fields = ("team__name",)
    list_filter = ("team__season",)
    raw_id_fields = ("team",)
    league_id_field = "team__season__league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(Alternate)
class AlternateAdmin(_BaseAdmin):
    list_display = ("__str__", "board_number", "status")
    search_fields = ("season_player__player__lichess_username",)
    list_filter = ("season_player__season", "board_number", "status")
    raw_id_fields = ("season_player",)
    exclude = ("player_rating",)
    league_id_field = "season_player__season__league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(AlternateAssignment)
class AlternateAssignmentAdmin(_BaseAdmin):
    list_display = ("__str__", "player")
    search_fields = ("team__name", "player__lichess_username")
    list_filter = ("round__season", "round__number", "board_number")
    raw_id_fields = ("round", "team", "player", "replaced_player")
    autocomplete_fields = ("round", "player", "replaced_player")
    league_id_field = "round__season__league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(AlternateBucket)
class AlternateBucketAdmin(_BaseAdmin):
    list_display = ("__str__", "season")
    search_fields = ()
    list_filter = ("season", "board_number")
    league_id_field = "season__league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(AlternateSearch)
class AlternateSearchAdmin(_BaseAdmin):
    list_display = ("__str__", "status")
    search_fields = ("team__name",)
    list_filter = ("round__season", "round__number", "board_number", "status")
    league_id_field = "round__season__league_id"
    raw_id_fields = ("round",)
    autocomplete_fields = ("round",)
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(AlternatesManagerSetting)
class AlternatesManagerSettingAdmin(_BaseAdmin):
    list_display = ("__str__",)
    league_id_field = "league_id"
    league_competitor_type = "team"


# -------------------------------------------------------------------------------
@admin.register(TeamPairing)
class TeamPairingAdmin(_BaseAdmin):
    list_display = (
        "white_team_name",
        "black_team_name",
        "season_name",
        "round_number",
        "get_manual_tiebreak_display",
    )
    search_fields = ("white_team__name", "black_team__name")
    list_filter = ("round__season", "round__number", "round__knockout_stage")
    raw_id_fields = ("white_team", "black_team", "round", "advances_winner_to_round")
    autocomplete_fields = (
        "white_team",
        "black_team",
        "round",
        "advances_winner_to_round",
    )
    league_id_field = "round__season__league_id"
    league_competitor_type = "team"
    actions = [
        "set_white_wins_tiebreak",
        "set_black_wins_tiebreak",
        "clear_manual_tiebreak",
    ]

    fieldsets = (
        (
            "Pairing Details",
            {"fields": ("white_team", "black_team", "round", "pairing_order")},
        ),
        (
            "Results",
            {"fields": ("white_points", "white_wins", "black_points", "black_wins")},
        ),
        (
            "Knockout Settings",
            {
                "fields": ("manual_tiebreak_value", "advances_winner_to_round"),
                "classes": ("collapse",),
                "description": "Manual tiebreak: positive values favor white team, negative favor black team",
            },
        ),
    )

    def get_manual_tiebreak_display(self, obj):
        if obj.manual_tiebreak_value is None:
            return "-"
        elif obj.manual_tiebreak_value > 0:
            return f"+{obj.manual_tiebreak_value} (White)"
        elif obj.manual_tiebreak_value < 0:
            return f"{obj.manual_tiebreak_value} (Black)"
        else:
            return "0 (Tie)"

    get_manual_tiebreak_display.short_description = "Manual Tiebreak"

    def set_white_wins_tiebreak(self, request, queryset):
        """Set manual tiebreak to favor white team (+1.0)."""
        knockout_pairings = queryset.filter(
            round__season__league__pairing_type__in=[
                "knockout-single",
                "knockout-multi",
            ]
        )

        if not knockout_pairings.exists():
            self.message_user(
                request,
                "Selected pairings are not from knockout tournaments.",
                messages.ERROR,
            )
            return

        updated_count = knockout_pairings.update(manual_tiebreak_value=1.0)

        self.message_user(
            request,
            f"Set manual tiebreak to favor white team for {updated_count} pairings.",
            messages.SUCCESS,
        )

    set_white_wins_tiebreak.short_description = "Set manual tiebreak: White team wins"

    def set_black_wins_tiebreak(self, request, queryset):
        """Set manual tiebreak to favor black team (-1.0)."""
        knockout_pairings = queryset.filter(
            round__season__league__pairing_type__in=[
                "knockout-single",
                "knockout-multi",
            ]
        )

        if not knockout_pairings.exists():
            self.message_user(
                request,
                "Selected pairings are not from knockout tournaments.",
                messages.ERROR,
            )
            return

        updated_count = knockout_pairings.update(manual_tiebreak_value=-1.0)

        self.message_user(
            request,
            f"Set manual tiebreak to favor black team for {updated_count} pairings.",
            messages.SUCCESS,
        )

    set_black_wins_tiebreak.short_description = "Set manual tiebreak: Black team wins"

    def clear_manual_tiebreak(self, request, queryset):
        """Clear manual tiebreak values."""
        updated_count = queryset.update(manual_tiebreak_value=None)

        self.message_user(
            request,
            f"Cleared manual tiebreak for {updated_count} pairings.",
            messages.SUCCESS,
        )

    clear_manual_tiebreak.short_description = "Clear manual tiebreak"


# -------------------------------------------------------------------------------
class PlayerPresenceInline(admin.TabularInline):
    model = PlayerPresence
    extra = 0
    exclude = ("round", "player")
    readonly_fields = ("first_msg_time", "last_msg_time", "online_for_game")
    can_delete = False
    max_num = 0


# -------------------------------------------------------------------------------
class PlayerPresenceEventInline(admin.TabularInline):
    model = PlayerPresenceEvent
    extra = 0
    fields = ("timestamp", "player", "event_type", "game_id")
    readonly_fields = fields
    can_delete = False
    max_num = 0
    ordering = ("-timestamp",)
    show_change_link = False
    verbose_name_plural = "Presence event log"

    def has_add_permission(self, request, obj=None):
        return False


# -------------------------------------------------------------------------------
@admin.register(PlayerPresenceEvent)
class PlayerPresenceEventAdmin(_BaseAdmin):
    list_display = ("timestamp", "player", "event_type", "pairing", "round", "game_id")
    list_filter = ("event_type", "round")
    search_fields = ("player__lichess_username", "game_id")
    readonly_fields = (
        "player",
        "timestamp",
        "event_type",
        "pairing",
        "round",
        "game_id",
    )
    raw_id_fields = ("player", "pairing", "round")
    date_hierarchy = "timestamp"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


# -------------------------------------------------------------------------------
@admin.register(PlayerPairing)
class PlayerPairingAdmin(_BaseAdmin):
    list_display = ("__str__", "scheduled_time", "game_link_url")
    search_fields = ("white__lichess_username", "black__lichess_username", "game_link")
    raw_id_fields = ("white", "black")
    autocomplete_fields = ("white", "black")
    inlines = [PlayerPresenceInline, PlayerPresenceEventInline]
    exclude = ("white_rating", "black_rating", "tv_state")
    actions = ["send_pairing_notification"]

    def send_pairing_notification(self, request, queryset):
        count = 0
        for pairing in queryset.all():
            round_ = pairing.get_round()
            if round_ is not None:
                signals.notify_players_late_pairing.send(
                    sender=self, round_=round_, pairing=pairing
                )
                count += 1
        self.message_user(
            request, "Notifications sent for %d pairings." % count, messages.INFO
        )

    def get_queryset(self, request):
        queryset = super(_BaseAdmin, self).get_queryset(request)
        if self.has_assigned_perm(request.user, "change"):
            return queryset
        return queryset.filter(
            teamplayerpairing__team_pairing__round__season__league_id__in=self.authorized_leagues(
                request.user
            )
        ) | queryset.filter(
            loneplayerpairing__round__season__league_id__in=self.authorized_leagues(
                request.user
            )
        )

    def has_add_permission(self, request):
        return self.has_assigned_perm(request.user, "add")

    def get_league_id(self, obj):
        if hasattr(obj, "teamplayerpairing"):
            return obj.teamplayerpairing.team_pairing.round.season.league_id
        elif hasattr(obj, "loneplayerpairing"):
            return obj.loneplayerpairing.round.season.league_id
        else:
            return None

    def has_league_perm(self, user, action, obj):
        if obj is None:
            return bool(self.authorized_leagues(user))
        else:
            return self.get_league_id(obj) in self.authorized_leagues(user)

    def clean_form(self, request, form):
        pass

    def game_link_url(self, obj):
        if not obj.game_link:
            return ""
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

    def related_objects_for_comments(self, request, object_id):
        related_objects = []
        related_objects += list(
            TeamPlayerPairing.objects.filter(id=object_id).nocache()
        )
        related_objects += list(
            LonePlayerPairing.objects.filter(id=object_id).nocache()
        )
        return related_objects


# -------------------------------------------------------------------------------
@admin.register(TeamPlayerPairing)
class TeamPlayerPairingAdmin(_BaseAdmin):
    list_display = ("__str__", "team_pairing", "board_number", "game_link_url")
    search_fields = (
        "white__lichess_username",
        "black__lichess_username",
        "team_pairing__white_team__name",
        "team_pairing__black_team__name",
        "game_link",
    )
    list_filter = (
        "team_pairing__round__season",
        "team_pairing__round__number",
    )
    raw_id_fields = ("white", "black", "team_pairing")
    autocomplete_fields = ("white", "black")
    league_id_field = "team_pairing__round__season__league_id"
    league_competitor_type = "team"

    def game_link_url(self, obj):
        if not obj.game_link:
            return ""
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

    def related_objects_for_comments(self, request, object_id):
        return list(PlayerPairing.objects.filter(id=object_id).nocache())


# -------------------------------------------------------------------------------
@admin.register(LonePlayerPairing)
class LonePlayerPairingAdmin(_BaseAdmin):
    list_display = ("__str__", "round", "game_link_url")
    search_fields = ("white__lichess_username", "black__lichess_username", "game_link")
    list_filter = ("round__season", "round__number")
    raw_id_fields = ("white", "black", "round")
    autocomplete_fields = ("white", "black", "round")
    league_id_field = "round__season__league_id"
    league_competitor_type = "individual"

    def game_link_url(self, obj):
        if not obj.game_link:
            return ""
        return format_html("<a href='{url}'>{url}</a>", url=obj.game_link)

    def related_objects_for_comments(self, request, object_id):
        return list(PlayerPairing.objects.filter(id=object_id).nocache())


# -------------------------------------------------------------------------------
@admin.register(Registration)
class RegistrationAdmin(_BaseAdmin):
    list_display_links = ()
    list_filter = ("status", "validation_status", "season", "section_preference__name")
    actions = ("validate", "approve")
    league_id_field = "season__league_id"

    def get_list_display(self, request):
        return self.remove_email_if_no_dox(
            request.user,
            [
                "review",
                "email",
                "status",
                "valid",
                "season",
                "section",
                "rating",
                "date_created",
                "date_validated",
            ],
        )

    def get_fields(self, request, obj=None):
        return self.remove_email_if_no_dox(
            request.user, super().get_fields(request, obj)
        )

    def get_search_fields(self, request):
        return self.remove_email_if_no_dox(
            request.user, ("player__lichess_username", "email", "season__name")
        )

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super().changelist_view(request, extra_context=extra_context)

    def section(self, obj):
        return obj.section_preference.name if obj.section_preference else ""

    def review(self, obj):
        _url = (
            reverse("admin:review_registration", args=[obj.pk])
            + "?"
            + self.get_preserved_filters(self.request)
        )
        return mark_safe('<a href="%s"><b>%s</b></a>' % (_url, obj.lichess_username))

    VALIDATION_ISSUE_ICONS: ClassVar[dict[str, str]] = {
        "no_rating": "\u0030\ufe0f\u20e3",
        "account_not_normal": "\U0001f6ab",
        "fide_id_wrong_player": "\U0001f194",
        "predefined_fide_mismatch": "\U0001f522",
        "not_in_predefined_list": "\U0001f4cb",
        "fide_id_not_in_predefined_list": "\U0001f3f7\ufe0f",
        "fide_id_duplicate": "\U0001f465",
        "provisional_rating": "\u23f3",
        "rules_not_agreed": "\U0001f4dc",
        "tos_not_agreed": "\U0001f4c4",
    }

    def valid(self, obj):
        if obj.validation_status == ValidationStatus.OK:
            return mark_safe('<img src="%s">' % static("admin/img/icon-yes.svg"))
        issues = obj.validation_issues or []
        parts = []
        for issue in issues:
            icon = self.VALIDATION_ISSUE_ICONS.get(issue["code"], "\u2753")
            escaped_msg = escape(issue["message"])
            parts.append(f'<span title="{escaped_msg}">{icon}</span>')
        return mark_safe(" ".join(parts))

    def date_validated(self, obj):
        return obj.player.date_modified

    date_validated.admin_order_field = "-player__date_modified"

    def get_urls(self):
        urls = super(RegistrationAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/review/",
                self.admin_site.admin_view(self.review_registration),
                name="review_registration",
            ),
            path(
                "<int:object_id>/approve/",
                self.admin_site.admin_view(self.approve_registration),
                name="approve_registration",
            ),
            path(
                "<int:object_id>/reject/",
                self.admin_site.admin_view(self.reject_registration),
                name="reject_registration",
            ),
        ]
        return my_urls + urls

    def validate(self, request, queryset):
        signals.do_validate_registration.send(sender=RegistrationAdmin, regs=queryset)
        for reg in queryset.select_related("season__league", "player"):
            reg.refresh_from_db()
            reg.refresh_validation()
        self.message_user(request, "Validation started.", messages.INFO)
        return redirect("admin:tournament_registration_changelist")

    def approve(self, request, queryset):
        if not request.user.has_perm("tournament.invite_to_slack"):
            self.message_user(
                request,
                "You don't have permissions to invite users to slack.",
                messages.ERROR,
            )
            return redirect("admin:tournament_registration_changelist")
        count = 0
        for reg in queryset:
            if reg.status == "pending":
                workflow = ApproveRegistrationWorkflow(reg)

                send_confirm_email = workflow.default_send_confirm_email
                invite_to_slack = workflow.default_invite_to_slack
                default_section = workflow.default_section
                if workflow.is_late:
                    retroactive_byes = workflow.default_byes
                    late_join_points = workflow.default_ljp
                else:
                    retroactive_byes = None
                    late_join_points = None

                workflow.approve_reg(
                    request,
                    None,
                    send_confirm_email,
                    invite_to_slack,
                    default_section,
                    retroactive_byes,
                    late_join_points,
                )
                count += 1

        self.message_user(request, "%d approved." % count, messages.INFO)
        return redirect("admin:tournament_registration_changelist")

    def review_registration(self, request, object_id):
        reg = get_object_or_404(Registration, pk=object_id)
        if not request.user.has_perm(
            "tournament.change_registration", reg.season.league
        ):
            raise PermissionDenied

        if request.method == "POST":
            changelist_filters = request.POST.get("_changelist_filters", "")
            form = forms.ReviewRegistrationForm(request.POST)
            if form.is_valid():
                params = "?_changelist_filters=" + urlquote(changelist_filters)
                if "approve" in form.data and reg.status == "pending":
                    return redirect_with_params(
                        "admin:approve_registration", object_id=object_id, params=params
                    )
                elif "reject" in form.data and reg.status == "pending":
                    return redirect_with_params(
                        "admin:reject_registration", object_id=object_id, params=params
                    )
                elif "edit" in form.data:
                    return redirect_with_params(
                        "admin:tournament_registration_change", object_id, params=params
                    )
                else:
                    return redirect_with_params(
                        "admin:tournament_registration_changelist", params=params
                    )
        else:
            changelist_filters = request.GET.get("_changelist_filters", "")
            form = forms.ReviewRegistrationForm()

        is_team = reg.season.league.competitor_type == "team"

        predefined_list_detail = None
        if (
            reg.season.validate_predefined_list_contains_username
            or reg.season.validate_predefined_list_contains_fide_id
            or reg.season.validate_predefined_list_contains_username_fide_id_together
        ):
            predefined_list_detail = reg.predefined_list_check().detail

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": reg,
            "provisional": reg.player.provisional_for(league=reg.season.league),
            "title": "Review registration",
            "form": form,
            "is_team": is_team,
            "date_validated": reg.player.date_modified,
            "changelist_filters": changelist_filters,
            "predefined_list_detail": predefined_list_detail,
        }

        return render(request, "tournament/admin/review_registration.html", context)

    def approve_registration(self, request, object_id):
        reg = get_object_or_404(Registration, pk=object_id)
        if not request.user.has_perm(
            "tournament.change_registration", reg.season.league
        ):
            raise PermissionDenied

        if reg.status != "pending":
            return redirect("admin:review_registration", object_id)

        if request.method == "POST":
            changelist_filters = request.POST.get("_changelist_filters", "")
            form = forms.ApproveRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                if "confirm" in form.data:
                    workflow = ApproveRegistrationWorkflow(reg)
                    workflow.approve_reg(
                        request,
                        self,
                        form.cleaned_data["send_confirm_email"],
                        form.cleaned_data["invite_to_slack"],
                        form.cleaned_data.get("section", reg.season),
                        form.cleaned_data.get("retroactive_byes"),
                        form.cleaned_data.get("late_join_points"),
                    )
                    return redirect_with_params(
                        "admin:tournament_registration_changelist",
                        params="?" + changelist_filters,
                    )
                else:
                    return redirect_with_params(
                        "admin:review_registration",
                        object_id,
                        params="?_changelist_filters=" + urlquote(changelist_filters),
                    )
        else:
            changelist_filters = request.GET.get("_changelist_filters", "")
            form = forms.ApproveRegistrationForm(registration=reg)

        next_round = (
            Round.objects.filter(season=reg.season, publish_pairings=False)
            .order_by("number")
            .first()
        )

        mod = LeagueModerator.objects.filter(
            player__lichess_username__iexact=reg.lichess_username
        ).first()
        no_email_change = (
            mod is not None and mod.player.email and mod.player.email != reg.email
        )
        confirm_email = mod.player.email if no_email_change else reg.email

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": reg,
            "title": "Confirm approval",
            "form": form,
            "next_round": next_round,
            "confirm_email": confirm_email,
            "no_email_change": no_email_change,
            "changelist_filters": changelist_filters,
        }

        return render(request, "tournament/admin/approve_registration.html", context)

    def reject_registration(self, request, object_id):
        reg = get_object_or_404(Registration, pk=object_id)
        if not request.user.has_perm(
            "tournament.change_registration", reg.season.league
        ):
            raise PermissionDenied

        if reg.status != "pending":
            return redirect("admin:review_registration", object_id)

        if request.method == "POST":
            changelist_filters = request.POST.get("_changelist_filters", "")
            form = forms.RejectRegistrationForm(request.POST, registration=reg)
            if form.is_valid():
                if "confirm" in form.data:
                    with reversion.create_revision():
                        reversion.set_user(request.user)
                        reversion.set_comment("Rejected registration.")

                        reg.status = "rejected"
                        reg.status_changed_by = request.user.username
                        reg.status_changed_date = timezone.now()
                        reg.save()

                    self.message_user(
                        request,
                        'Registration for "%s" rejected.' % reg.lichess_username,
                        messages.INFO,
                    )
                    try:
                        send_mail(
                            render_to_string(
                                "tournament/emails/registration_rejected_subject.txt",
                                {"reg": reg},
                            ),
                            render_to_string(
                                "tournament/emails/registration_rejected.txt",
                                {"reg": reg},
                            ),
                            settings.DEFAULT_FROM_EMAIL,
                            [reg.email],
                            html_message=render_to_string(
                                "tournament/emails/registration_rejected.html",
                                {"reg": reg},
                            ),
                        )
                        self.message_user(
                            request,
                            'Rejection email sent to "%s".' % reg.email,
                            messages.INFO,
                        )
                    except SMTPException:
                        logger.exception("A rejection email could not be sent.")

                    return redirect_with_params(
                        "admin:tournament_registration_changelist",
                        params="?" + changelist_filters,
                    )
                else:
                    return redirect("admin:review_registration", object_id)
                    return redirect_with_params(
                        "admin:review_registration",
                        object_id,
                        params="?_changelist_filters=" + urlquote(changelist_filters),
                    )
        else:
            changelist_filters = request.GET.get("_changelist_filters", "")
            form = forms.RejectRegistrationForm(registration=reg)

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": reg,
            "title": "Confirm rejection",
            "form": form,
            "changelist_filters": changelist_filters,
        }

        return render(request, "tournament/admin/reject_registration.html", context)


class InSlackFilter(SimpleListFilter):
    title = "is in slack"
    parameter_name = "player__slack_user_id"

    def lookups(self, request, model_admin):
        return (
            (
                "1",
                "Yes",
            ),
            (
                "0",
                "No",
            ),
        )

    def queryset(self, request, queryset):
        if self.value() == "0":
            return queryset.filter(player__slack_user_id="")
        if self.value() == "1":
            return queryset.exclude(player__slack_user_id="")
        return queryset


# -------------------------------------------------------------------------------
@admin.register(SeasonPlayer)
class SeasonPlayerAdmin(_BaseAdmin):
    list_display = ("player", "season", "is_active", "in_slack")
    search_fields = ("season__name", "player__lichess_username")
    list_filter = ("season__league", "season", "is_active", InSlackFilter)
    raw_id_fields = ("player", "registration")
    autocomplete_fields = ("player",)
    league_id_field = "season__league_id"
    actions = ["bulk_email", "link_reminder"]

    def in_slack(self, sp):
        return bool(sp.player.slack_user_id)

    in_slack.boolean = True

    def get_urls(self):
        urls = super(SeasonPlayerAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_ids>/bulk_email/",
                self.admin_site.admin_view(self.bulk_email_view),
                name="bulk_email_by_players",
            ),
        ]
        return my_urls + urls

    def link_reminder(self, request, queryset):
        slack_users = slackapi.get_user_list()
        by_email = {u.email: u.id for u in slack_users}

        for sp in (
            queryset.filter(is_active=True, player__slack_user_id="")
            .select_related("player")
            .nocache()
        ):
            uid = by_email.get(sp.player.email)
            if uid:
                token = LoginToken.objects.create(
                    slack_user_id=uid,
                    username_hint=sp.player.lichess_username,
                    expires=timezone.now() + timedelta(days=30),
                )
                url = reverse(
                    "by_league:login_with_token",
                    args=[sp.season.league.tag, token.secret_token],
                )
                url = request.build_absolute_uri(url)
                text = (
                    "Reminder: You need to link your Slack and Lichess accounts. <%s|Click here> to do that now. Contact a mod if you need help."
                    % url
                )
                slackapi.send_message(uid, text)

        return redirect("admin:tournament_seasonplayer_changelist")

    def bulk_email(self, request, queryset):
        return redirect(
            "admin:bulk_email_by_players",
            object_ids=",".join((str(sp.id) for sp in queryset)),
        )

    def bulk_email_view(self, request, object_ids):
        season_players = (
            SeasonPlayer.objects.filter(id__in=[int(i) for i in object_ids.split(",")])
            .select_related("season", "player")
            .nocache()
        )
        seasons = {sp.season for sp in season_players}
        for season in seasons:
            if not request.user.has_perm("tournament.bulk_email", season.league):
                raise PermissionDenied

        if request.method == "POST":
            form = forms.BulkEmailForm(len(season_players), request.POST)
            if form.is_valid() and form.cleaned_data["confirm_send"]:
                email_addresses = {
                    sp.player.email for sp in season_players if sp.player.email != ""
                }
                email_messages = []
                for addr in email_addresses:
                    message = EmailMultiAlternatives(
                        form.cleaned_data["subject"],
                        form.cleaned_data["text_content"],
                        settings.DEFAULT_FROM_EMAIL,
                        [addr],
                    )
                    message.attach_alternative(
                        form.cleaned_data["html_content"], "text/html"
                    )
                    email_messages.append(message)
                conn = mail.get_connection()
                conn.open()
                conn.send_messages(email_messages)
                conn.close()
                self.message_user(
                    request,
                    "Emails sent to %d players." % len(season_players),
                    messages.INFO,
                )
                return redirect("admin:tournament_seasonplayer_changelist")
        else:
            form = forms.BulkEmailForm(len(season_players))

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": "Bulk email",
            "title": "Bulk email",
            "form": form,
        }

        return render(request, "tournament/admin/bulk_email.html", context)


# -------------------------------------------------------------------------------
@admin.register(LonePlayerScore)
class LonePlayerScoreAdmin(_BaseAdmin):
    list_display = ("season_player", "points", "late_join_points")
    search_fields = (
        "season_player__season__name",
        "season_player__player__lichess_username",
    )
    list_filter = ("season_player__season",)
    raw_id_fields = ("season_player",)
    league_id_field = "season_player__season__league_id"
    league_competitor_type = "individual"


# -------------------------------------------------------------------------------
@admin.register(PlayerAvailability)
class PlayerAvailabilityAdmin(_BaseAdmin):
    list_display = ("player", "round", "is_available")
    search_fields = ("player__lichess_username",)
    list_filter = ("round__season", "round__number")
    raw_id_fields = ("player", "round")
    autocomplete_fields = ("player", "round")
    league_id_field = "round__season__league_id"


# -------------------------------------------------------------------------------
@admin.register(SeasonPrize)
class SeasonPrizeAdmin(_BaseAdmin):
    list_display = ("season", "rank", "max_rating")
    search_fields = ("season__name",)
    league_id_field = "season__league_id"


# -------------------------------------------------------------------------------
@admin.register(SeasonPrizeWinner)
class SeasonPrizeWinnerAdmin(_BaseAdmin):
    list_display = (
        "season_prize",
        "player",
    )
    search_fields = ("season_prize__season__name", "player__lichess_username")
    raw_id_fields = ("season_prize", "player")
    autocomplete_fields = ("player",)
    league_id_field = "season_prize__season__league_id"


# -------------------------------------------------------------------------------
@admin.register(GameNomination)
class GameNominationAdmin(_BaseAdmin):
    list_display = ("__str__",)
    search_fields = ("season__name", "nominating_player__lichess_username")
    raw_id_fields = ("nominating_player", "pairing")
    autocomplete_fields = ("nominating_player",)
    league_id_field = "season__league_id"


# -------------------------------------------------------------------------------
@admin.register(GameSelection)
class GameSelectionAdmin(_BaseAdmin):
    list_display = ("__str__",)
    search_fields = ("season__name",)
    raw_id_fields = ("pairing",)
    league_id_field = "season__league_id"


# -------------------------------------------------------------------------------
@admin.register(AvailableTime)
class AvailableTimeAdmin(_BaseAdmin):
    list_display = ("player", "time", "league")
    search_fields = ("player__lichess_username",)
    autocomplete_fields = ("player",)
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(NavItem)
class NavItemAdmin(_BaseAdmin):
    list_display = ("__str__", "parent")
    search_fields = ("text",)
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(ApiKey)
class ApiKeyAdmin(_BaseAdmin):
    list_display = ("name",)
    search_fields = ("name",)


# -------------------------------------------------------------------------------
@admin.register(PrivateUrlAuth)
class PrivateUrlAuthAdmin(_BaseAdmin):
    list_display = ("__str__", "expires")
    search_fields = ("authenticated_user",)


# -------------------------------------------------------------------------------
@admin.register(Document)
class DocumentAdmin(_BaseAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    autocomplete_fields = ("owner",)

    def get_queryset(self, request):
        queryset = super(_BaseAdmin, self).get_queryset(request)
        if request.user.is_superuser:
            return queryset
        filtered_queryset = (
            queryset.filter(
                leaguedocument__league_id__in=self.authorized_leagues(request.user)
            )
            | queryset.filter(
                seasondocument__season__league_id__in=self.authorized_leagues(
                    request.user
                )
            )
            | queryset.filter(owner=request.user)
        )
        if self.has_assigned_perm(request.user, "change"):
            filtered_queryset |= queryset.filter(allow_editors=True)
        return filtered_queryset

    def get_league_id(self, obj):
        if hasattr(obj, "leaguedocument"):
            return obj.leaguedocument.league_id
        elif hasattr(obj, "seasondocument"):
            return obj.seasondocument.season.league_id
        else:
            return None

    def has_league_perm(self, user, action, obj):
        if obj is None:
            return (
                bool(self.authorized_leagues(user))
                or Document.objects.filter(owner=user).exists()
            )
        else:
            return (
                user.is_superuser
                or obj.owned_by(user)
                or self.get_league_id(obj) in self.authorized_leagues(user)
                or action == "change"
                and obj.allow_editors
                and self.has_assigned_perm(user, "change")
            )

    def has_change_permission(self, request, obj=None):
        return self.has_league_perm(request.user, "change", obj)

    def get_changeform_initial_data(self, request):
        get_data = super(DocumentAdmin, self).get_changeform_initial_data(request)
        get_data["owner"] = request.user.pk
        return get_data

    def clean_form(self, request, form):
        pass

    def get_readonly_fields(self, request, obj=None):
        if obj is None or request.user.is_superuser or obj.owned_by(request.user):
            return ()
        return ("allow_editors", "owner")


# -------------------------------------------------------------------------------
@admin.register(LeagueDocument)
class LeagueDocumentAdmin(_BaseAdmin):
    list_display = ("document", "league", "tag", "type", "url")
    search_fields = ("league__name", "tag", "document__name")
    league_id_field = "league_id"

    def url(self, obj):
        _url = reverse("by_league:document", args=[obj.league.tag, obj.tag])
        return mark_safe('<a href="%s">%s</a>' % (_url, _url))


# -------------------------------------------------------------------------------
@admin.register(SeasonDocument)
class SeasonDocumentAdmin(_BaseAdmin):
    list_display = ("document", "season", "tag", "type", "url")
    search_fields = ("season__name", "tag", "document__name")
    league_id_field = "season__league_id"

    def url(self, obj):
        _url = reverse(
            "by_league:by_season:document",
            args=[obj.season.league.tag, obj.season.tag, obj.tag],
        )
        return mark_safe('<a href="%s">%s</a>' % (_url, _url))


# -------------------------------------------------------------------------------
@admin.register(LeagueChannel)
class LeagueChannelAdmin(_BaseAdmin):
    list_display = ("league", "type", "slack_channel")
    search_fields = ("league__name", "slack_channel")
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(ScheduledEvent)
class ScheduledEventAdmin(_BaseAdmin):
    list_display = ("type", "offset", "relative_to", "league", "season")
    search_fields = ("league__name", "season__name")
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(PlayerNotificationSetting)
class PlayerNotificationSettingAdmin(_BaseAdmin):
    list_display = (
        "player",
        "type",
        "league",
        "offset",
        "enable_lichess_mail",
        "enable_slack_im",
        "enable_slack_mpim",
    )
    list_filter = ("league", "type")
    search_fields = ("player__lichess_username",)
    raw_id_fields = ("player",)
    autocomplete_fields = ("player",)
    league_id_field = "league_id"


# -------------------------------------------------------------------------------
@admin.register(ScheduledNotification)
class ScheduledNotificationAdmin(_BaseAdmin):
    list_display = ("setting", "pairing", "notification_time")
    list_filter = ("setting__type",)
    search_fields = (
        "pairing__white__lichess_username",
        "pairing__black__lichess_username",
    )
    raw_id_fields = ("setting", "pairing")
    league_id_field = "setting__league_id"


# -------------------------------------------------------------------------------
@admin.register(ModRequest)
class ModRequestAdmin(_BaseAdmin):
    list_display = ("review", "type", "status", "season", "date_created")
    list_display_links = ()
    list_filter = ("status", "type", "season")
    search_fields = ("requester__lichess_username",)
    raw_id_fields = ("round", "requester", "pairing")
    autocomplete_fields = ("requester",)
    league_id_field = "season__league_id"

    def changelist_view(self, request, extra_context=None):
        self.request = request
        return super(ModRequestAdmin, self).changelist_view(
            request, extra_context=extra_context
        )

    def review(self, obj):
        _url = (
            reverse("admin:tournament_modrequest_review", args=[obj.pk])
            + "?"
            + self.get_preserved_filters(self.request)
        )
        return mark_safe(
            '<a href="%s"><b>%s</b></a>' % (_url, obj.requester.lichess_username)
        )

    def edit(self, obj):
        return "Edit"

    def get_urls(self):
        urls = super(ModRequestAdmin, self).get_urls()
        my_urls = [
            path(
                "<int:object_id>/review/",
                self.admin_site.admin_view(self.review_request),
                name="tournament_modrequest_review",
            ),
            path(
                "<int:object_id>/approve/",
                self.admin_site.admin_view(self.approve_request),
                name="tournament_modrequest_approve",
            ),
            path(
                "<int:object_id>/reject/",
                self.admin_site.admin_view(self.reject_request),
                name="tournament_modrequest_reject",
            ),
        ]
        return my_urls + urls

    def review_request(self, request, object_id):
        obj = get_object_or_404(ModRequest, pk=object_id)
        if not request.user.has_perm("tournament.change_modrequest", obj.season.league):
            raise PermissionDenied

        if request.method == "POST":
            changelist_filters = request.POST.get("_changelist_filters", "")
            form = forms.ReviewModRequestForm(request.POST)
            if form.is_valid():
                params = "?_changelist_filters=" + urlquote(changelist_filters)
                if "approve" in form.data and obj.status == "pending":
                    return redirect_with_params(
                        "admin:tournament_modrequest_approve",
                        object_id=object_id,
                        params=params,
                    )
                elif "reject" in form.data and obj.status == "pending":
                    return redirect_with_params(
                        "admin:tournament_modrequest_reject",
                        object_id=object_id,
                        params=params,
                    )
                elif "edit" in form.data:
                    return redirect_with_params(
                        "admin:tournament_modrequest_change", object_id, params=params
                    )
                else:
                    return redirect_with_params(
                        "admin:tournament_modrequest_changelist", params=params
                    )
        else:
            changelist_filters = request.GET.get("_changelist_filters", "")
            form = forms.ReviewModRequestForm()

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": obj,
            "title": "Review mod request",
            "form": form,
            "changelist_filters": changelist_filters,
        }

        return render(request, "tournament/admin/review_modrequest.html", context)

    def approve_request(self, request, object_id):
        obj = get_object_or_404(ModRequest, pk=object_id)
        if not request.user.has_perm("tournament.change_modrequest", obj.season.league):
            raise PermissionDenied

        if obj.status != "pending":
            return redirect("admin:tournament_modrequest_review", object_id)

        if request.method == "POST":
            changelist_filters = request.POST.get("_changelist_filters", "")
            form = forms.ApproveModRequestForm(request.POST)
            if form.is_valid():
                if "confirm" in form.data:
                    obj.approve(request.user.username, form.cleaned_data["response"])
                    self.message_user(request, "Request approved.", messages.INFO)
                    return redirect_with_params(
                        "admin:tournament_modrequest_changelist",
                        params="?" + changelist_filters,
                    )
                else:
                    return redirect_with_params(
                        "admin:tournament_modrequest_review",
                        object_id,
                        params="?_changelist_filters=" + urlquote(changelist_filters),
                    )
        else:
            changelist_filters = request.GET.get("_changelist_filters", "")
            form = forms.ApproveModRequestForm()

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": obj,
            "title": "Confirm approval",
            "form": form,
            "changelist_filters": changelist_filters,
        }

        return render(request, "tournament/admin/approve_modrequest.html", context)

    def reject_request(self, request, object_id):
        obj = get_object_or_404(ModRequest, pk=object_id)
        if not request.user.has_perm("tournament.change_modrequest", obj.season.league):
            raise PermissionDenied

        if obj.status != "pending":
            return redirect("admin:tournament_modrequest_review", object_id)

        if request.method == "POST":
            changelist_filters = request.POST.get("_changelist_filters", "")
            form = forms.RejectModRequestForm(request.POST)
            if form.is_valid():
                if "confirm" in form.data:
                    obj.reject(request.user.username, form.cleaned_data["response"])
                    self.message_user(request, "Request rejected.", messages.INFO)
                    return redirect_with_params(
                        "admin:tournament_modrequest_changelist",
                        params="?" + changelist_filters,
                    )
                else:
                    return redirect_with_params(
                        "admin:tournament_modrequest_review",
                        object_id,
                        params="?_changelist_filters=" + urlquote(changelist_filters),
                    )
        else:
            changelist_filters = request.GET.get("_changelist_filters", "")
            form = forms.RejectModRequestForm()

        context = {
            "has_permission": True,
            "opts": self.model._meta,
            "site_url": "/",
            "original": obj,
            "title": "Confirm rejection",
            "form": form,
            "changelist_filters": changelist_filters,
        }

        return render(request, "tournament/admin/reject_modrequest.html", context)


@admin.register(Broadcast)
class BroadcastAdmin(_BaseAdmin):
    list_display = (
        "season",
        "first_board",
        "lichess_id",
    )
    list_filter = (
        "season__league",
        "season",
    )
    search_fields = (
        "season__tag",
        "season__league__name",
    )


@admin.register(BroadcastRound)
class BroadcastRoundAdmin(_BaseAdmin):
    list_display = (
        "round_id",
        "broadcast",
        "first_board",
        "lichess_id",
    )
    list_filter = (
        "round_id__season__league",
        "round_id__season",
    )
    search_fields = (
        "round_id__season__tag",
        "round_id__season__league__name",
        "round_id__number",
    )


@admin.register(InviteCode)
class InviteCodeAdmin(_BaseAdmin):
    list_display = (
        "code",
        "code_type",
        "league",
        "season",
        "team",
        "used_by",
        "used_at",
        "created_by",
    )
    list_filter = ("league", "season", "code_type", "team", "used_at")
    search_fields = ("code", "used_by__lichess_username", "team__name")
    readonly_fields = ("code", "used_by", "used_at", "date_created", "date_modified")
    actions = ["export_codes"]

    def get_readonly_fields(self, request, obj=None):
        if obj is None:  # Creating new invite code
            return ("used_by", "used_at", "date_created", "date_modified")
        else:  # Editing existing invite code
            return ("code", "used_by", "used_at", "date_created", "date_modified")

    def has_add_permission(self, request):
        # Users should use the batch generation feature instead
        return False

    def export_codes(self, request, queryset):
        """Export selected invite codes as CSV"""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="invite_codes.csv"'

        writer = csv.writer(response)
        writer.writerow(
            [
                "Code",
                "Type",
                "League",
                "Season",
                "Team",
                "Status",
                "Used By",
                "Used At",
                "Created By",
                "Notes",
            ]
        )

        for code in queryset:
            writer.writerow(
                [
                    code.code,
                    code.get_code_type_display(),
                    code.league.name,
                    code.season.name,
                    code.team.name if code.team else "",
                    "Used" if code.used_by else "Available",
                    code.used_by.lichess_username if code.used_by else "",
                    code.used_at.strftime("%Y-%m-%d %H:%M:%S") if code.used_at else "",
                    code.created_by.username if code.created_by else "",
                    code.notes,
                ]
            )

        return response

    export_codes.short_description = "Export selected codes as CSV"


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "get_text_preview",
        "status",
        "path_prefix",
        "start_date",
        "end_date",
        "is_active",
        "date_created",
    ]
    list_display_links = ["__str__", "status", "path_prefix"]
    list_filter = ["status", "is_active", "start_date", "end_date", "date_created"]
    search_fields = ["text", "path_prefix"]
    ordering = ["-date_created"]
    readonly_fields = ["date_created", "date_modified"]

    fieldsets = (
        (
            "Announcement Details",
            {
                "fields": (
                    "text",
                    "status",
                    "path_prefix",
                    "start_date",
                    "end_date",
                    "is_active",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("date_created", "date_modified"),
                "classes": ("collapse",),
            },
        ),
    )


# ===============================================================================
# Knockout Tournament Admin
# ===============================================================================


class KnockoutSeedingInline(admin.TabularInline):
    model = KnockoutSeeding
    extra = 0
    fields = ("seed_number", "team", "is_manual_seed")
    ordering = ("seed_number",)


@admin.register(KnockoutBracket)
class KnockoutBracketAdmin(admin.ModelAdmin):
    list_display = [
        "season",
        "bracket_size",
        "seeding_style",
        "games_per_match",
        "matches_per_stage",
        "tournament_type",
        "is_completed",
    ]
    list_filter = [
        "seeding_style",
        "games_per_match",
        "matches_per_stage",
        "is_completed",
    ]
    search_fields = ["season__name", "season__league__name"]
    inlines = [KnockoutSeedingInline]
    actions = [
        "generate_knockout_bracket_action",
        "regenerate_seedings_action",
        "generate_next_match_set_action",
    ]

    fieldsets = (
        (
            "Bracket Configuration",
            {
                "fields": (
                    "season",
                    "bracket_size",
                    "seeding_style",
                    "games_per_match",
                    "matches_per_stage",
                )
            },
        ),
        (
            "Status",
            {"fields": ("is_completed",)},
        ),
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("season", "season__league")

    def generate_knockout_bracket_action(self, request, queryset):
        """Generate knockout bracket and first round pairings."""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one bracket to generate.",
                messages.ERROR,
            )
            return

        bracket = queryset.first()

        try:
            # Import here to avoid circular imports
            from heltour.tournament.pairinggen import generate_knockout_bracket

            # Check if bracket already has pairings
            first_round = bracket.season.round_set.filter(number=1).first()
            if first_round and first_round.teampairing_set.exists():
                self.message_user(
                    request,
                    f"Bracket for {bracket.season} already has pairings. "
                    "Use 'Regenerate Seedings' to update seedings only.",
                    messages.ERROR,
                )
                return

            # Generate the bracket
            generate_knockout_bracket(bracket.season)

            self.message_user(
                request,
                f"Successfully generated knockout bracket for {bracket.season}.",
                messages.SUCCESS,
            )

        except Exception as e:
            self.message_user(
                request, f"Error generating knockout bracket: {str(e)}", messages.ERROR
            )

    generate_knockout_bracket_action.short_description = (
        "Generate knockout bracket and first round"
    )

    def regenerate_seedings_action(self, request, queryset):
        """Regenerate seedings for existing brackets."""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one bracket to regenerate seedings.",
                messages.ERROR,
            )
            return

        bracket = queryset.first()

        try:
            # Clear existing seedings
            KnockoutSeeding.objects.filter(bracket=bracket).delete()

            # Get active teams/players
            if bracket.season.league.competitor_type == "team":
                from heltour.tournament.models import Team

                competitors = Team.objects.filter(
                    season=bracket.season, is_active=True
                ).order_by("id")
            else:
                from heltour.tournament.models import SeasonPlayer

                season_players = (
                    SeasonPlayer.objects.filter(season=bracket.season, is_active=True)
                    .select_related("player")
                    .order_by("id")
                )
                competitors = [sp.player for sp in season_players]

            # Create new seedings
            for i, competitor in enumerate(competitors):
                KnockoutSeeding.objects.create(
                    bracket=bracket,
                    team=competitor
                    if bracket.season.league.competitor_type == "team"
                    else None,
                    # For individual tournaments, we'd need a different field
                    seed_number=i + 1,
                    is_manual_seed=False,
                )

            self.message_user(
                request,
                f"Successfully regenerated seedings for {bracket.season}. "
                f"Created {len(competitors)} seedings.",
                messages.SUCCESS,
            )

        except Exception as e:
            self.message_user(
                request, f"Error regenerating seedings: {str(e)}", messages.ERROR
            )

    regenerate_seedings_action.short_description = "Regenerate automatic seedings"

    def generate_next_match_set_action(self, request, queryset):
        """Generate next set of matches for multi-match knockout tournaments."""
        if queryset.count() != 1:
            self.message_user(
                request,
                "Please select exactly one bracket to generate next match set for.",
                messages.ERROR,
            )
            return

        bracket = queryset.first()

        # Check if this is a multi-match tournament
        if bracket.matches_per_stage <= 1:
            self.message_user(
                request,
                f"Bracket for {bracket.season} is not a multi-match tournament (matches_per_stage = {bracket.matches_per_stage}).",
                messages.ERROR,
            )
            return

        try:
            from heltour.tournament.db_to_structure import knockout_bracket_to_structure
            from heltour.tournament_core.multi_match import (
                can_generate_next_match_set,
                generate_next_match_set,
            )

            # Convert bracket to tournament structure
            tournament = knockout_bracket_to_structure(bracket)

            # Find the most recent round
            if not tournament.rounds:
                self.message_user(
                    request,
                    f"No rounds found for {bracket.season}. Generate initial bracket first.",
                    messages.ERROR,
                )
                return

            latest_round_number = max(r.number for r in tournament.rounds)

            # Check if next match set can be generated
            if not can_generate_next_match_set(tournament, latest_round_number):
                self.message_user(
                    request,
                    f"Cannot generate next match set for {bracket.season}. "
                    "Either all teams haven't completed their current matches, "
                    "or all matches for this stage are already complete.",
                    messages.WARNING,
                )
                return

            # Generate next match set
            updated_tournament = generate_next_match_set(
                tournament, latest_round_number
            )

            # Convert updated tournament back to database models
            self._create_next_match_pairings(
                updated_tournament, bracket, latest_round_number
            )

            # Update progress tracking
            from heltour.tournament.db_to_structure import (
                update_multi_match_progress_from_tournament,
            )

            update_multi_match_progress_from_tournament(updated_tournament, bracket)

            self.message_user(
                request,
                f"Successfully generated next match set for {bracket.season}. "
                f"New return matches created with flipped colors.",
                messages.SUCCESS,
            )

        except Exception as e:
            self.message_user(
                request, f"Error generating next match set: {str(e)}", messages.ERROR
            )

    generate_next_match_set_action.short_description = (
        "Generate next match set (multi-match tournaments)"
    )

    def _create_next_match_pairings(self, updated_tournament, bracket, round_number):
        """Create TeamPairing objects for the next match set."""
        import reversion
        from heltour.tournament.models import Team, Round as RoundModel, TeamPairing
        from heltour.tournament_core.multi_match import get_pairing_order_for_match

        # Get the database round for this specific tournament
        try:
            round_obj = RoundModel.objects.get(
                season=bracket.season, number=round_number
            )
        except RoundModel.MultipleObjectsReturned:
            # If multiple rounds exist, try to find the one with existing pairings
            all_rounds = RoundModel.objects.filter(
                season=bracket.season, number=round_number
            )

            # Try to find the round that has pairings
            round_with_pairings = None
            for round_candidate in all_rounds:
                pairing_count = TeamPairing.objects.filter(
                    round=round_candidate
                ).count()
                if pairing_count > 0:
                    round_with_pairings = round_candidate
                    break

            round_obj = round_with_pairings or all_rounds.first()
        except RoundModel.DoesNotExist:
            raise ValueError(
                f"Round {round_number} does not exist for season {bracket.season}"
            )

        # Find the new matches (return matches) in the updated tournament
        tournament_round = updated_tournament.rounds[round_number - 1]

        # Calculate how many matches existed before (original matches)
        total_pairs = len(
            set(
                tuple(sorted([match.competitor1_id, match.competitor2_id]))
                for match in tournament_round.matches
            )
        )

        existing_pairings_count = TeamPairing.objects.filter(round=round_obj).count()

        # Create pairings for the new matches only
        new_matches = tournament_round.matches[existing_pairings_count:]

        with reversion.create_revision():
            reversion.set_comment(
                f"Generated next match set for multi-match knockout (match {updated_tournament.current_match_number})"
            )

            for i, match in enumerate(new_matches):
                try:
                    white_team = Team.objects.get(id=match.competitor1_id)
                    black_team = Team.objects.get(id=match.competitor2_id)

                    # Calculate the correct pairing order for this return match
                    pairing_order = existing_pairings_count + i + 1

                    TeamPairing.objects.create(
                        white_team=white_team,
                        black_team=black_team,
                        round=round_obj,
                        pairing_order=pairing_order,
                    )

                except Team.DoesNotExist:
                    # Skip if teams don't exist
                    continue

    def tournament_type(self, obj):
        """Display the tournament type based on matches per stage."""
        if obj.matches_per_stage == 1:
            return "Single Elimination"
        elif obj.matches_per_stage == 2:
            return "Return Matches"
        else:
            return f"{obj.matches_per_stage}-Match Stages"

    tournament_type.short_description = "Tournament Type"


@admin.register(KnockoutSeeding)
class KnockoutSeedingAdmin(admin.ModelAdmin):
    list_display = ["bracket", "seed_number", "team", "is_manual_seed"]
    list_filter = ["is_manual_seed", "bracket__season__league"]
    search_fields = ["team__name", "bracket__season__name"]
    ordering = ("bracket", "seed_number")

    fieldsets = (
        (
            "Seeding Details",
            {"fields": ("bracket", "seed_number", "team", "is_manual_seed")},
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "bracket", "bracket__season", "bracket__season__league", "team"
            )
        )


@admin.register(KnockoutAdvancement)
class KnockoutAdvancementAdmin(admin.ModelAdmin):
    list_display = ["team", "bracket", "from_stage", "to_stage", "advanced_date"]
    list_filter = ["from_stage", "to_stage", "bracket__season__league", "advanced_date"]
    search_fields = ["team__name", "bracket__season__name"]
    ordering = ("-advanced_date",)
    readonly_fields = ("advanced_date",)

    fieldsets = (
        (
            "Advancement Details",
            {"fields": ("bracket", "team", "from_stage", "to_stage", "source_pairing")},
        ),
        (
            "Metadata",
            {
                "fields": ("advanced_date",),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "bracket",
                "bracket__season",
                "bracket__season__league",
                "team",
                "source_pairing",
            )
        )


@admin.register(TeamMultiMatchProgress)
class TeamMultiMatchProgressAdmin(admin.ModelAdmin):
    list_display = [
        "team",
        "opponent_team",
        "bracket",
        "round_number",
        "stage_name",
        "matches_completed",
        "total_matches_required",
        "progress_percentage",
        "last_updated",
    ]
    list_filter = [
        "bracket__season__league",
        "round_number",
        "stage_name",
        "matches_completed",
        "total_matches_required",
    ]
    search_fields = ["team__name", "opponent_team__name", "bracket__season__name"]
    ordering = ("bracket", "round_number", "original_pairing_order")
    readonly_fields = ("last_updated", "progress_percentage", "current_match_status")

    fieldsets = (
        (
            "Match Progress Details",
            {
                "fields": (
                    "bracket",
                    "team",
                    "opponent_team",
                    "round_number",
                    "stage_name",
                )
            },
        ),
        (
            "Progress Tracking",
            {
                "fields": (
                    "original_pairing_order",
                    "matches_completed",
                    "total_matches_required",
                    "progress_percentage",
                    "current_match_status",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("last_updated",),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related(
                "bracket",
                "bracket__season",
                "bracket__season__league",
                "team",
                "opponent_team",
            )
        )

    def progress_percentage(self, obj):
        """Display progress as percentage."""
        if obj.total_matches_required == 0:
            return "0%"
        percentage = (obj.matches_completed / obj.total_matches_required) * 100
        return f"{percentage:.0f}%"

    progress_percentage.short_description = "Progress"

    def current_match_status(self, obj):
        """Display current match status."""
        if obj.is_stage_complete_for_pair:
            return "✅ Stage Complete"
        else:
            return (
                f"🔄 Match {obj.current_match_number} of {obj.total_matches_required}"
            )

    current_match_status.short_description = "Status"
