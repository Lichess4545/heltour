from datetime import timedelta, datetime

from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from phonenumber_field.formfields import SplitPhoneNumberField
from django_countries.widgets import CountrySelectWidget

from heltour import gdpr
from heltour.tournament.models import (
    ALTERNATE_PREFERENCE_OPTIONS,
    PLAYER_NOTIFICATION_TYPES,
    GameNomination,
    InviteCode,
    ModRequest,
    PlayerNotificationSetting,
    Registration,
    RegistrationMode,
    Season,
    SeasonPlayer,
    Section,
    Team,
    TeamMember,
    normalize_gamelink,
    username_validator,
)
from heltour.tournament.workflows import ApproveRegistrationWorkflow

YES_NO_OPTIONS = (
    (
        True,
        "Yes",
    ),
    (
        False,
        "No",
    ),
)


class RegistrationForm(forms.ModelForm):
    # Override contact_number to use SplitPhoneNumberField
    contact_number = SplitPhoneNumberField(
        required=False, label=_("Contact Number"), initial=("US", "")
    )

    class Meta:
        model = Registration
        fields = (
            "email",
            "first_name",
            "last_name",
            "gender",
            "date_of_birth",
            "nationality",
            "corporate_email",
            "personal_email",
            "contact_number",
            "fide_id",
            "regional_rating",
            "has_played_20_games",
            "can_commit",
            "friends",
            "avoid",
            "agreed_to_rules",
            "agreed_to_tos",
            "alternate_preference",
            "section_preference",
            "weeks_unavailable",
        )
        labels = {
            "email": _("Your Email"),
            "first_name": _("First Name"),
            "last_name": _("Family Name"),
            "gender": _("Gender"),
            "date_of_birth": _("Date of Birth"),
            "nationality": _("Nationality"),
            "corporate_email": _("Corporate Email Address"),
            "personal_email": _("Personal Email Address (optional)"),
            "contact_number": _("Contact Number"),
            "fide_id": _("FIDE ID (optional)"),
            "regional_rating": _("Regional Rating"),
        }
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
            "gender": forms.Select(),
            "nationality": CountrySelectWidget(),
        }
        help_texts = {
            "corporate_email": _("Please use your company email address"),
            "fide_id": _("Your FIDE player ID if you have one"),
        }

    def __init__(self, *args, rules_url="", **kwargs):
        self.season = kwargs.pop("season")

        self.player = kwargs.pop("player")

        already_accepted = SeasonPlayer.objects.filter(
            season__in=self.season.section_list(), player=self.player
        ).exists()

        league = self.season.league
        super(RegistrationForm, self).__init__(*args, **kwargs)

        # Configure email field based on league settings
        if not league.email_required:
            del self.fields["email"]
        else:
            # Make email field required when email_required=True
            self.fields["email"].required = True

        # Configure name fields
        if league.require_name:
            self.fields["first_name"].required = True
            self.fields["last_name"].required = True
        else:
            del self.fields["first_name"]
            del self.fields["last_name"]

        # Configure personal email field
        if league.require_personal_email:
            self.fields["personal_email"].required = True
        else:
            del self.fields["personal_email"]

        # Configure gender field
        if league.require_gender:
            self.fields["gender"].required = True
        else:
            del self.fields["gender"]

        # Configure date of birth field
        if league.require_date_of_birth:
            self.fields["date_of_birth"].required = True
            # Set default date of birth to 18 years ago
            if not self.instance.pk:  # Only for new registrations
                eighteen_years_ago = datetime.now().date() - timedelta(days=365 * 18)
                self.fields["date_of_birth"].initial = eighteen_years_ago
        else:
            del self.fields["date_of_birth"]

        # Configure nationality field
        if league.require_nationality:
            self.fields["nationality"].required = True
        else:
            del self.fields["nationality"]

        # Configure corporate email field
        if league.require_corporate_email:
            self.fields["corporate_email"].required = True
            label = league.organisation_label or "Organisation"
            self.fields["corporate_email"].label = _(
                f"{label} Email Address"
            )
            self.fields["corporate_email"].help_text = _(
                f"Please use your {label.lower()} email address"
            )
        else:
            del self.fields["corporate_email"]

        # Configure contact number field
        if league.require_contact_number:
            self.fields["contact_number"].required = True
        else:
            del self.fields["contact_number"]

        # Configure FIDE ID field
        if league.require_fide_id:
            self.fields["fide_id"].required = True
        else:
            del self.fields["fide_id"]

        # Configure regional rating field
        if league.require_regional_rating:
            self.fields["regional_rating"].required = True
            # Update the label with the specific regional rating name if provided
            if league.regional_rating_name:
                self.fields["regional_rating"].label = _(
                    f"{league.regional_rating_name} Rating"
                )
        else:
            del self.fields["regional_rating"]

        # Add invite code field if league is invite-only
        if league.registration_mode == RegistrationMode.INVITE_ONLY:
            self.fields["invite_code"] = forms.CharField(
                max_length=50,
                required=True,
                label=_("Invite Code"),
                help_text=_("Please enter the invite code you received"),
                widget=forms.TextInput(attrs={"placeholder": "CHESS-KNIGHT-ABC12345"}),
                error_messages={
                    "required": _("Invite code is required for this league")
                },
            )
            # Field order with invite code at the beginning, then name fields if present
            priority_fields = ["invite_code"]
            if "first_name" in self.fields:
                priority_fields.append("first_name")
            if "last_name" in self.fields:
                priority_fields.append("last_name")
            field_order = priority_fields + [
                f for f in self.fields if f not in priority_fields
            ]
            self.order_fields(field_order)
        else:
            # Field order with name fields at the beginning if present
            priority_fields = []
            if "first_name" in self.fields:
                priority_fields.append("first_name")
            if "last_name" in self.fields:
                priority_fields.append("last_name")
            if priority_fields:
                field_order = priority_fields + [
                    f for f in self.fields if f not in priority_fields
                ]
                self.order_fields(field_order)

        # Rating fields
        # 20 games - remove if provisional warnings are disabled
        if league.show_provisional_warning:
            self.fields["has_played_20_games"] = forms.TypedChoiceField(
                widget=forms.HiddenInput, choices=YES_NO_OPTIONS
            )
        else:
            # Remove the field entirely when provisional warnings are disabled
            del self.fields["has_played_20_games"]
        # Can commit
        # We do not want to ask about this anymore, it was decided that it is a useless question. Hide it for now.
        self.fields["can_commit"] = forms.TypedChoiceField(
            initial=True, widget=forms.HiddenInput, choices=YES_NO_OPTIONS
        )
        # Friends and avoid
        if league.competitor_type == "team":
            # Hide friends/avoid fields if:
            # 1. Season has started (teams already created)
            # 2. Using invite-only registration (teams are pre-determined by codes)
            if (
                self.season.is_started()
                or league.registration_mode == RegistrationMode.INVITE_ONLY
            ):
                # the friends and avoid fields are for team creation. once a season is started and a teams are
                # created we do not need to ask people about this. hide those fields in that case.
                self.fields["friends"] = forms.CharField(
                    required=False, widget=forms.HiddenInput
                )
                self.fields["avoid"] = forms.CharField(
                    required=False, widget=forms.HiddenInput
                )
            else:
                self.fields["friends"] = forms.CharField(
                    required=False,
                    label=_(
                        "Are there any friends you would like to be teammates with?"
                    ),
                    help_text=_(
                        "Note: Please enter their exact Lichess usernames. "
                        "Usernames can be separated by commas, e.g.: Ledger4545, Chesster, DrNykterstein. "
                        "All players must register. All players must join Slack. "
                    ),
                )
                self.fields["avoid"] = forms.CharField(
                    required=False,
                    label=_(
                        "Are there any players you would NOT like to be teammates with?"
                    ),
                    help_text=_(
                        "Note: Please enter their exact Lichess usernames. "
                        "Usernames can be separated by commas, "
                        "e.g.: Lou-E, glbert, M0r1"
                    ),
                )
        else:
            del self.fields["friends"]
            del self.fields["avoid"]
        # Agree to rules
        if rules_url:
            rules_help_text = _(
                'You can read the rules here: <a target="_blank" href="%s">Rules Document</a>'
                % rules_url
            )
        else:
            rules_help_text = ""
        league_name = league.name
        if not league_name.endswith("League"):
            league_name += " League"

        self.fields["agreed_to_tos"] = forms.TypedChoiceField(
            required=True,
            label=_(gdpr.AGREED_TO_TOS_LABEL),
            help_text=_(gdpr.AGREED_TO_TOS_HELP_TEXT),
            choices=YES_NO_OPTIONS,
            widget=forms.RadioSelect,
            coerce=lambda x: x == "True",
        )

        self.fields["agreed_to_rules"] = forms.TypedChoiceField(
            required=True,
            label=_(gdpr.AGREED_TO_RULES_LABEL % league_name),
            help_text=rules_help_text,
            choices=YES_NO_OPTIONS,
            widget=forms.RadioSelect,
            coerce=lambda x: x == "True",
        )

        # Alternate preference
        if league.competitor_type == "team":
            # Hide alternate preference for invite-only leagues (team placement is predetermined)
            if (
                self.season.is_started()
                or league.registration_mode == RegistrationMode.INVITE_ONLY
            ):
                self.fields["alternate_preference"] = forms.ChoiceField(
                    required=False,
                    choices=ALTERNATE_PREFERENCE_OPTIONS,
                    initial="full_time",
                    widget=forms.HiddenInput(),
                )
            else:
                self.fields["alternate_preference"] = forms.ChoiceField(
                    required=True,
                    choices=ALTERNATE_PREFERENCE_OPTIONS,
                    widget=forms.RadioSelect,
                    label=_(
                        "Are you interested in being an alternate or a full time player?"
                    ),
                    help_text=_(
                        "Players are put into teams on a first come first served basis, based on registration date. "
                        "You may be an alternate even if you request to be a full time player."
                    ),
                )
        else:
            del self.fields["alternate_preference"]

        section_list = self.season.section_list()
        if len(section_list) > 1:
            section_options = [("", "No preference (use my rating)")]
            section_options += [(s.section.id, s.section.name) for s in section_list]
            self.fields["section_preference"] = forms.ChoiceField(
                required=False,
                choices=section_options,
                widget=forms.RadioSelect,
                label=_("Which section would you prefer to play in?"),
                help_text=_(
                    "You may be placed in a different section depending on eligibility."
                ),
            )
        else:
            del self.fields["section_preference"]

        # Weeks unavailable - if player is already accepted they can edit their availability in the player dashboard
        # Also respect the league setting for asking availability
        if (
            self.season.round_duration == timedelta(days=7)
            and not already_accepted
            and league.ask_availability
        ):
            weeks = [
                (
                    r.number,
                    "Round %s (%s - %s)"
                    % (
                        r.number,
                        (
                            r.start_date.strftime("%b %-d")
                            if r.start_date is not None
                            else "?"
                        ),
                        (
                            r.end_date.strftime("%b %-d")
                            if r.end_date is not None
                            else "?"
                        ),
                    ),
                )
                for r in self.season.round_set.order_by("number")
            ]
            toggle_attrs = {
                "data-toggle": "toggle",
                "data-on": "Unavailable",
                "data-off": "Available",
                "data-onstyle": "default",
                "data-offstyle": "success",
                "data-size": "small",
            }
            self.fields["weeks_unavailable"] = forms.MultipleChoiceField(
                required=False,
                label=_("Indicate any rounds you would not be able to play."),
                choices=weeks,
                widget=forms.CheckboxSelectMultiple(attrs=toggle_attrs),
            )
        else:
            del self.fields["weeks_unavailable"]

    def save(self, commit=True, *args, **kwargs):
        registration = super(RegistrationForm, self).save(commit=False, *args, **kwargs)
        registration.season = self.season
        registration.player = self.player

        # Handle invite code for invite-only leagues
        if hasattr(self, "invite_code_obj") and self.invite_code_obj:
            registration.invite_code_used = self.invite_code_obj

        is_new = registration.pk is None
        fields_changed = set(self.changed_data) & {
            "alternate_preference",
            "section_preference",
            "weeks_unavailable",
        }

        # Auto-approve registrations with valid invite codes
        should_auto_approve = (
            is_new
            and hasattr(self, "invite_code_obj")
            and self.invite_code_obj
            and self.season.league.registration_mode == RegistrationMode.INVITE_ONLY
        )

        if should_auto_approve:
            registration.status = "approved"
        elif is_new:
            # Only set to pending if it's a new registration without auto-approval
            registration.status = "pending"
        elif fields_changed:
            # For existing registrations, only change to pending if specific fields changed
            registration.status = "pending"

        if commit:
            registration.save()
            # Mark the invite code as used after saving the registration
            if hasattr(self, "invite_code_obj") and self.invite_code_obj:
                self.invite_code_obj.mark_used(self.player)

                # Handle auto-approval for invite codes
                if should_auto_approve and self.invite_code_obj:
                    from heltour.tournament.models import SeasonPlayer, TeamMember
                    from heltour.tournament.workflows import add_player_to_team

                    # Create or update SeasonPlayer for both captain and team member codes
                    sp, created = SeasonPlayer.objects.update_or_create(
                        player=self.player,
                        season=self.season,
                        defaults={"registration": registration, "is_active": True},
                    )

                    # Only handle team assignment for team_member codes
                    if (
                        self.invite_code_obj.code_type == "team_member"
                        and self.invite_code_obj.team
                    ):
                        existing_member = TeamMember.objects.filter(
                            player=self.player, team__season=self.season
                        ).first()

                        if not existing_member:
                            # Add player to existing team
                            add_player_to_team(self.player, self.invite_code_obj.team)
                    # For captain codes, we auto-approve but don't create the team yet - they need to complete setup first

        registration.player.agreed_to_tos()
        return registration

    def clean(self):
        cd = super().clean()
        for field_name in [
            "agreed_to_tos",
            "agreed_to_rules",
            "can_commit",
        ]:
            if not cd.get(field_name, False):
                self.add_error(field_name, _(gdpr.MISSING_CONSENT_MESSAGE))
        return cd

    def clean_invite_code(self):
        """Validate the invite code for invite-only leagues."""
        if self.season.league.registration_mode != RegistrationMode.INVITE_ONLY:
            return None

        code = self.cleaned_data.get("invite_code", "").strip()
        if not code:
            raise ValidationError(_("Invite code is required for this league"))

        # Look up the invite code (case-insensitive)
        invite_code = InviteCode.get_by_code(code, self.season.league, self.season)

        if not invite_code:
            raise ValidationError(_("Invalid invite code"))

        if not invite_code.is_available():
            raise ValidationError(_("This invite code has already been used"))

        # Store the invite code object for use in save()
        self.invite_code_obj = invite_code
        return code

    def clean_weeks_unavailable(self):
        # If the field was deleted from the form, skip validation
        if "weeks_unavailable" not in self.fields:
            return ""

        upcoming_rounds = [
            r
            for r in self.season.round_set.order_by("number")
            if r.start_date and r.start_date > timezone.now()
        ]
        upcoming_rounds_available = [
            r
            for r in upcoming_rounds
            if str(r.number) not in self.cleaned_data["weeks_unavailable"]
        ]
        upcoming_rounds_unavailable = [
            r
            for r in upcoming_rounds
            if str(r.number) in self.cleaned_data["weeks_unavailable"]
        ]
        if len(upcoming_rounds_available) == 0 and len(upcoming_rounds_unavailable) > 0:
            raise ValidationError(
                "You can't mark yourself as unavailable for all upcoming rounds."
            )
        return ",".join(self.cleaned_data["weeks_unavailable"])

    def clean_section_preference(self):
        # If the field was deleted from the form, skip validation
        if "section_preference" not in self.fields:
            return None

        if self.cleaned_data["section_preference"] == "":
            return None
        return Section.objects.get(pk=int(self.cleaned_data["section_preference"]))


