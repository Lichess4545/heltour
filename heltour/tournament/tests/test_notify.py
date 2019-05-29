from django.test import TestCase
import heltour.tournament.models as m
from unittest.mock import MagicMock, Mock, patch


def create_lone_league():

    league2 = m.League.objects.create(
            name='Lone League',
            tag='lone')
    season2 = m.Season.objects.create(
            league=league2,
            name='Lone Season',
            tag='lone',
            rounds=round_count,
            boards=board_count)


def create_team_league():
    team_count = 4
    round_count = 3
    board_count = 2

    league = m.League.objects.create(
            name='Team League',
            tag='team',
            competitor_type='team')

    season = m.Season.objects.create(
            league=league,
            name='Team Season',
            tag='team',
            rounds=round_count,
            boards=board_count)

    for team_num in range(1, team_count + 1):
        team = m.Team.objects.create(
                season=season,
                number=team_num,
                name=f'Team {team_num}')
        m.TeamScore.objects.create(team=team)
        for board_num in range(1, board_count + 1):
            player = m.Player.objects.create(
                    lichess_username=f'p-t{team_num}-b{board_num}')
            sp = m.SeasonPlayer.objects.create(season=season, player=player)
            m.TeamMember.objects.create(
                    team=team,
                    player=player,
                    board_number=board_num)

def make_alternate():
    season = m.Season.objects.first()
    alt_player = m.Player.objects.create(lichess_username='Alternate')
    sp = m.SeasonPlayer.objects.create(season=season, player=alt_player)
    alt = m.Alternate.objects.create(season_player=sp, board_number=1)
    return (alt_player, sp, alt)

def make_team_pairing(t1, t2):
    return m.TeamPairing.objects.create(
            white_team=t1,
            black_team=t2,
            round=m.Round.objects.get(number=1),
            pairing_order=0)

def make_player_pairing(tp, t1, t2):
    return m.TeamPlayerPairing.objects.create(
            team_pairing=tp,
            board_number=1,
            white=t1.board(1),
            black=t2.board(1))

class NotifyAlternateAndOpponentTestCase(TestCase):
    def setUp(self):
        create_team_league()


    def test_with_and_without_captains(self):
        t1, t2 = m.Team.objects.get(number=1), m.Team.objects.get(number=2)
        tp = make_team_pairing(t1, t2)
        tpp = make_player_pairing(tp, t1, t2)
        alt_player, sp, alt = make_alternate()
        aa = m.AlternateAssignment.objects.create(
                round=tp.round,
                team=t1,
                board_number=1,
                player=alt_player)

        league = m.League.objects.first()

        test_message_user = MagicMock()
        with patch.multiple('heltour.tournament.notify',
                _message_user=test_message_user,
                send_pairing_notification=MagicMock()):

            from heltour.tournament.notify import _notify_alternate_and_opponent
            _notify_alternate_and_opponent(league, aa)
            first_call = test_message_user.call_args_list[0]
            pos_args = first_call[0]
            message = pos_args[2]
            self.assertNotIn(f'The team captain is <@', message)


        t1.set_captain(t1.board(2))
        test_message_user = MagicMock()
        with patch.multiple('heltour.tournament.notify',
                _message_user=test_message_user,
                send_pairing_notification=MagicMock()):

            from heltour.tournament.notify import _notify_alternate_and_opponent
            _notify_alternate_and_opponent(league, aa)
            first_call = test_message_user.call_args_list[0]
            pos_args = first_call[0]
            message = pos_args[2]
            self.assertIn(f'The team captain is <@', message)

    def test_no_team_pairing(self):
        league = m.League.objects.first()
        alt_player, sp, alt = make_alternate()
        t1 = m.Team.objects.get(number=1)
        aa = m.AlternateAssignment.objects.create(
                round=m.Round.objects.get(number=1),
                team=t1,
                board_number=1,
                player=alt_player)

        test_message_user = MagicMock()
        spn = MagicMock()
        with patch.multiple('heltour.tournament.notify',
                _message_user=test_message_user,
                send_pairing_notification=spn()):

            from heltour.tournament.notify import _notify_alternate_and_opponent
            _notify_alternate_and_opponent(league, aa)
            first_call = test_message_user.call_args_list[0]
            pos_args = first_call[0]
            message = pos_args[2]
            self.assertEqual(
                    '@alternate: You will be playing on board 1 of '
                    '"Team 1" for round 1.',
                    message)

    def test_no_team_player_pairings_yet(self):
        league = m.League.objects.first()
        t1, t2 = m.Team.objects.get(number=1), m.Team.objects.get(number=2)
        tp = make_team_pairing(t1, t2)
        alt_player, sp, alt = make_alternate()
        aa = m.AlternateAssignment.objects.create(
                round=m.Round.objects.get(number=1),
                team=t1,
                board_number=1,
                player=alt_player)

        test_message_user = MagicMock()
        spn = MagicMock()
        with patch.multiple('heltour.tournament.notify',
                _message_user=test_message_user,
                send_pairing_notification=spn()):

            from heltour.tournament.notify import _notify_alternate_and_opponent
            _notify_alternate_and_opponent(league, aa)
            first_call = test_message_user.call_args_list[0]
            pos_args = first_call[0]
            message = pos_args[2]
            self.assertEqual(
                    '@alternate: You will be playing on board 1 of '
                    '"Team 1" for round 1.',
                    message)

    def test_opponent_not_available(self):
        league = m.League.objects.first()
        r = m.Round.objects.get(number=1)
        t1, t2 = m.Team.objects.get(number=1), m.Team.objects.get(number=2)
        tp = make_team_pairing(t1, t2)
        tpp = make_player_pairing(tp, t1, t2)
        alt_player, sp, alt = make_alternate()
        aa = m.AlternateAssignment.objects.create(
                round=m.Round.objects.get(number=1),
                team=t1,
                board_number=1,
                player=alt_player)

        tpp.refresh_from_db()
        opp = tpp.opponent_of(aa.player)
        m.PlayerAvailability.objects.create(
                round=r,
                player=opp,
                is_available=False)
        test_message_user = MagicMock()
        spn = MagicMock()
        with patch.multiple('heltour.tournament.notify',
                _message_user=test_message_user,
                send_pairing_notification=spn()):

            from heltour.tournament.notify import _notify_alternate_and_opponent
            _notify_alternate_and_opponent(league, aa)
            first_call = test_message_user.call_args_list[0]
            pos_args = first_call[0]
            message = pos_args[2]
            self.assertIn('I am still searching', message)


