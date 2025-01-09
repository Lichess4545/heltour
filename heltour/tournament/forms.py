from django import forms
from django.utils.translation import gettext_lazy as _
from ckeditor_uploader.widgets import CKEditorUploadingWidget

from .models import *
from django.core.exceptions import ValidationError
from heltour import settings
from django.urls import reverse
from heltour.tournament.workflows import ApproveRegistrationWorkflow
from heltour import gdpr

YES_NO_OPTIONS = (
    (True, 'Yes',),
    (False, 'No',),
)


class RegistrationForm(forms.ModelForm):

    class Meta:
        model = Registration
        fields = (
            'email',
            'has_played_20_games',
            'can_commit', 'friends', 'avoid', 'agreed_to_rules', 'agreed_to_tos',
            'alternate_preference', 'section_preference', 'weeks_unavailable',
        )
        labels = {
            'email': _('Your Email'),
        }

    def __init__(self, *args, rules_url='', **kwargs):
        self.season = kwargs.pop('season')
        
        self.username = kwargs.pop('user')
        
        already_accepted = SeasonPlayer.objects.filter(
            season__in=self.season.section_list(), player__lichess_username=self.username).exists()
        
        league = self.season.league
        super(RegistrationForm, self).__init__(*args, **kwargs)

        # Rating fields
        # 20 games
        self.fields['has_played_20_games'] = forms.TypedChoiceField(widget=forms.HiddenInput, choices=YES_NO_OPTIONS)
        # Can commit
        time_control = league.time_control
        self.fields['can_commit'] = forms.TypedChoiceField(initial=True, widget=forms.HiddenInput, choices=YES_NO_OPTIONS)
        # Friends and avoid
        if league.competitor_type == 'team':
            if self.season.is_started():
                self.fields['friends'] = forms.CharField(required=False, widget=forms.HiddenInput)
                self.fields['avoid'] = forms.CharField(required=False, widget=forms.HiddenInput)
            else:
                self.fields['friends'] = forms.CharField(required=False, label=_(
                    'Are there any friends you would like to be teammates with?'),
                                                         help_text=_(
                                                             'Note: Please enter their exact Lichess usernames. Usernames can be separated by commas, e.g.: Ledger4545, Chesster, DrNykterstein. All players must register. All players must join Slack. All players should also request each other.'))
                self.fields['avoid'] = forms.CharField(required=False, label=_(
                    'Are there any players you would NOT like to be teammates with?'),
                                                       help_text=_(
                                                           'Note: Please enter their exact Lichess usernames. Usernames can be separated by commas, e.g.: Lou-E, glbert, M0r1'))
        else:
            del self.fields['friends']
            del self.fields['avoid']
        # Agree to rules
        if rules_url:
            rules_help_text = _('You can read the rules here: <a target="_blank" href="%s">Rules Document</a>' % rules_url)
        else:
            rules_help_text = ''
        league_name = league.name
        if not league_name.endswith('League'):
            league_name += ' League'

        self.fields['agreed_to_tos'] = \
            forms.TypedChoiceField(
                required=True,
                label=_(gdpr.AGREED_TO_TOS_LABEL),
                help_text=_(gdpr.AGREED_TO_TOS_HELP_TEXT),
                choices=YES_NO_OPTIONS,
                widget=forms.RadioSelect,
                coerce=lambda x: x == 'True'
            )


        self.fields['agreed_to_rules'] = \
            forms.TypedChoiceField(
                required=True,
                label=_(gdpr.AGREED_TO_RULES_LABEL % league_name),
                help_text=rules_help_text,
                choices=YES_NO_OPTIONS,
                widget=forms.RadioSelect,
                coerce=lambda x: x == 'True'
            )

        # Alternate preference
        if league.competitor_type == 'team':
            if self.season.is_started():
                self.fields['alternate_preference'] = forms.ChoiceField(required=False,
                                                                        choices=ALTERNATE_PREFERENCE_OPTIONS,
                                                                        initial='full_time',
                                                                        widget=forms.HiddenInput())
            else:
                self.fields['alternate_preference'] = forms.ChoiceField(required=True,
                                                                        choices=ALTERNATE_PREFERENCE_OPTIONS,
                                                                        widget=forms.RadioSelect,
                                                                        label=_(
                                                                            'Are you interested in being an alternate or a full time player?'),
                                                                        help_text=_(
                                                                            'Players are put into teams on a first come first served basis, based on registration date. \
                                                                            You may be an alternate even if you request to be a full time player.'))
        else:
            del self.fields['alternate_preference']

        section_list = self.season.section_list()
        if len(section_list) > 1:
            section_options = [('', 'No preference (use my rating)')]
            section_options += [(s.section.id, s.section.name) for s in section_list]
            self.fields['section_preference'] = forms.ChoiceField(required=False,
                                                                  choices=section_options,
                                                                  widget=forms.RadioSelect,
                                                                  label=_(
                                                                      'Which section would you prefer to play in?'),
                                                                  help_text=_(
                                                                      'You may be placed in a different section depending on eligibility.'))
        else:
            del self.fields['section_preference']

        # Weeks unavailable - if player is already accepted they can edit their availability in the player dashboard
        if self.season.round_duration == timedelta(days=7) and not already_accepted:
            weeks = [(r.number, 'Round %s (%s - %s)' %
                      (r.number,
                       r.start_date.strftime('%b %-d') if r.start_date is not None else '?',
                       r.end_date.strftime('%b %-d') if r.end_date is not None else '?'))
                     for r in self.season.round_set.order_by('number')]
            toggle_attrs = {
                'data-toggle': 'toggle',
                'data-on': 'Unavailable',
                'data-off': 'Available',
                'data-onstyle': 'default',
                'data-offstyle': 'success',
                'data-size': 'small',
            }
            self.fields['weeks_unavailable'] = forms.MultipleChoiceField(required=False, label=_(
                'Indicate any rounds you would not be able to play.'),
                                                                         choices=weeks,
                                                                         widget=forms.CheckboxSelectMultiple(
                                                                             attrs=toggle_attrs))
        else:
            del self.fields['weeks_unavailable']


    def save(self, commit=True, *args, **kwargs):
        registration = super(RegistrationForm, self).save(commit=False, *args, **kwargs)
        registration.season = self.season
        registration.lichess_username = str(self.username)

        is_new = registration.pk is None
        fields_changed = set(self.changed_data) & {
            "alternate_preference",
            "section_preference",
            "weeks_unavailable",
        }

        if is_new or fields_changed:
            registration.status = "pending"

        if commit:
            registration.save()
        registration.player().agreed_to_tos()
        return registration

    def clean(self):
        cd = super().clean()
        for field_name in [
            'agreed_to_tos',
            'agreed_to_rules',
            'can_commit',
        ]:
            if not cd.get(field_name, False):
                self.add_error(
                    field_name,
                    _(gdpr.MISSING_CONSENT_MESSAGE)
                )
        return cd



    def clean_weeks_unavailable(self):
        upcoming_rounds = [r for r in self.season.round_set.order_by('number') if
                           r.start_date > timezone.now()]
        upcoming_rounds_available = [r for r in upcoming_rounds if
                                     str(r.number) not in self.cleaned_data['weeks_unavailable']]
        upcoming_rounds_unavailable = [r for r in upcoming_rounds if
                                       str(r.number) in self.cleaned_data['weeks_unavailable']]
        if len(upcoming_rounds_available) == 0 and len(upcoming_rounds_unavailable) > 0:
            raise ValidationError(
                'You can\'t mark yourself as unavailable for all upcoming rounds.')
        return ','.join(self.cleaned_data['weeks_unavailable'])

    def clean_section_preference(self):
        if self.cleaned_data['section_preference'] == '':
            return None
        return Section.objects.get(pk=int(self.cleaned_data['section_preference']))