class ReviewRegistrationForm(forms.Form):
    pass


class ApproveRegistrationForm(forms.Form):
    invite_to_slack = forms.BooleanField(required=False)
    send_confirm_email = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        reg = kwargs.pop("registration")
        super(ApproveRegistrationForm, self).__init__(*args, **kwargs)

        workflow = ApproveRegistrationWorkflow(reg)

        self.fields["send_confirm_email"].initial = workflow.default_send_confirm_email
        self.fields["invite_to_slack"].initial = workflow.default_invite_to_slack

        section_list = reg.season.section_list()
        if len(section_list) > 1:
            section_options = [
                (season.id, season.section.name) for season in section_list
            ]
            self.fields["section"] = forms.ChoiceField(
                choices=section_options, initial=workflow.default_section.id
            )

        if workflow.is_late:
            self.fields["retroactive_byes"] = forms.IntegerField(
                initial=workflow.default_byes
            )
            self.fields["late_join_points"] = forms.FloatField(
                initial=workflow.default_ljp
            )

    def clean_section(self):
        return Season.objects.get(pk=int(self.cleaned_data["section"]))


class RejectRegistrationForm(forms.Form):

    def __init__(self, *args, **kwargs):
        _ = kwargs.pop("registration")
        super(RejectRegistrationForm, self).__init__(*args, **kwargs)


