from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.contrib import admin
from django.contrib.auth.models import User
from heltour.tournament.models import Alternate, Player, SeasonPlayer
from heltour.tournament.tests.testutils import createCommonLeagueData, get_season, get_player


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
        cls.superuser = User(
            username='superuser',
            password='Password',
            is_superuser=True,
            is_staff=True,
        )
        cls.superuser.save()
        cls.p = get_player('Player1')
        cls.sp = SeasonPlayer.objects.create(player=cls.p, season=cls.season)


    def test_add_alternate(self):
        self.client.force_login(user=self.superuser)
        response = self.client.post(f'/admin/tournament/season/{self.season.pk}/manage_players/',
                                    data={"changes": '[{"action": "create-alternate", "board_number": 1, "player_name": "Player1"}]'})
        self.assertEqual(Alternate.objects.all().count(), 1)
        self.assertEqual(Alternate.objects.all().first().season_player.player.lichess_username, 'Player1')