class ReviewRegistrationForm(forms.Form):
    pass


class ApproveRegistrationForm(forms.Form):
    invite_to_slack = forms.BooleanField(required=False)
    send_confirm_email = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('registration')
        super(ApproveRegistrationForm, self).__init__(*args, **kwargs)

        workflow = ApproveRegistrationWorkflow(reg)

        self.fields['send_confirm_email'].initial = workflow.default_send_confirm_email
        self.fields['invite_to_slack'].initial = workflow.default_invite_to_slack

        section_list = reg.season.section_list()
        if len(section_list) > 1:
            section_options = [(season.id, season.section.name) for season in section_list]
            self.fields['section'] = forms.ChoiceField(choices=section_options,
                                                       initial=workflow.default_section.id)

        if workflow.is_late:
            self.fields['retroactive_byes'] = forms.IntegerField(initial=workflow.default_byes)
            self.fields['late_join_points'] = forms.FloatField(initial=workflow.default_ljp)

    def clean_section(self):
        return Season.objects.get(pk=int(self.cleaned_data['section']))


class RejectRegistrationForm(forms.Form):

    def __init__(self, *args, **kwargs):
        _ = kwargs.pop('registration')
        super(RejectRegistrationForm, self).__init__(*args, **kwargs)


class ModRequestForm(forms.ModelForm):
    class Meta:
        model = ModRequest
        fields = (
            'notes', 'screenshot'
        )
        labels = {
            'notes': _('Notes'),
            'screenshot': _('Screenshot (if applicable)'),
        }