class ModRequestForm(forms.ModelForm):
    class Meta:
        model = ModRequest
        fields = ("notes", "screenshot")
        labels = {
            "notes": _("Notes"),
            "screenshot": _("Screenshot (if applicable)"),
        }


class ReviewModRequestForm(forms.Form):
    pass


class ApproveModRequestForm(forms.Form):
    response = forms.CharField(required=False, max_length=1024, widget=forms.Textarea)


class RejectModRequestForm(forms.Form):
    response = forms.CharField(required=False, max_length=1024, widget=forms.Textarea)


class ImportSeasonForm(forms.Form):
    spreadsheet_url = forms.CharField(label="Spreadsheet URL", max_length=1023)
    season_name = forms.CharField(label="Season name", max_length=255)
    season_tag = forms.SlugField(label="Season tag")
    rosters_only = forms.BooleanField(required=False, label="Rosters only")
    exclude_live_pairings = forms.BooleanField(
        required=False, label="Exclude live pairings"
    )


class GeneratePairingsForm(forms.Form):
    overwrite_existing = forms.BooleanField(
        required=False, label="Overwrite existing pairings"
    )
    run_in_background = forms.BooleanField(required=False, label="Run in background")
    auto_assign_forfeits = forms.BooleanField(
        required=False,
        label="Auto-assign forfeit wins for missing players",
        help_text="Automatically assign forfeit results for board pairings with missing players",
    )
    publish_immediately = forms.BooleanField(
        required=False,
        label="Publish pairings immediately",
        help_text="Make pairings visible to players immediately after generation",
    )