class SendPairingNotificationTestCase(TestCase):
    def setUp(self):
        create_team_league()

    def commonObjects(self):
        league = m.League.objects.first()
        r = m.Round.objects.get(number=1)
        t1, t2 = m.Team.objects.get(number=1), m.Team.objects.get(number=2)
        tp = make_team_pairing(t1, t2)
        tpp = make_player_pairing(tp, t1, t2)
        white, black = tpp.white, tpp.black
        return league, r, t1, t2, tp, tpp, white, black

    def test_captains(self):
        league, r, t1, t2, tp, tpp, white, black = self.commonObjects()
        t1.set_captain(t1.board(2))
        t2.set_captain(t2.board(2))
        #  pns = MagicMock(spec=m.PlayerNotificationSetting)
        #  pns.get_or_default.return_value = Mock(
                #  k
                #  )
        lc, lm, mmu = MagicMock(), MagicMock(), MagicMock()
        first = Mock()
        first.return_value = 'schedule'
        lc.objects.filter.return_value = first
        with patch.multiple('heltour.tournament.notify',
                LeagueChannel=lc,
                _lichess_message=lm,
                _message_multiple_users=mmu):
            from heltour.tournament.notify import send_pairing_notification

            send_pairing_notification('round_started', tpp, 'm', 'm', 'm', 'm')
            mmu.assert_called_with(
                    league,
                    [p.lichess_username.lower()
                        for p in [white, black, t1.board(2), t2.board(2)]],
                    'm')
    def test_mpim_urls(self):
        league, r, t1, t2, tp, tpp, white, black = self.commonObjects()

        lc = MagicMock()
        first = Mock()
        first.return_value = 'schedule'
        lc.objects.filter.return_value = first

        lm, mmu = MagicMock(), MagicMock()
        with patch.multiple('heltour.tournament.notify',
                LeagueChannel=lc,
                _lichess_message=lm,
                _message_multiple_users=mmu):
            from heltour.tournament.notify import send_pairing_notification

            li_msg = '{slack_url}'
            send_pairing_notification('round_started', tpp, 'm', 'm', 'm',
                    li_msg)
            print(lm.call_args_list[0][0][3])

        t1.set_captain(t1.board(2))
        t2.set_captain(t2.board(2))
        lm, mmu = MagicMock(), MagicMock()
        with patch.multiple('heltour.tournament.notify',
                LeagueChannel=lc,
                _lichess_message=lm,
                _message_multiple_users=mmu):
            from heltour.tournament.notify import send_pairing_notification

            li_msg = '{slack_url}'
            send_pairing_notification('round_started', tpp, 'm', 'm', 'm',
                    li_msg)
            print(lm.call_args_list[0][0][3])

        t2.set_captain(t2.board(1))
        lm, mmu = MagicMock(), MagicMock()
        with patch.multiple('heltour.tournament.notify',
                LeagueChannel=lc,
                _lichess_message=lm,
                _message_multiple_users=mmu):
            from heltour.tournament.notify import send_pairing_notification

            li_msg = '{slack_url}'
            send_pairing_notification('round_started', tpp, 'm', 'm', 'm',
                    li_msg)
            print(lm.call_args_list[0][0][3])

        pns = m.PlayerNotificationSetting.get_or_default(
                league=league,
                player=t1.board(1),
                type='round_started')
        pns.enable_slack_mpim = False
        pns.save()

        lm, mmu = MagicMock(), MagicMock()
        with patch.multiple('heltour.tournament.notify',
                LeagueChannel=lc,
                _lichess_message=lm,
                _message_multiple_users=mmu):
            from heltour.tournament.notify import send_pairing_notification

            li_msg = '{slack_url}'
            send_pairing_notification('round_started', tpp, 'm', 'm', 'm',
                    li_msg)
            print(lm.call_args_list[0][0][3])