class ReviewModRequestForm(forms.Form):
    pass


class ApproveModRequestForm(forms.Form):
    response = forms.CharField(required=False, max_length=1024, widget=forms.Textarea)


class RejectModRequestForm(forms.Form):
    response = forms.CharField(required=False, max_length=1024, widget=forms.Textarea)


class ImportSeasonForm(forms.Form):
    spreadsheet_url = forms.CharField(label='Spreadsheet URL', max_length=1023)
    season_name = forms.CharField(label='Season name', max_length=255)
    season_tag = forms.SlugField(label='Season tag')
    rosters_only = forms.BooleanField(required=False, label='Rosters only')
    exclude_live_pairings = forms.BooleanField(required=False, label='Exclude live pairings')


class GeneratePairingsForm(forms.Form):
    overwrite_existing = forms.BooleanField(required=False, label='Overwrite existing pairings')
    run_in_background = forms.BooleanField(required=False, label='Run in background')


class ReviewPairingsForm(forms.Form):
    pass


class EditRostersForm(forms.Form):
    changes = forms.CharField(widget=forms.HiddenInput)
    rating_type = forms.ChoiceField(
        choices=[('actual', 'Actual Ratings'), ('expected', 'Expected Ratings')])


class RoundTransitionForm(forms.Form):
    def __init__(self, is_team_league, round_to_close, round_to_open, season_to_close, *args,
                 **kwargs):
        super(RoundTransitionForm, self).__init__(*args, **kwargs)

        if round_to_close is not None:
            self.fields['complete_round'] = forms.BooleanField(initial=True,
                                                               required=False,
                                                               label='Set round %d as completed' % round_to_close.number)
            self.fields['round_to_close'] = forms.IntegerField(initial=round_to_close.number,
                                                               widget=forms.HiddenInput)

        if season_to_close is not None:
            self.fields['complete_season'] = forms.BooleanField(initial=True,
                                                                required=False,
                                                                label='Set %s as completed' % season_to_close.name)

        if round_to_open is not None:
            if is_team_league:
                self.fields['update_board_order'] = forms.BooleanField(initial=True,
                                                                       required=False,
                                                                       label='Update board order')
            self.fields['generate_pairings'] = forms.BooleanField(initial=True,
                                                                  required=False,
                                                                  label='Generate pairings for round %d' % round_to_open.number)
            self.fields['round_to_open'] = forms.IntegerField(initial=round_to_open.number,
                                                              widget=forms.HiddenInput)


class NominateForm(forms.Form):
    game_link = forms.URLField(required=False)

    def __init__(self, season, player, current_nominations, max_nominations, season_pairings, *args,
                 **kwargs):
        super(NominateForm, self).__init__(*args, **kwargs)
        self.season = season
        self.player = player
        self.current_nominations = current_nominations
        self.max_nominations = max_nominations
        self.season_pairings = season_pairings

    def clean_game_link(self):
        game_link, ok = normalize_gamelink(self.cleaned_data['game_link'])
        if not ok:
            raise ValidationError('Invalid game link.', code='invalid')
        if len(self.current_nominations) >= self.max_nominations:
            raise ValidationError(
                'You\'ve reached the nomination limit. Delete one before nominating again.',
                code='invalid')
        if GameNomination.objects.filter(season=self.season, nominating_player=self.player,
                                         game_link=game_link).exists():
            raise ValidationError('You have already nominated this game.')
        self.pairing = self.season_pairings.filter(game_link=game_link).first()
        if self.pairing is None:
            raise ValidationError('The game link doesn\'t match any pairings this season.')
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
        leagues = kwargs.pop('leagues')
        super(ContactForm, self).__init__(*args, **kwargs)

        self.fields['league'] = forms.ChoiceField(choices=[(l.tag, l.name) for l in leagues])


class BulkEmailForm(forms.Form):
    subject = forms.CharField(max_length=140)
    html_content = forms.CharField(max_length=4096, required=True, widget=CKEditorUploadingWidget())
    text_content = forms.CharField(max_length=4096, required=True, widget=forms.Textarea)
    confirm_send = forms.BooleanField()

    def __init__(self, player_count, *args, **kwargs):
        super(BulkEmailForm, self).__init__(*args, **kwargs)

        self.fields['confirm_send'].label = 'Yes, I\'m sure - send emails to %d players' % (
            player_count)