class ReviewPairingsForm(forms.Form):
    pass


class EditRostersForm(forms.Form):
    changes = forms.CharField(widget=forms.HiddenInput)


class RoundTransitionForm(forms.Form):
    def __init__(
        self,
        is_team_league,
        round_to_close,
        round_to_open,
        season_to_close,
        *args,
        **kwargs,
    ):
        super(RoundTransitionForm, self).__init__(*args, **kwargs)

        if round_to_close is not None:
            self.fields["complete_round"] = forms.BooleanField(
                initial=True,
                required=False,
                label="Set round %d as completed" % round_to_close.number,
            )
            self.fields["round_to_close"] = forms.IntegerField(
                initial=round_to_close.number, widget=forms.HiddenInput
            )

        if season_to_close is not None:
            self.fields["complete_season"] = forms.BooleanField(
                initial=True,
                required=False,
                label="Set %s as completed" % season_to_close.name,
            )

        if round_to_open is not None:
            if is_team_league:
                self.fields["update_board_order"] = forms.BooleanField(
                    initial=False, required=False, label="Update board order"
                )
            self.fields["generate_pairings"] = forms.BooleanField(
                initial=True,
                required=False,
                label="Generate pairings for round %d" % round_to_open.number,
            )
            self.fields["auto_assign_forfeits"] = forms.BooleanField(
                initial=True,
                required=False,
                label="Auto-assign forfeit wins for missing players",
                help_text="Automatically assign forfeit results for board pairings with missing players",
            )
            self.fields["publish_immediately"] = forms.BooleanField(
                initial=False,
                required=False,
                label="Publish pairings immediately",
                help_text="Make pairings visible to players immediately after generation",
            )
            self.fields["round_to_open"] = forms.IntegerField(
                initial=round_to_open.number, widget=forms.HiddenInput
            )


