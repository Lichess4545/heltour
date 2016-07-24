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
            'peak_classical_rating', 'has_played_20_games',
            'already_in_slack_group', 'can_commit', 'friends', 'agreed_to_rules',
            'alternate_preference', 'weeks_unavailable',
        )
        labels = {
            'lichess_username': _(u'Your Lichess Username'),
            'slack_username': _(u'Your Slack Username'),
            'email': _(u'Your email'),
            'classical_rating': _(u'Your Lichess Classical Rating'),
            'peak_classical_rating': _(u'Your highest peak Lichess Classical Rating'),
            'has_played_20_games': _(u'Have you played more than 20 games of classical chess on Lichess?'),
            'already_in_slack_group': _(u'Are you on our Slack group?'),
            'can_commit': _(u'Are you able to commit to 1 Long Time Control Game (45|45 currently) of Classical Chess on Lichess.org per week?'),
            'agreed_to_rules': _(u'Do you agree to the rules of the 45|45 League?'),
            'alternate_preference': _(u'Are you interested in being an alternate or a full time player?'),
            'previous_season_alternate': _(u'Were you an alternate for the previous season?'),
            'friends': _(u'Are there any friends you would like to be paired with?'),
        }
        help_texts = {
            'slack_username': _(u"Please, it should be the same. If you aren't. on our Slack yet, please fill in N/A."),
            'friends': _(u'Note: All players must register. All players must join Slack. All players should also request each other?'),
            'has_played_20_games': _(u'If no, this must be fulfilled ASAP.'),
            # TODO: This rules link should be specified in the league object.
            'agreed_to_rules': _(u'<a target="_blank" href="https://docs.google.com/document/d/1nRzexE_dNmqc-XiE48JxkVeW3oZjAPqUAmYltVPEbrU/edit">Rules Document</a>'),
        }
        widgets = {
            'has_played_20_games': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'already_in_slack_group': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'can_commit': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'agreed_to_rules': forms.RadioSelect(choices=YES_NO_OPTIONS),
            'alternate_preference': forms.RadioSelect(choices=ALTERNATE_PREFERENCE_OPTIONS),
        }

    def __init__(self, *args, **kwargs):
        self.season = kwargs.pop('season')
        super(RegistrationForm, self).__init__(*args, **kwargs)

        weeks = [(i, 'Week %s' % i) for i in range(1, self.season.rounds + 1)]
        self.fields['weeks_unavailable'] = forms.MultipleChoiceField(required=False, label='Are there any weeks you would be unable to play?', choices=weeks, widget=forms.CheckboxSelectMultiple)
        self.fields['has_played_20_games'].required = True
        self.fields['already_in_slack_group'].required = True
        self.fields['can_commit'].required = True
        self.fields['agreed_to_rules'].required = True

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
    moderator_notes = forms.CharField(required=False, max_length=4095, widget=forms.Textarea(attrs={'class':'notes'}))
    
    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('registration')
        super(ReviewRegistrationForm, self).__init__(*args, **kwargs)
        
        self.fields['moderator_notes'].initial = reg.moderator_notes

class ApproveRegistrationForm(forms.Form):
    invite_to_slack = forms.BooleanField(required=False)
    send_confirm_email = forms.BooleanField(required=False, initial=True)
    
    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('registration')
        super(ApproveRegistrationForm, self).__init__(*args, **kwargs)
        
        self.fields['invite_to_slack'].initial = not reg.already_in_slack_group

class RejectRegistrationForm(forms.Form):
    
    def __init__(self, *args, **kwargs):
        reg = kwargs.pop('registration')
        super(RejectRegistrationForm, self).__init__(*args, **kwargs)
        
class ImportSeasonForm(forms.Form):
    spreadsheet_url = forms.CharField(label='Spreadsheet URL', max_length=1023)
    season_name = forms.CharField(label='Season name', max_length=255)
    rosters_only = forms.BooleanField(required=False, label='Rosters only')
    exclude_live_pairings = forms.BooleanField(required=False, label='Exclude live pairings')
    
    def __init__(self, *args, **kwargs):
        super(ImportSeasonForm, self).__init__(*args, **kwargs)
