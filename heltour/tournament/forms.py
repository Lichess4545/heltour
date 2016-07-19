from django import forms

class RegistrationForm(forms.Form):
    lichess_username = forms.CharField(label='Your Lichess Username', max_length=255)