class TeamSpamForm(forms.Form):
    text = forms.CharField(max_length=4096, required=True, widget=forms.Textarea)
    confirm_send = forms.BooleanField()

    def __init__(self, season, *args, **kwargs):
        super(TeamSpamForm, self).__init__(*args, **kwargs)

        self.fields['confirm_send'].label = 'Yes, I\'m sure - send spam to %d teams in %s' % (
            season.team_set.count(), season.name)


class TvFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        current_league = kwargs.pop('current_league')
        leagues = kwargs.pop('leagues')
        boards = kwargs.pop('boards')
        teams = kwargs.pop('teams')
        super(TvFilterForm, self).__init__(*args, **kwargs)

        self.fields['league'] = forms.ChoiceField(
            choices=[('all', 'All Leagues')] + [(l.tag, l.name) for l in leagues],
            initial=current_league.tag)
        if boards is not None and len(boards) > 0:
            self.fields['board'] = forms.ChoiceField(
                choices=[('all', 'All Boards')] + [(n, 'Board %d' % n) for n in boards])
        if teams is not None and len(teams) > 0:
            self.fields['team'] = forms.ChoiceField(
                choices=[('all', 'All Teams')] + [(team.number, team.name) for team in teams])


class TvTimezoneForm(forms.Form):
    timezone = forms.ChoiceField(choices=[('local', 'Local'), ('utc', 'UTC')])


class NotificationsForm(forms.Form):
    def __init__(self, league, player, *args, **kwargs):
        super(NotificationsForm, self).__init__(*args, **kwargs)
        for type_, _ in PLAYER_NOTIFICATION_TYPES:
            setting = PlayerNotificationSetting.get_or_default(player=player, league=league,
                                                               type=type_)
            self.fields[type_ + "_lichess"] = forms.BooleanField(required=False, label="Lichess",
                                                                 initial=setting.enable_lichess_mail)
            self.fields[type_ + "_slack"] = forms.BooleanField(required=False, label="Slack",
                                                               initial=setting.enable_slack_im)
            # users should not be able to switch off the pairing messages in slack, 
            # as they have to reply to those messages to be considered responsive
            is_round_started_type = type_ == 'round_started'
            self.fields[type_ + "_slack_wo"] = forms.BooleanField(required=False,
                                                                  label="Slack (with opponent)",
                                                                  initial=is_round_started_type or setting.enable_slack_mpim,
                                                                  disabled=is_round_started_type)
            # users cannot switch off lichess messages for started games, as the bulk api requires us to send those
            is_game_started_type = type_ == 'game_started'
            self.fields[type_ + "_lichess"] = forms.BooleanField(required=False,
                                                                 label="Lichess",
                                                                 initial=is_game_started_type,
                                                                 disabled=is_game_started_type)
            if type_ == 'before_game_time':
                offset_options = [(5, '5 minutes'), (10, '10 minutes'), (20, '20 minutes'),
                                  (30, '30 minutes'), (60, '1 hour'), (120, '2 hours')]
                self.fields[type_ + '_offset'] = forms.TypedChoiceField(choices=offset_options,
                                                                        initial=int(
                                                                            setting.offset.total_seconds() / 60),
                                                                        coerce=int)


class LoginForm(forms.Form):
    lichess_username = forms.CharField(max_length=255, required=False,
                                       validators=[username_validator])


class MoveLateRegForm(forms.Form):
    update_fields = forms.BooleanField(initial=True)
    prev_round = forms.IntegerField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('reg')
        super(MoveLateRegForm, self).__init__(*args, **kwargs)
        self.fields['prev_round'].initial = reg.round.number


class CreateTeamsForm(forms.Form):
    count = forms.IntegerField(min_value=1,
                               initial=20,
                               label="Count",
                               help_text='Number of iterations to run the algorithm looking '
                                         'for the "happiest" league')

    balance = forms.FloatField(min_value=0,
                               max_value=1,
                               initial=0.8,
                               label="Balance",
                               help_text="Ratio of team members to alternates.  A value of 0.8 "
                                         "means 20% will be made alternates")
    confirm_create = forms.BooleanField()

    def __init__(self, team_count, *args, **kwargs):
        super(CreateTeamsForm, self).__init__(*args, **kwargs)

        self.fields[
            'confirm_create'].label = f"Yes, I'm sure. Delete {team_count} teams and regenerate"
