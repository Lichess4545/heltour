"""Some places to store some stuff with GDPR for sanity
"""

import textwrap
from django.utils.html import mark_safe

SLACK_EMAIL_CONSENT_LABEL = 'I consent to sharing my email with Slack'
SLACK_EMAIL_CONSENT_HELP_TEXT = mark_safe(textwrap.dedent(
    '''We need your consent to share your email address with Slack Technologies,
    Inc. so that if your registration is approved, we can invite you to join the
    leagues' Slack workspace. You are free to revoke your consent at any time by
    contacting <a href="gdpr@lichess.org">gdpr@lichess.org</a>.
    For further details, please see the
    <a href="/team4545/document/privacy-policy/">Lichess4545 Privacy Policy.</a>'''
))

LICHESS_USERNAME_CONSENT_LABEL = textwrap.dedent(
    '''
    I consent to the use of my Lichess username for documenting league results.
    '''
)
LICHESS_USERNAME_CONSENT_HELP_TEXT = mark_safe(textwrap.dedent(
    '''We need your consent to publish your Lichess username on the Lichess4545
    website in order to document league results and statistics. Note
    that you are free to revoke your consent at any time by contacting
    <a href="gdpr@lichess.org">gdpr@lichess.org</a>.
    For further details, please see the
    <a href="/team4545/document/privacy-policy/">Lichess4545 Privacy Policy.</a>'''
))

AGREED_TO_RULES_LABEL = textwrap.dedent(
    '''
    Do you agree to comply with the %s league rules?
    '''
)

AGREED_TO_TOS_LABEL = textwrap.dedent(
    '''Do you agree to comply with the Lichess4545 Terms of Service?'''
)
AGREED_TO_TOS_HELP_TEXT = textwrap.dedent(
    '''<a href="/team4545/document/terms-of-service/">Lichess4545 Terms of Service.</a>'''
)

MISSING_CONSENT_MESSAGE = "We require this consent for you to participate in our leagues"
