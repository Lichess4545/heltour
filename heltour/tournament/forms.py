from django import forms
from django.utils.translation import ugettext_lazy as _

from .models import (
    Registration,
    PREVIOUS_SEASON_ALTERNATE_OPTIONS,
    ALTERNATE_PREFERENCE_OPTIONS,
)

YES_NO_OPTIONS = (
    (True, 'Yes',),
    (False, 'No',),
)

class RegistrationForm(forms.ModelForm):
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
            'classical_rating': _(u'Your Lichess Classical Rating'),
            'peak_classical_rating': _(u'Your Highest Peak Lichess Classical Rating'),
            'alternate_preference': _(u'Are you interested in being an alternate or a full time player?'),
            'previous_season_alternate': _(u'Were you an alternate for the previous season?'),
            'friends': _(u'Are there any friends you would like to be paired with?'),
        }
        help_texts = {
            'slack_username': _(u"Please, it should be the same. If you aren't on our Slack yet, please fill in N/A."),
            'friends': _(u'Note: All players must register. All players must join Slack. All players should also request each other.'),
        }
        widgets = {
            'has_played_20_games': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'already_in_slack_group': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'previous_season_alternate': forms.RadioSelect(),
            'can_commit': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'agreed_to_rules': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'alternate_preference': forms.RadioSelect(),
        }

    def __init__(self, *args, **kwargs):
        self.season = kwargs.pop('season')
        super(RegistrationForm, self).__init__(*args, **kwargs)

        weeks = [(i, 'Week %s' % i) for i in range(1, self.season.rounds + 1)]
        self.fields['weeks_unavailable'] = forms.MultipleChoiceField(required=False, label=_(u'Are there any weeks you would be unable to play?'),
                                                                     choices=weeks, widget=forms.CheckboxSelectMultiple)
        self.fields['has_played_20_games'] = forms.TypedChoiceField(required=True, label=_(u'Have you played more than 20 games of classical chess on Lichess?'),
                                                                    help_text=_(u'If no, this must be fulfilled ASAP.'), choices=YES_NO_OPTIONS,
                                                                    widget=forms.RadioSelect, coerce=lambda x: x == 'True')
        self.fields['already_in_slack_group'] = forms.TypedChoiceField(required=True, label=_(u'Are you on our Slack group?'), choices=YES_NO_OPTIONS,
                                                                       widget=forms.RadioSelect, coerce=lambda x: x == 'True')
        self.fields['previous_season_alternate'].choices = PREVIOUS_SEASON_ALTERNATE_OPTIONS
        self.fields['can_commit'] = forms.TypedChoiceField(required=True, label=_(u'Are you able to commit to 1 long time control game (45|45 currently) of classical chess on Lichess.org per week?'),
                                                           choices=YES_NO_OPTIONS, widget=forms.RadioSelect, coerce=lambda x: x == 'True')
        # TODO: This rules link should be specified in the league object.
        self.fields['agreed_to_rules'] = forms.TypedChoiceField(required=True, label=_(u'Do you agree to the rules of the 45|45 League?'),
                                                                help_text=_(u'<a target="_blank" href="https://docs.google.com/document/d/1nRzexE_dNmqc-XiE48JxkVeW3oZjAPqUAmYltVPEbrU/edit">Rules Document</a>'),
                                                                choices=YES_NO_OPTIONS, widget=forms.RadioSelect, coerce=lambda x: x == 'True')
        self.fields['alternate_preference'].choices = ALTERNATE_PREFERENCE_OPTIONS
        
        if self.season.league.competitor_type != 'team':
            # Modifications for lonewolf
            del self.fields['alternate_preference']
            del self.fields['previous_season_alternate']
            del self.fields['friends']
            self.fields['can_commit'].label = _(u'Are you able to commit to 1 long time control game (30|30 currently) of classical chess on Lichess.org per week?')
            self.fields['agreed_to_rules'].label = _(u'Do you agree to the rules of the LoneWolf League?')
            self.fields['agreed_to_rules'].help_text = _(u'<a target="_blank" href="https://docs.google.com/document/d/105gEd79MdUVIt4pW_T_BsX-TvSyNB1lvNJ9p73k9gFo/edit">Rules Document</a>')

    def save(self, commit=True, *args, **kwargs):
        registration = super(RegistrationForm, self).save(commit=False, *args, **kwargs)
        registration.season = self.season
        registration.status = 'pending'
        if commit:
            registration.save()
        return registration

    def clean_weeks_unavailable(self):
        return ','.join(self.cleaned_data['weeks_unavailable'])


class ReviewRegistrationForm(forms.Form):
    pass

class ApproveRegistrationForm(forms.Form):
    invite_to_slack = forms.BooleanField(required=False)
    send_confirm_email = forms.BooleanField(required=False, initial=True)

    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('registration')
        super(ApproveRegistrationForm, self).__init__(*args, **kwargs)

        self.fields['invite_to_slack'].initial = not reg.already_in_slack_group
        
        if reg.season.league.competitor_type != 'team' and reg.season.round_set.filter(publish_pairings=True).count() > 0:
            self.fields['retroactive_byes'] = forms.IntegerField(initial=0)
            self.fields['late_join_points'] = forms.FloatField(initial=0)

class RejectRegistrationForm(forms.Form):

    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('registration')
        super(RejectRegistrationForm, self).__init__(*args, **kwargs)

class ImportSeasonForm(forms.Form):
    spreadsheet_url = forms.CharField(label='Spreadsheet URL', max_length=1023)
    season_name = forms.CharField(label='Season name', max_length=255)
    season_tag = forms.SlugField(label='Season tag')
    rosters_only = forms.BooleanField(required=False, label='Rosters only')
    exclude_live_pairings = forms.BooleanField(required=False, label='Exclude live pairings')

class GeneratePairingsForm(forms.Form):
    overwrite_existing = forms.BooleanField(required=False, label='Overwrite existing pairings')

class ReviewPairingsForm(forms.Form):
    pass

class EditRostersForm(forms.Form):
    changes = forms.CharField(widget=forms.HiddenInput)

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
