from datetime import timedelta
from django.test import TestCase
from django.utils import timezone
from django.urls import reverse
from django.contrib import admin
from django.contrib.auth.models import User
from heltour.tournament.admin import ScheduledNotificationAdmin
from heltour.tournament.models import LonePlayerPairing, ScheduledNotification
from heltour.tournament.tests.testutils import createCommonLeagueData, get_season


class AdminSearchTestCase(TestCase):
    def setUp(self):
        createCommonLeagueData()
        season = get_season('lone')
        round1 = season.round_set.get(number=1)
        sps = season.seasonplayer_set.all()
        pairing1 = LonePlayerPairing.objects.create(round=round1, white=sps[0].player,
                                                    black=sps[1].player, pairing_order=1)
        pairing1.scheduled_time = timezone.now() + timedelta(hours=2)
        pairing1.save()

    def test_schedulednotifcation_search(self, *args):
        model_admin_class = ScheduledNotification
        for fieldname in ScheduledNotificationAdmin.search_fields:
            query = f'{fieldname}__icontains'
            kwargs = {query: 'Player'}
            self.assertEqual(model_admin_class.objects.filter(**kwargs).count(), 2)

    def test_all_search_fields(self):
        superuser = User(
            username="superuser",
            password="Password",
            is_superuser=True,
            is_staff=True,
        )
        superuser.full_clean()
        superuser.save()
        self.client.force_login(superuser)
        for model_class, admin_class in admin.site._registry.items():
            with self.subTest(model_class._meta.model_name):
                path = reverse(f"admin:{model_class._meta.app_label}_{model_class._meta.model_name}_changelist")
                response = self.client.get(path + "?q=whatever")
                self.assertEqual(response.status_code, 200)
