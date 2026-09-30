"""Some places to store some stuff with GDPR for sanity
"""

import textwrap
from django.utils.html import mark_safe
from heltour.tournament.chatbackend import chatbackend, chatbackend_render


AGREED_TO_RULES_LABEL = textwrap.dedent(
    '''
    Do you agree to comply with the %s rules?
    '''
)

AGREED_TO_TOS_LABEL = textwrap.dedent(
    '''Do you agree to comply with the Lichess4545 Terms of Service?'''
)
if chatbackend_render():
    AGREED_TO_TOS_HELP_TEXT = mark_safe(
        textwrap.dedent(
            f'''
            By selecting Yes, you understand and agree that we will share your email
            address with {chatbackend()} in line with our
            <a href="/team4545/document/privacy-policy/">Privacy Policy</a>
            (and justified in our
            <a href="/team4545/document/terms-of-service/">Terms of Service</a>)
             '''
        )
    )
else:
    AGREED_TO_TOS_HELP_TEXT = mark_safe(
        textwrap.dedent(
            '''
            See our <a href="/team4545/document/privacy-policy/">Privacy Policy</a>
            and <a href="/team4545/document/terms-of-service/">Terms of Service</a>.
            '''
        )
    )

MISSING_CONSENT_MESSAGE = "We require this consent for you to participate in our leagues"