class NominateForm(forms.Form):
    game_link = forms.URLField(required=False)

    def __init__(
        self,
        season,
        player,
        current_nominations,
        max_nominations,
        season_pairings,
        *args,
        **kwargs,
    ):
        super(NominateForm, self).__init__(*args, **kwargs)
        self.season = season
        self.player = player
        self.current_nominations = current_nominations
        self.max_nominations = max_nominations
        self.season_pairings = season_pairings

    def clean_game_link(self):
        game_link, ok = normalize_gamelink(self.cleaned_data["game_link"])
        if not ok:
            raise ValidationError("Invalid game link.", code="invalid")
        if len(self.current_nominations) >= self.max_nominations:
            raise ValidationError(
                "You've reached the nomination limit. Delete one before nominating again.",
                code="invalid",
            )
        if GameNomination.objects.filter(
            season=self.season, nominating_player=self.player, game_link=game_link
        ).exists():
            raise ValidationError("You have already nominated this game.")
        self.pairing = self.season_pairings.filter(game_link=game_link).first()
        if self.pairing is None:
            raise ValidationError(
                "The game link doesn't match any pairings this season."
            )
        return game_link


class DeleteNominationForm(forms.Form):
    pass


class ContactForm(forms.Form):
    league = forms.ChoiceField(choices=[])
    your_lichess_username = forms.CharField(max_length=255, required=False)
    your_email_address = forms.EmailField(max_length=255)
    subject = forms.CharField(max_length=140)
    message = forms.CharField(max_length=1024, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        leagues = kwargs.pop("leagues")
        super(ContactForm, self).__init__(*args, **kwargs)

        self.fields["league"] = forms.ChoiceField(
            choices=[(league.tag, league.name) for league in leagues]
        )


class BulkEmailForm(forms.Form):
    subject = forms.CharField(max_length=140)
    html_content = forms.CharField(
        max_length=4096, required=True, widget=CKEditorUploadingWidget()
    )
    text_content = forms.CharField(
        max_length=4096, required=True, widget=forms.Textarea
    )
    confirm_send = forms.BooleanField()

    def __init__(self, player_count, *args, **kwargs):
        super(BulkEmailForm, self).__init__(*args, **kwargs)

        self.fields["confirm_send"].label = (
            "Yes, I'm sure - send emails to %d players" % (player_count)
        )


class TeamSpamForm(forms.Form):
    text = forms.CharField(max_length=4096, required=True, widget=forms.Textarea)
    confirm_send = forms.BooleanField()

    def __init__(self, season, *args, **kwargs):
        super(TeamSpamForm, self).__init__(*args, **kwargs)

        self.fields["confirm_send"].label = (
            "Yes, I'm sure - send spam to %d teams in %s"
            % (season.team_set.count(), season.name)
        )


class TvFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        current_league = kwargs.pop("current_league")
        leagues = kwargs.pop("leagues")
        boards = kwargs.pop("boards")
        teams = kwargs.pop("teams")
        super(TvFilterForm, self).__init__(*args, **kwargs)

        self.fields["league"] = forms.ChoiceField(
            choices=[("all", "All Leagues")]
            + [(league.tag, league.name) for league in leagues],
            initial=current_league.tag,
        )
        if boards is not None and len(boards) > 0:
            self.fields["board"] = forms.ChoiceField(
                choices=[("all", "All Boards")] + [(n, "Board %d" % n) for n in boards]
            )
        if teams is not None and len(teams) > 0:
            self.fields["team"] = forms.ChoiceField(
                choices=[("all", "All Teams")]
                + [(team.number, team.name) for team in teams]
            )


class TvTimezoneForm(forms.Form):
    timezone = forms.ChoiceField(choices=[("local", "Local"), ("utc", "UTC")])


class NotificationsForm(forms.Form):
    def __init__(self, league, player, *args, **kwargs):
        super(NotificationsForm, self).__init__(*args, **kwargs)
        for type_, _ in PLAYER_NOTIFICATION_TYPES:
            setting = PlayerNotificationSetting.get_or_default(
                player=player, league=league, type=type_
            )
            self.fields[type_ + "_lichess"] = forms.BooleanField(
                required=False, label="Lichess", initial=setting.enable_lichess_mail
            )
            self.fields[type_ + "_slack"] = forms.BooleanField(
                required=False, label="Slack", initial=setting.enable_slack_im
            )
            # users should not be able to switch off the pairing messages in slack,
            # as they have to reply to those messages to be considered responsive
            is_round_started_type = type_ == "round_started"
            self.fields[type_ + "_slack_wo"] = forms.BooleanField(
                required=False,
                label="Slack (with opponent)",
                initial=is_round_started_type or setting.enable_slack_mpim,
                disabled=is_round_started_type,
            )
            # users cannot switch off lichess messages for started games, as the bulk api requires us to send those
            is_game_started_type = type_ == "game_started"
            self.fields[type_ + "_lichess"] = forms.BooleanField(
                required=False,
                label="Lichess",
                initial=is_game_started_type,
                disabled=is_game_started_type,
            )
            if type_ == "before_game_time":
                offset_options = [
                    (5, "5 minutes"),
                    (10, "10 minutes"),
                    (20, "20 minutes"),
                    (30, "30 minutes"),
                    (60, "1 hour"),
                    (120, "2 hours"),
                ]
                self.fields[type_ + "_offset"] = forms.TypedChoiceField(
                    choices=offset_options,
                    initial=int(setting.offset.total_seconds() / 60),
                    coerce=int,
                )


class LoginForm(forms.Form):
    lichess_username = forms.CharField(
        max_length=255, required=False, validators=[username_validator]
    )


class MoveLateRegForm(forms.Form):
    update_fields = forms.BooleanField(initial=True)
    prev_round = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        reg = kwargs.pop("reg")
        super(MoveLateRegForm, self).__init__(*args, **kwargs)
        self.fields["prev_round"].initial = reg.round.number


class CreateTeamsForm(forms.Form):
    count = forms.IntegerField(
        min_value=1,
        initial=20,
        label="Count",
        help_text="Number of iterations to run the algorithm looking "
        'for the "happiest" league',
    )

    balance = forms.FloatField(
        min_value=0,
        max_value=1,
        initial=0.8,
        label="Balance",
        help_text="Ratio of team members to alternates.  A value of 0.8 "
        "means 20% will be made alternates",
    )
    confirm_create = forms.BooleanField()

    def __init__(self, team_count, *args, **kwargs):
        super(CreateTeamsForm, self).__init__(*args, **kwargs)

        self.fields["confirm_create"].label = (
            f"Yes, I'm sure. Delete {team_count} teams and regenerate"
        )


class GenerateTeamInviteCodeForm(forms.Form):
    """Form for team captains to generate invite codes for their team"""

    count = forms.IntegerField(
        min_value=1,
        max_value=5,
        initial=1,
        label="Number of codes",
        help_text="Generate 1-5 invite codes at once",
    )

    def __init__(self, *args, team=None, season=None, player=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.team = team
        self.season = season
        self.player = player

    def clean(self):
        cleaned_data = super().clean()

        if self.player and not hasattr(self, "skip_limit_check"):
            # Check if captain hasn't exceeded their limit
            existing_codes = InviteCode.objects.filter(
                season=self.season, created_by_captain=self.player
            ).count()

            requested_count = cleaned_data.get("count", 0)

            if existing_codes + requested_count > self.season.codes_per_captain_limit:
                remaining = self.season.codes_per_captain_limit - existing_codes
                if remaining == 0:
                    raise forms.ValidationError(
                        f"You have reached your limit of {self.season.codes_per_captain_limit} invite codes."
                    )
                else:
                    raise forms.ValidationError(
                        f'You can only create {remaining} more invite code{"s" if remaining != 1 else ""}. '
                        f"You have created {existing_codes} out of {self.season.codes_per_captain_limit} allowed."
                    )

        return cleaned_data

    def save(self, created_by):
        """Generate the invite codes"""
        count = self.cleaned_data["count"]
        codes = []

        for _ in range(count):
            code = InviteCode(
                league=self.team.season.league,
                season=self.season,
                code=InviteCode.generate_code(),
                code_type="team_member",
                team=self.team,
                created_by=created_by if created_by.is_staff else None,
                created_by_captain=self.player if self.player else None,
                notes=f"Created for team {self.team.name}",
            )

            # Ensure unique code
            while InviteCode.objects.filter(code=code.code).exists():
                code.code = InviteCode.generate_code()

            code.save()
            codes.append(code)

        return codes


class TeamCreateForm(forms.Form):
    """Form for creating a new team with all required information"""

    team_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Team Name",
        help_text="Enter a name for your team (max 100 characters)",
    )
    company_name = forms.CharField(
        max_length=255,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Company Name",
    )
    company_address = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        label="Company Office Address",
    )
    team_contact_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control"}),
        label="Team Contact Email",
    )
    team_contact_number = SplitPhoneNumberField(
        required=True, label="Team Contact Number", initial=["US", ""]
    )

    def __init__(self, *args, **kwargs):
        self.season = kwargs.pop("season")
        self.player = kwargs.pop("player")
        super().__init__(*args, **kwargs)
        label = self.season.league.organisation_label or "Company / University / Organisation"
        self.fields["company_name"].label = f"{label} Name"
        self.fields["company_address"].label = "Physical Address"

    def clean_team_name(self):
        name = self.cleaned_data["team_name"].strip()
        if not name:
            raise forms.ValidationError("Team name cannot be empty")
        # Check if team name already exists in this season
        if Team.objects.filter(season=self.season, name=name).exists():
            raise forms.ValidationError("A team with this name already exists")
        return name

    def save(self):
        # Get the next available team number
        existing_numbers = Team.objects.filter(season=self.season).values_list(
            "number", flat=True
        )
        team_number = 1
        while team_number in existing_numbers:
            team_number += 1

        # Create the team
        team = Team.objects.create(
            season=self.season,
            number=team_number,
            name=self.cleaned_data["team_name"],
            company_name=self.cleaned_data["company_name"],
            company_address=self.cleaned_data["company_address"],
            team_contact_email=self.cleaned_data["team_contact_email"],
            team_contact_number=self.cleaned_data["team_contact_number"],
            is_active=True,
            slack_channel="",
        )

        # Create captain membership
        TeamMember.objects.create(
            team=team,
            player=self.player,
            board_number=1,
            is_captain=True,
            is_vice_captain=False,
        )

        return team


