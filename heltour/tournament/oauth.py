import base64
import hashlib
from datetime import timedelta
from unicodedata import normalize

import requests
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core import signing
from django.http.response import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string

from heltour import settings
from heltour.tournament import lichessapi
from heltour.tournament.models import (
    LoginToken,
    OauthToken,
    Player,
    create_api_token,
    logger,
)

_SCOPES = [
    'email:read',
    'challenge:read',
    'challenge:write'
]


def redirect_for_authorization(request, league_tag, secret_token):
    # Redirect to lichess's OAuth2 consent screen
    # We don't care if anyone else initiates a request, so we can use the state variable to store
    # the league tag so we can redirect properly
    state = {
        'league': league_tag,
        'token': secret_token
    }
    request.session['oauth_code_verifier'] = get_random_string(64)
    auth = f'{settings.LICHESS_OAUTH_AUTHORIZE_URL}' + \
           '?response_type=code' + \
           f'&client_id={settings.LICHESS_OAUTH_CLIENTID}' + \
           f'&redirect_uri={_get_redirect_uri(request)}' + \
           f'&scope={" ".join(_SCOPES)}' + \
           '&code_challenge_method=S256' + \
           f'&code_challenge={_code_challenge(request.session["oauth_code_verifier"])}' + \
           f'&state={_encode_state(state)}'
    return redirect(auth)


def login_with_code(request, code, encoded_state):
    if not code or not encoded_state:
        logger.error('Missing code/state')
        return redirect('login_failed')

    try:
        state = _decode_state(encoded_state)
    except signing.BadSignature:
        logger.error('Bad state encoding')
        return redirect('login_failed')

    status, oauth_token = _get_oauth_token(request, code)
    if status:
        return HttpResponse(f'Received {status} from token endpoint', 401)
    username = _get_account_username(oauth_token)
    oauth_token.account_username = username
    # TODO: This slows down login. Figure out what to do with this.
    # oauth_token.account_email = _get_account_email(oauth_token)
    player = Player.get_or_create(username)

    # At this point all http requests are successful, so we can start persisting everything
    oauth_token.save()
    player.oauth_token = oauth_token
    player.save()

    # We are using get_or_create here instead of django's create_user
    # to minimize the occurrence of race conditions
    user, _ = User.objects.get_or_create(username__iexact=_normalize_username(username),
                                         defaults={"password": _unusable_password(),
                                                   "username": _normalize_username(username),
                                                   })
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    # Ensure the player's profile is present so we can display ratings, etc.
    _ensure_profile_present(player)

    # Slack linking?
    if state['token']:
        token = LoginToken.objects.filter(secret_token=state['token']).first()
        if token and not token.is_expired() and token.slack_user_id:
            Player.link_slack_account(username, token.slack_user_id)
            request.session['slack_linked'] = True

    # Success. Now redirect
    redir_url = request.session.get('login_redirect')
    if redir_url:
        request.session['login_redirect'] = None
        return redirect(redir_url)
    else:
        return redirect('by_league:user_dashboard', state['league'])


def _normalize_username(username: str) -> str:
    # normalize('NFKC', username) reproduces what the django method create_user() would do
    return normalize('NFKC', username)


def _unusable_password() -> str:
    # a password starting with ! signifies an unusable password to django, at least for versions 4.2 - 5.2
    # additionally, those unusable passwords are by default of length 40,
    # however django only checks that they start with !, and will then return False for User.has_usable_password()
    return f"!{create_api_token(length=40)}"


def _ensure_profile_present(player):
    if not player.profile:
        user_meta = lichessapi.get_user_meta(player.lichess_username, priority=100)
        player.update_profile(user_meta)


def _get_account_username(oauth_token):
    response = requests.get(settings.LICHESS_OAUTH_ACCOUNT_URL,
                            headers=_get_auth_headers(oauth_token.access_token))
    if response.status_code != 200:
        return HttpResponse(f'Received {response.status_code} from account endpoint', 401)
    return response.json()['username']


def _get_account_email(oauth_token):
    response = requests.get(settings.LICHESS_OAUTH_EMAIL_URL,
                            headers=_get_auth_headers(oauth_token.access_token))
    if response.status_code != 200:
        return HttpResponse(f'Received {response.status_code} from email endpoint', 401)
    return response.json()['email']


def _get_oauth_token(request, code):
    token_response = requests.post(settings.LICHESS_OAUTH_TOKEN_URL, {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': _get_redirect_uri(request),
        'client_id': settings.LICHESS_OAUTH_CLIENTID,
        'code_verifier': request.session.get('oauth_code_verifier'),
    })
    if token_response.status_code != 200:
        logger.error(f'Received {token_response.status_code} from token endpoint: {token_response.text}')
        return token_response.status_code, None
    token_json = token_response.json()
    return None, OauthToken(access_token=token_json['access_token'],
                      token_type=token_json['token_type'],
                      expires=timezone.now() + timedelta(
                          seconds=token_json.get('expires_in', 5270400)),
                      refresh_token=token_json.get('refresh_token', ''),
                      scope=token_json.get('scope', ' '.join(_SCOPES)))


def _code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def _get_redirect_uri(request):
    http_url =  request.build_absolute_uri(reverse('lichess_auth'))
    return http_url.replace('http://', settings.LICHESS_OAUTH_REDIRECT_SCHEME)


def _encode_state(state):
    # This state isn't actually security critical, but it's just good practice to sign
    return signing.dumps(state)


def _decode_state(state):
    return signing.loads(state)


def _get_auth_headers(access_token):
    return {'Authorization': f'Bearer {access_token}'}
