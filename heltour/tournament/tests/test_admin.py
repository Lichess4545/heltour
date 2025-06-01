from unittest.mock import patch
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib import admin
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.http.response import HttpResponseForbidden
from heltour.tournament.models import (Alternate, LonePlayerPairing, Player,
    Round, Season, SeasonPlayer, Team, TeamPairing)
from heltour.tournament.tests.testutils import (createCommonLeagueData,
    get_season, get_player, get_round)


class AdminSearchTestCase(TestCase):
    def test_all_search_fields(self):
        superuser = User(
            username='superuser',
            password='Password',
            is_superuser=True,
            is_staff=True,
        )
        superuser.save()
        self.client.force_login(user=superuser)
        for model_class, admin_class in admin.site._registry.items():
            with self.subTest(model_class._meta.model_name):
                path = reverse(f'admin:{model_class._meta.app_label}_{model_class._meta.model_name}_changelist')
                response = self.client.get(path + "?q=whatever")
                self.assertEqual(response.status_code, 200)


class ManagePlayerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.season = get_season('team')
        cls.season.start_date = timezone.now()
        cls.season.save()
        cls.superuser = User.objects.create(username='superuser', password='Password', is_superuser=True, is_staff=True)
        cls.p = get_player('Player1')
        cls.sp = SeasonPlayer.objects.create(player=cls.p, season=cls.season)

    def test_add_alternate(self):
        self.client.force_login(user=self.superuser)
        response = self.client.post(f'/admin/tournament/season/{self.season.pk}/manage_players/',
                                    data={"changes": '[{"action": "create-alternate", "board_number": 1, "player_name": "Player1"}]'})
        self.assertEqual(Alternate.objects.all().count(), 1)
        self.assertEqual(Alternate.objects.all().first().season_player.player.lichess_username, 'Player1')


class SeasonAdminTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.superuser = User.objects.create(username='superuser', password='password', is_superuser=True, is_staff=True)
        t1 = Team.objects.get(number=1)
        t2 = Team.objects.get(number=2)
        r1 = get_round("team", 1)
        tp = TeamPairing.objects.create(white_team=t1, black_team=t2, round=r1, pairing_order=1)

    @patch('heltour.tournament.simulation.simulate_season')
    @patch('django.contrib.admin.ModelAdmin.message_user')
    def test_simulate(self, message, simulate):
        self.client.force_login(user=self.superuser)
        path = reverse('admin:tournament_season_changelist')
        response = self.client.post(path, data={'action': 'simulate_tournament', '_selected_action': get_season('lone').pk}, follow=True)
        self.assertTrue(simulate.called)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], 'Simulation complete.')

    @patch('heltour.tournament.models.Season.calculate_scores')
    @patch('heltour.tournament.models.TeamPairing.refresh_points')
    @patch('heltour.tournament.models.TeamPairing.save')
    @patch('django.contrib.admin.ModelAdmin.message_user')
    def test_recalculate(self, message, tpsave, tprefresh, scalculate):
        self.client.force_login(user=self.superuser)
        path = reverse('admin:tournament_season_changelist')
        response = self.client.post(path, data={'action': 'recalculate_scores',
                                                '_selected_action': get_season('lone').pk},
                                    follow=True)
        self.assertFalse(tprefresh.called)
        self.assertFalse(tpsave.called)
        self.assertTrue(scalculate.called)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], 'Scores recalculated.')
        message.reset_mock()
        scalculate.reset_mock()
        response = self.client.post(path,
                                    data={'action': 'recalculate_scores',
                                          '_selected_action': Season.objects.all().values_list('pk', flat=True)},
                                    follow=True)
        self.assertTrue(tprefresh.called)
        self.assertTrue(tpsave.called)
        self.assertTrue(scalculate.called)
        self.assertEqual(scalculate.call_count, 2)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], 'Scores recalculated.')

    @patch('django.contrib.admin.ModelAdmin.message_user')
    @patch('heltour.tournament.admin.normalize_gamelink',
           side_effect=[('incorrectlink1', False), ('mockedlink2', True)]
           )
    def test_verify(self, gamelink, message):
        self.client.force_login(user=self.superuser)
        path = reverse('admin:tournament_season_changelist')
        response = self.client.post(path,
                                    data={'action': 'verify_data',
                                          '_selected_action': Season.objects.all().values_list('pk', flat=True)},
                                    follow=True)
        self.assertTrue(message.called)
        self.assertEqual(message.call_args.args[1], 'Data verified.')
        message.reset_mock()
        lr1 = get_round('lone', 1)
        p1 = Player.objects.get(lichess_username="Player1")
        p2 = Player.objects.get(lichess_username="Player2")
        p3 = Player.objects.get(lichess_username="Player3")
        p4 = Player.objects.get(lichess_username="Player4")
        lpp1 = LonePlayerPairing.objects.create(round=lr1, white=p1, black=p2, game_link='incorrectlink1', pairing_order=0)
        lpp2 = LonePlayerPairing.objects.create(round=lr1, white=p3, black=p4, game_link='incorrectlink2', pairing_order=1)
        response = self.client.post(path,
                                    data={'action': 'verify_data',
                                          '_selected_action': Season.objects.all().values_list('pk', flat=True)},
                                    follow=True)
        lpp2.refresh_from_db()
        self.assertEqual(gamelink.call_count, 2)
        self.assertTrue(message.call_count, 2)
        self.assertEqual(message.call_args_list[0][0][1], '1 bad gamelinks for Test Season.')
        self.assertEqual(message.call_args_list[1][0][1], 'Data verified.')
        self.assertEqual(lpp1.game_link, 'incorrectlink1')
        self.assertEqual(lpp2.game_link, 'mockedlink2')
