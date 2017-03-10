from django import forms
from django.utils.translation import ugettext_lazy as _
from captcha.fields import ReCaptchaField
from ckeditor_uploader.widgets import CKEditorUploadingWidget

from .models import *
from django.core.exceptions import ValidationError
from heltour import settings
import captcha
from django.core.urlresolvers import reverse
from heltour.tournament.workflows import ApproveRegistrationWorkflow

YES_NO_OPTIONS = (
    (True, 'Yes',),
    (False, 'No',),
)

class RegistrationForm(forms.ModelForm):
    captcha = ReCaptchaField()
    class Meta:
        model = Registration
        fields = (
            'lichess_username', 'slack_username', 'email', 'classical_rating',
            'peak_classical_rating', 'has_played_20_games', 'already_in_slack_group',
            'previous_season_alternate', 'can_commit', 'friends', 'agreed_to_rules',
            'alternate_preference', 'weeks_unavailable',
        )
        labels = {
            'lichess_username': _(u'Your Lichess Username'),
            'slack_username': _(u'Your Slack Username'),
            'email': _(u'Your Email'),
        }
        help_texts = {
            'slack_username': _(u"Please, it should be the same. If you aren't on our Slack yet, please fill in N/A."),
        }

    def __init__(self, *args, **kwargs):
        self.season = kwargs.pop('season')
        league = self.season.league
        super(RegistrationForm, self).__init__(*args, **kwargs)

        # Rating fields
        rating_type = league.get_rating_type_display()
        self.fields['classical_rating'] = forms.IntegerField(required=True, label=_(u'Your Lichess %s Rating' % rating_type))
        self.fields['peak_classical_rating'] = forms.IntegerField(required=True, label=_(u'Your Highest Peak Lichess %s Rating' % rating_type))

        # 20 games
        self.fields['has_played_20_games'] = forms.TypedChoiceField(required=True, choices=YES_NO_OPTIONS, widget=forms.RadioSelect, coerce=lambda x: x == 'True',
                                                                    label=_(u'Have you played more than 20 rated games of %s chess on Lichess?' % rating_type.lower()),
                                                                    help_text=_(u'If no, this must be fulfilled ASAP.'),)

        # In slack
        self.fields['already_in_slack_group'] = forms.TypedChoiceField(required=True, label=_(u'Are you on our Slack group?'), choices=YES_NO_OPTIONS,
                                                                       widget=forms.RadioSelect, coerce=lambda x: x == 'True')

        # Previous season status
        if league.competitor_type == 'team':
            self.fields['previous_season_alternate'] = forms.ChoiceField(required=True, choices=PREVIOUS_SEASON_ALTERNATE_OPTIONS, widget=forms.RadioSelect,
                                                                         label=_(u'Were you an alternate for the previous season?'))
        else:
            del self.fields['previous_season_alternate']

        # Can commit
        time_control = league.time_control
        if league.rating_type == 'classical':
            self.fields['can_commit'] = forms.TypedChoiceField(required=True, choices=YES_NO_OPTIONS, widget=forms.RadioSelect, coerce=lambda x: x == 'True',
                   label=_(u'Are you able to commit to 1 long time control game (%s currently) of classical chess on Lichess.org per week?' % time_control))
        else:
            start_time = '' if self.season.start_date is None else \
                         ' on %s at %s UTC' % (self.season.start_date.strftime('%b %-d'), self.season.start_date.strftime('%H:%M'))
            self.fields['can_commit'] = forms.TypedChoiceField(required=True, choices=YES_NO_OPTIONS, widget=forms.RadioSelect, coerce=lambda x: x == 'True',
                   label=_(u'Are you able to commit to playing %d rounds of %s blitz games back to back%s?'
                           % (self.season.rounds, time_control, start_time)))
        # Friends
        if league.competitor_type == 'team':
            self.fields['friends'] = forms.CharField(required=False, label=_(u'Are there any friends you would like to be paired with?'),
                                                     help_text=_(u'Note: All players must register. All players must join Slack. All players should also request each other.'))
        else:
            del self.fields['friends']

        # Agree to rules
        rules_doc = LeagueDocument.objects.filter(league=league, type='rules').first()
        if rules_doc is not None:
            doc_url = reverse('by_league:document', args=[league.tag, rules_doc.tag])
            rules_help_text = _(u'<a target="_blank" href="%s">Rules Document</a>' % doc_url)
        else:
            rules_help_text = ''
        league_name = league.name
        if not league_name.endswith('League'):
            league_name += ' League'

        self.fields['agreed_to_rules'] = forms.TypedChoiceField(required=True, label=_(u'Do you agree to the rules of the %s?' % league_name),
                                                                help_text=rules_help_text,
                                                                choices=YES_NO_OPTIONS, widget=forms.RadioSelect, coerce=lambda x: x == 'True')

        # Alternate preference
        if league.competitor_type == 'team':
            self.fields['alternate_preference'] = forms.ChoiceField(required=True, choices=ALTERNATE_PREFERENCE_OPTIONS, widget=forms.RadioSelect,
                                                                    label=_(u'Are you interested in being an alternate or a full time player?'),
                                                                    help_text=_(u'If you register late, you may start as an alternate anyway.'))
        else:
            del self.fields['alternate_preference']

        # Weeks unavailable
        if self.season.round_duration == timedelta(days=7):
            weeks = [(r.number, 'Week %s (%s - %s)' %
                                (r.number, r.start_date.strftime('%b %-d') if r.start_date is not None else '?', r.end_date.strftime('%b %-d') if r.end_date is not None else '?'))
                     for r in self.season.round_set.order_by('number')]
            self.fields['weeks_unavailable'] = forms.MultipleChoiceField(required=False, label=_(u'Are there any weeks you would NOT be able to play?'),
                                                                         choices=weeks, widget=forms.CheckboxSelectMultiple)
        else:
            del self.fields['weeks_unavailable']

        # Captcha
        if settings.DEBUG:
            del self.fields['captcha']

    def save(self, commit=True, *args, **kwargs):
        registration = super(RegistrationForm, self).save(commit=False, *args, **kwargs)
        registration.season = self.season
        registration.status = 'pending'
        if commit:
            registration.save()
        return registration

    def clean_weeks_unavailable(self):
        upcoming_rounds = [r for r in self.season.round_set.order_by('number') if r.start_date > timezone.now()]
        upcoming_rounds_available = [r for r in upcoming_rounds if str(r.number) not in self.cleaned_data['weeks_unavailable']]
        upcoming_rounds_unavailable = [r for r in upcoming_rounds if str(r.number) in self.cleaned_data['weeks_unavailable']]
        if len(upcoming_rounds_available) == 0 and len(upcoming_rounds_unavailable) > 0:
            raise ValidationError('You can\'t mark yourself as unavailable for all upcoming rounds.')
        return ','.join(self.cleaned_data['weeks_unavailable'])


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

        if workflow.is_late:
            self.fields['retroactive_byes'] = forms.IntegerField(initial=workflow.default_byes)
            self.fields['late_join_points'] = forms.FloatField(initial=workflow.default_ljp)