class TeamNameEditForm(forms.Form):
    """Simple form for editing team name only"""

    team_name = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control"}),
        label="Team Name",
        help_text="Enter a new name for your team (max 100 characters)",
    )

    def __init__(self, *args, **kwargs):
        self.team = kwargs.pop("team")
        super().__init__(*args, **kwargs)
        self.fields["team_name"].initial = self.team.name

    def clean_team_name(self):
        name = self.cleaned_data["team_name"].strip()
        if not name:
            raise forms.ValidationError("Team name cannot be empty")
        # Check if another team has this name (only if name changed)
        if (
            name != self.team.name
            and Team.objects.filter(season=self.team.season, name=name).exists()
        ):
            raise forms.ValidationError("A team with this name already exists")
        return name

    def save(self):
        self.team.name = self.cleaned_data["team_name"]
        self.team.save()
        return self.team


class BoardOrderForm(forms.Form):
    """Form for reordering team board assignments"""

    def __init__(self, *args, **kwargs):
        self.team = kwargs.pop("team")
        self.user = kwargs.pop("user")
        self.upcoming_round = kwargs.pop("upcoming_round", None)
        super().__init__(*args, **kwargs)

        # Create fields for each team member
        team_members = self.team.teammember_set.select_related("player").order_by(
            "board_number"
        )

        # Allow assigning up to the total number of team members, with some buffer for flexibility
        max_board = max(self.team.season.boards, team_members.count() + 2)

        for member in team_members:
            self.fields[f"player_{member.player.id}"] = forms.IntegerField(
                min_value=1,
                max_value=max_board,
                initial=member.board_number,
                label=member.player.lichess_username,
                widget=forms.NumberInput(
                    attrs={"class": "form-control board-number-input"}
                ),
            )

    def clean(self):
        cleaned_data = super().clean()

        # Check deadline if not admin
        if self.upcoming_round and not self.user.is_staff:
            if not self.upcoming_round.is_board_update_allowed():
                deadline = self.upcoming_round.get_board_update_deadline()
                raise forms.ValidationError(
                    f'Board assignments are locked. The deadline was {deadline.strftime("%Y-%m-%d %H:%M %Z")}.'
                )

        # Collect all board numbers
        board_numbers = []
        for field_name, value in cleaned_data.items():
            if field_name.startswith("player_") and value is not None:
                board_numbers.append(value)

        # Only validate if we have board numbers
        if board_numbers:
            # Check for duplicates
            if len(board_numbers) != len(set(board_numbers)):
                raise forms.ValidationError("Each board number must be unique.")

            # Check that all assigned boards are within valid range
            invalid_boards = [
                b for b in board_numbers if b > self.team.season.boards + 2
            ]
            if invalid_boards:
                invalid_list = sorted(list(set(invalid_boards)))
                raise forms.ValidationError(
                    f"Board numbers {invalid_list} are too high. Maximum allowed is {self.team.season.boards + 2}."
                )

        return cleaned_data

    def save(self):
        """Update board assignments"""
        with transaction.atomic():
            # First, collect all the changes
            updates = []
            for field_name, board_number in self.cleaned_data.items():
                if field_name.startswith("player_"):
                    player_id = int(field_name.replace("player_", ""))
                    member = self.team.teammember_set.get(player_id=player_id)
                    if member.board_number != board_number:
                        updates.append((member, board_number))

            if not updates:
                return  # No changes to make

            # Use a temporary high board number to avoid conflicts
            # Find a safe temporary number that's outside the valid range
            max_board = self.team.season.boards
            temp_start = max_board + 100

            # Step 1: Move all changing members to temporary high board numbers
            for i, (member, _) in enumerate(updates):
                member.board_number = temp_start + i
                member.save()

            # Step 2: Now set the actual new board numbers
            for member, new_board_number in updates:
                member.board_number = new_board_number
                member.save()
