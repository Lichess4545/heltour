from django.contrib.auth import login
from django.http.response import HttpResponse
from django.shortcuts import redirect, reverse
from heltour.tournament.models import *
import requests
import reversion

SCOPES = [
    'email:read',
    'challenge:read',
    'challenge:write'
]


def get_redirect_uri(request):
    return request.build_absolute_uri(reverse('lichess_auth'))


def redirect_for_authorization(request, league_tag):
    # Redirect to lichess's OAuth2 consent screen
    # We don't care if anyone else initiates a request, so we can use the state variable to store
    # the league tag so we can redirect properly
    auth = f'{settings.LICHESS_OAUTH_AUTHORIZE_URL}' + \
           f'?response_type=code' + \
           f'&client_id={settings.LICHESS_OAUTH_CLIENTID}' + \
           f'&redirect_uri={get_redirect_uri(request)}' + \
           f'&scope={" ".join(SCOPES)}' + \
           f'&state={league_tag}'
    return redirect(auth)


def get_auth_headers(access_token):
    return {'Authorization': f'Bearer {access_token}'}


def login_with_code(request, code, state):
    # Get the OAuth2 token given the provided code
    token_response = requests.post(settings.LICHESS_OAUTH_TOKEN_URL, {
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': get_redirect_uri(request),
        'client_id': settings.LICHESS_OAUTH_CLIENTID,
        'client_secret': settings.LICHESS_OAUTH_CLIENTSECRET
    })
    if token_response.status_code != 200:
        return HttpResponse(f'Received {token_response.status_code} from token endpoint', 401)
    access_token = token_response.json()['access_token']

    # Read the user account information to get their username
    # TODO: Maybe we can update their Player.profile?
    # TODO: Eventually we should persist oauth tokens for creating challenges etc.
    # TODO: Fetch and store their verified email for slack account linking
    account_response = requests.get(settings.LICHESS_OAUTH_ACCOUNT_URL, headers=get_auth_headers(access_token))
    if account_response.status_code != 200:
        return HttpResponse(f'Received {account_response.status_code} from account endpoint', 401)
    lichess_username = account_response.json()['id']

    user = User.objects.filter(username__iexact=lichess_username).first()
    if not user:
        # Create the user with a password no one will ever use; it can always be manually reset if needed
        with reversion.create_revision():
            reversion.set_comment('Create user from lichess OAuth2 login')
            user = User.objects.create_user(username=lichess_username, password=create_api_token())
    user.backend = 'django.contrib.auth.backends.ModelBackend'
    login(request, user)

    league_tag = state
    return redirect('by_league:user_dashboard', league_tag)