class RejectRegistrationForm(forms.Form):

    def __init__(self, *args, **kwargs):
        _ = kwargs.pop('registration')
        super(RejectRegistrationForm, self).__init__(*args, **kwargs)

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
    rating_type = forms.ChoiceField(choices=[('actual', 'Actual Ratings'), ('expected', 'Expected Ratings')])

class RoundTransitionForm(forms.Form):
    def __init__(self, is_team_league, round_to_close, round_to_open, season_to_close, *args, **kwargs):
        super(RoundTransitionForm, self).__init__(*args, **kwargs)

        if round_to_close is not None:
            self.fields['complete_round'] = forms.BooleanField(initial=True, required=False, label='Set round %d as completed' % round_to_close.number)
            self.fields['round_to_close'] = forms.IntegerField(initial=round_to_close.number, widget=forms.HiddenInput)

        if season_to_close is not None:
            self.fields['complete_season'] = forms.BooleanField(initial=True, required=False, label='Set %s as completed' % season_to_close.name)

        if round_to_open is not None:
            if is_team_league:
                self.fields['update_board_order'] = forms.BooleanField(initial=True, required=False, label='Update board order')
            self.fields['generate_pairings'] = forms.BooleanField(initial=True, required=False, label='Generate pairings for round %d' % round_to_open.number)
            self.fields['round_to_open'] = forms.IntegerField(initial=round_to_open.number, widget=forms.HiddenInput)

