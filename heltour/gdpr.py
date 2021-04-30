"""Some places to store some stuff with GDPR for sanity
"""

import textwrap
from django.utils.html import mark_safe


AGREED_TO_RULES_LABEL = textwrap.dedent(
    '''
    Do you agree to comply with the %s rules?
    '''
)

AGREED_TO_TOS_LABEL = textwrap.dedent(
    '''Do you agree to comply with the Lichess4545 Terms of Service?'''
)
AGREED_TO_TOS_HELP_TEXT = mark_safe(textwrap.dedent(
    '''
    By selecting Yes, you understand and agree that we will share your email
    address with Slack in line with our
    <a href="/team4545/document/privacy-policy/">Privacy Policy</a>
    (and justified in our
    <a href="/team4545/document/terms-of-service/">Terms of Service</a>)
     '''
))

MISSING_CONSENT_MESSAGE = "We require this consent for you to participate in our leagues"
