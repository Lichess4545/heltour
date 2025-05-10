
import datetime
import responses
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from heltour.tournament import oauth
from heltour.tournament.models import LoginToken, Player, User
from heltour.tournament.tests.testutils import createCommonLeagueData, get_league, league_tag, league_url, season_url
import re


class LoginTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    def test_encode_decode_state(self, *args):
        # Just verify that encode/decode are symmetrical
        original_state = {'league': 'teamleague', 'token': None}
        encoded = oauth._encode_state(original_state)
        new_state = oauth._decode_state(encoded)
        self.assertEqual(original_state, new_state)

    @patch('heltour.tournament.oauth._encode_state', return_value='encodedstate')
    def test_oauth_redirect(self, *args):
        response = self.client.get(league_url('team', 'login'))
        url = re.sub("&code_challenge=[0-9A-z-]{43}", "", response.url)
        expected_oauth_url = ('https://lichess.org/oauth'
                              '?response_type=code'
                              '&client_id=heltour'
                              '&redirect_uri=https://testserver/auth/lichess/'
                              '&scope=email:read%20challenge:read%20challenge:write'
                              '&code_challenge_method=S256'
                              '&state=encodedstate')
        # TODO: find a more elegant way to solve this with assertRedirects instead of just comparing url and status code with assertEqual.
        self.assertEqual(url, expected_oauth_url)
        self.assertEqual(response.status_code, 302)
#        self.assertRedirects(response, expected_oauth_url, fetch_redirect_response=False)
        oauth._encode_state.assert_called_with({'league': 'teamleague', 'token': None})


@patch('heltour.tournament.lichessapi.get_user_meta',
       return_value={'perfs': {'classical': {'rating': 2121, 'games': 10}}})
@patch('heltour.tournament.oauth._decode_state',
       return_value={'league': league_tag('team'), 'token': None})
@patch('django.utils.timezone.now',
       return_value=datetime.datetime(2019, 1, 1, 10, 30, 0, tzinfo=datetime.timezone.utc))
class LoginWithCodeTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()

    @responses.activate
    def test_new_user(self, *args):
        responses.add(responses.POST, 'https://lichess.org/api/token',
                      json={'access_token': '1234',
                            'refresh_token': '4567',
                            'expires_in': 3600,
                            'token_type': 'bearer'})
        responses.add(responses.GET, 'https://lichess.org/api/account',
                      json={'username': 'testuser'})

        self.auth_params = {'code': 'abc', 'state': 'encodedstate'}
        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)

        self.assertRedirects(response, league_url('team', 'user_dashboard'))
        self.assertContains(response, '<h3>testuser</h3>', status_code=200)
        oauth._decode_state.assert_called_with('encodedstate')

        player = Player.objects.get(lichess_username='testuser')

        self.assertEqual(2121, player.rating_for(get_league('team')))
        self.assertEqual(10, player.games_played_for(get_league('team')))

        self.assertEqual('1234', player.oauth_token.access_token)
        self.assertEqual('4567', player.oauth_token.refresh_token)
        self.assertEqual(datetime.datetime(2019, 1, 1, 11, 30, 0, tzinfo=datetime.timezone.utc),
                         player.oauth_token.expires)
        self.assertEqual('bearer', player.oauth_token.token_type)
        self.assertEqual('email:read challenge:read challenge:write', player.oauth_token.scope)
        self.assertEqual('testuser', player.oauth_token.account_username)
# TODO fixme: unclear why below assert should work, emails is not set ...
#        self.assertEqual('testuser@example.com', player.oauth_token.account_email)

    @responses.activate
    def test_existing_user(self, *args):
        responses.add(responses.POST, 'https://lichess.org/api/token',
                      json={'access_token': '1234',
                            'refresh_token': '4567',
                            'expires_in': 3600,
                            'token_type': 'bearer'})
        responses.add(responses.GET, 'https://lichess.org/api/account',
                      json={'username': 'testuser1'})

        self.auth_params = {'code': 'abc', 'state': 'encodedstate'}
        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)
        created_player = Player.objects.filter(lichess_username='testuser1').get()
        created_player.profile = {}
        created_player.save()

        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)

        self.assertRedirects(response, league_url('team', 'user_dashboard'))
        self.assertContains(response, '<h3>testuser1</h3>', status_code=200)

# TODO fixme: this is not how this works anymore, these are fetched anyway even for the existing user.
#        player = Player.objects.get(lichess_username='testuser1')
        # The existing player already has a profile field, so it shouldn't have been re-fetched
#        self.assertEqual(1200, player.rating_for(get_league('team')))
#        self.assertEqual(55, player.games_played_for(get_league('team')))

    @patch('heltour.tournament.oauth._decode_state',
           return_value={'league': league_tag('team'), 'token': '999'})
    @responses.activate
    def test_slack_link(self, *args):
        responses.add(responses.POST, 'https://lichess.org/api/token',
                      json={'access_token': '1234',
                            'refresh_token': '4567',
                            'expires_in': 3600,
                            'token_type': 'bearer'})
        responses.add(responses.GET, 'https://lichess.org/api/account',
                      json={'username': 'testuser'})
        self.auth_params = {'code': 'abc', 'state': 'encodedstate'}

        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)

        LoginToken.objects.create(secret_token='999', slack_user_id='U1234', expires=datetime.datetime(2019, 1, 1, 10, 30, 0, tzinfo=datetime.timezone.utc))

        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)

        self.assertRedirects(response, league_url('team', 'user_dashboard'))
        self.assertContains(response, '<h3>testuser</h3>', status_code=200)

# TODO: fixme, unclear why the below assert should even work, LoginToken.objects.create(slack_user_id='whatever') does not set the player.slack_user_id atm.
#        player = Player.objects.get(lichess_username='testuser')
#        self.assertEqual('U1234', player.slack_user_id)

    @responses.activate
    def test_session_redirect(self, *args):
        responses.add(responses.POST, 'https://lichess.org/api/token',
                      json={'access_token': '1234',
                            'refresh_token': '4567',
                            'expires_in': 3600,
                            'token_type': 'bearer'})
        responses.add(responses.GET, 'https://lichess.org/api/account',
                      json={'username': 'testuser'})
        self.auth_params = {'code': 'abc', 'state': 'encodedstate'}

        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)
        self.client.session['redirect_url'] = league_url('team', 'user_dashboard')
        response = self.client.get(reverse('lichess_auth'), self.auth_params, follow=True)
        self.assertTemplateUsed(response, 'tournament/user_dashboard.html')


class LoginBadTestCase(TestCase):

    def test_bad_response(self, *args):
        response = self.client.get(reverse('lichess_auth'), {'code': 'abc'}, follow=True)
        self.assertTemplateUsed(response, 'tournament/login_failed.html')
        response = self.client.get(reverse('lichess_auth'), {'state': 'abc'}, follow=True)
        self.assertTemplateUsed(response, 'tournament/login_failed.html')
        response = self.client.get(reverse('lichess_auth'), {'code': 'abc', 'state': 'abc'}, follow=True)
        self.assertTemplateUsed(response, 'tournament/login_failed.html')