class NominateForm(forms.Form):
    game_link = forms.URLField(required=False)

    def clean_game_link(self):
        game_link, ok = normalize_gamelink(self.cleaned_data['game_link'])
        if not ok:
            raise ValidationError('Invalid game link.', code='invalid')
        return game_link

class ContactForm(forms.Form):
    league = forms.ChoiceField(choices=[])
    your_lichess_username = forms.CharField(max_length=255, required=False)
    your_email_address = forms.EmailField(max_length=255)
    subject = forms.CharField(max_length=140)
    message = forms.CharField(max_length=1024, widget=forms.Textarea)
    captcha = ReCaptchaField()

    def __init__(self, *args, **kwargs):
        leagues = kwargs.pop('leagues')
        super(ContactForm, self).__init__(*args, **kwargs)

        self.fields['league'] = forms.ChoiceField(choices=[(l.tag, l.name) for l in leagues])

        if settings.DEBUG:
            del self.fields['captcha']

class BulkEmailForm(forms.Form):
    subject = forms.CharField(max_length=140)
    html_content = forms.CharField(max_length=4096, required=True, widget=CKEditorUploadingWidget())
    text_content = forms.CharField(max_length=4096, required=True, widget=forms.Textarea)
    confirm_send = forms.BooleanField()

    def __init__(self, season, *args, **kwargs):
        super(BulkEmailForm, self).__init__(*args, **kwargs)

        self.fields['confirm_send'].label = 'Yes, I\'m sure - send emails to %d players in %s' % (season.seasonplayer_set.count(), season.name)

class TvFilterForm(forms.Form):
    def __init__(self, *args, **kwargs):
        current_league = kwargs.pop('current_league')
        leagues = kwargs.pop('leagues')
        boards = kwargs.pop('boards')
        teams = kwargs.pop('teams')
        super(TvFilterForm, self).__init__(*args, **kwargs)

        self.fields['league'] = forms.ChoiceField(choices=[('all', 'All Leagues')] + [(l.tag, l.name) for l in leagues], initial=current_league.tag)
        if boards is not None and boards > 0:
            self.fields['board'] = forms.ChoiceField(choices=[('all', 'All Boards')] + [(n, 'Board %d' % n) for n in boards])
        if teams is not None and boards > 0:
            self.fields['team'] = forms.ChoiceField(choices=[('all', 'All Teams')] + [(team.number, team.name) for team in teams])

class TvTimezoneForm(forms.Form):
    timezone = forms.ChoiceField(choices=[('local', 'Local'), ('utc', 'UTC')])

class NotificationsForm(forms.Form):
    def __init__(self, league, player, *args, **kwargs):
        super(NotificationsForm, self).__init__(*args, **kwargs)
        for type_, _ in PLAYER_NOTIFICATION_TYPES:
            setting = PlayerNotificationSetting.get_or_default(player=player, league=league, type=type_)
            self.fields[type_ + "_lichess"] = forms.BooleanField(required=False, label="Lichess", initial=setting.enable_lichess_mail)
            self.fields[type_ + "_slack"] = forms.BooleanField(required=False, label="Slack", initial=setting.enable_slack_im)
            self.fields[type_ + "_slack_wo"] = forms.BooleanField(required=False, label="Slack (with opponent)", initial=setting.enable_slack_mpim)
            if type_ == 'before_game_time':
                offset_options = [(5, '5 minutes'), (10, '10 minutes'), (20, '20 minutes'), (30, '30 minutes'), (60, '1 hour'), (120, '2 hours')]
                self.fields[type_ + '_offset'] = forms.TypedChoiceField(choices=offset_options, initial=int(setting.offset.total_seconds()) / 60, coerce=int)
