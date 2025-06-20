from django.test import TestCase

from heltour.tournament.alternates_manager import do_alternate_search
from heltour.tournament.models import AlternateSearch, AlternatesManagerSetting
from heltour.tournament.tests.testutils import (
    createCommonLeagueData,
    get_league,
    get_round,
    get_season,
)


class AlternatesManagerTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        createCommonLeagueData()
        cls.l = get_league(league_type="team")
        cls.s = get_season(league_type="team")
        cls.r = get_round(league_type="team", round_number=1)
        cls.setting = AlternatesManagerSetting.objects.create(league=cls.l)

    def test_do_empty_alternate_search(self):
        do_alternate_search(
            season=self.s, round_=self.r, board_number=1, setting=self.setting
        )
        self.assertEqual(AlternateSearch.objects.all().count(), 0)
