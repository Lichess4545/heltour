from datetime import timedelta
#from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from django.contrib.admin.sites import AdminSite
from heltour.tournament.admin import ScheduledNotificationAdmin
from heltour.tournament.models import LonePlayerPairing, ScheduledNotification
from heltour.tournament.tests.testutils import createCommonLeagueData, get_season


class AdminSearchTestCase(TestCase):
    def setUp(self):
        self.site = AdminSite()
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

