import logging

from django.conf import settings
from django.urls import reverse

from heltour.tournament.models import (
    League,
    LonePlayerScore,
    Player,
    Registration,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamScore,
)


def set_rating(player, rating, rating_type="classical"):
    player.profile = {"perfs": {rating_type: {"rating": rating}}}


def create_reg(season, name):
    pl, _ = Player.objects.get_or_create(lichess_username=name)
    return Registration.objects.create(
        season=season,
        status="pending",
        player=pl,
        email="a@test.com",
        has_played_20_games=True,
        can_commit=True,
        agreed_to_rules=True,
        agreed_to_tos=True,
        alternate_preference="full_time",
    )


def get_valid_registration_form_data():
    """Helper to get valid form data for registration tests."""
    return {
        "agreed_to_tos": True,
        "agreed_to_rules": True,
        "can_commit": True,
        "friends": "",
        "avoid": "",
        "alternate_preference": "full_time",
        "first_name": "Test",
        "last_name": "Player",
        "gender": "male",
        "date_of_birth": "1995-06-20",
        "nationality": "US",
        "corporate_email": "test@company.com",
        "personal_email": "",
        "contact_number_0": "US",
        "contact_number_1": "2015550123",
        "fide_id": "",
        "email": "test@example.com",
        "has_played_20_games": True,
    }


def league_tag(league_type):
    return "%sleague" % league_type


def season_tag(league_type):
    return "%sseason" % league_type


def league_url(league_type, page_name):
    return reverse("by_league:%s" % page_name, args=[league_tag(league_type)])


def season_url(league_type, page_name):
    return reverse(
        "by_league:by_season:%s" % page_name,
        args=[league_tag(league_type), season_tag(league_type)],
    )


def get_league(league_type):
    return League.objects.get(tag="%sleague" % league_type)


def get_season(league_type):
    return Season.objects.get(tag="%sseason" % league_type)


def get_player(player_name):
    return Player.objects.get(lichess_username__iexact=player_name)


def get_round(league_type, round_number):
    return Round.objects.get(season=get_season(league_type), number=round_number)


def get_team(team_name: str) -> Team:
    return Team.objects.get(name=team_name)


def createCommonLeagueData(round_count: int = 3, team_count: int = 4) -> None:
    board_count = 2

    league = League.objects.create(
        name="Team League",
        tag=league_tag("team"),
        competitor_type="team",
        rating_type="classical",
    )
    season = Season.objects.create(
        league=league,
        name="Test Season",
        tag=season_tag("team"),
        rounds=round_count,
        boards=board_count,
    )
    league2 = League.objects.create(
        name="Lone League",
        tag=league_tag("lone"),
        competitor_type="lone",
        rating_type="classical",
    )
    season2 = Season.objects.create(
        league=league2, name="Test Season", tag=season_tag("lone"), rounds=round_count
    )

    player_num = 1
    for n in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=n, name="Team %s" % n)
        TeamScore.objects.create(team=team)
        for b in range(1, board_count + 1):
            player = Player.objects.create(lichess_username="Player%d" % player_num)
            sp = SeasonPlayer.objects.create(season=season2, player=player)
            LonePlayerScore.objects.create(season_player=sp)
            player_num += 1
            TeamMember.objects.create(team=team, player=player, board_number=b)


class Shush:
    def __enter__(self):
        self._prev_disable_level = logging.root.manager.disable
        logging.disable(logging.CRITICAL)
        return self

    def __exit__(self, exc_type, exc_value, exc_traceback):
        logging.disable(self._prev_disable_level)
        if exc_type is not None:
            logging.getLogger(__name__).error(f"Error {exc_type}: {exc_value}")
        return True


def can_run_javafo():
    """Check if we can run JavaFo tests."""
    if not hasattr(settings, "JAVAFO_COMMAND"):
        print(
            "\nWARNING: Skipping JavaFo tests - JAVAFO_COMMAND not configured in settings"
        )
        return False
    try:
        import subprocess

        result = subprocess.run(["java", "-version"], capture_output=True)
        return result.returncode == 0
    except:
        return False


# Tournament structure creation utilities (from tournament_core test_utils)
# These create pure tournament_core structures without database dependencies


def create_simple_round_robin(num_players: int = 4):
    """Create a simple round robin tournament structure.

    Note: This uses tournament_core.builder.TournamentBuilder which creates
    pure structures without database persistence.
    """
    from heltour.tournament_core.builder import TournamentBuilder

    players = list(range(1, num_players + 1))
    builder = TournamentBuilder(players)

    # Simple pairing for round robin
    for round_num in range(1, num_players):
        builder.add_round(round_num)

        # Pair players in a round robin fashion
        for i in range(num_players // 2):
            if round_num == 1:
                p1 = players[i]
                p2 = players[num_players - 1 - i]
            else:
                # Rotate players for subsequent rounds
                rotated = [players[0]] + players[2:] + [players[1]]
                p1 = rotated[i]
                p2 = rotated[num_players - 1 - i]

            # Alternate results for variety
            result = (
                "1-0"
                if (i + round_num) % 3 == 0
                else ("1/2-1/2" if (i + round_num) % 3 == 1 else "0-1")
            )
            builder.add_game(p1, p2, result)

        # Add bye if odd number of players
        if num_players % 2 == 1:
            builder.auto_byes()

    return builder.build()


def create_simple_team_tournament(num_teams: int = 4, boards_per_team: int = 4):
    """Create a simple team tournament structure.

    Note: This uses tournament_core.builder.TournamentBuilder which creates
    pure structures without database persistence.
    """
    from heltour.tournament_core.builder import TournamentBuilder

    teams = list(range(1, num_teams + 1))
    builder = TournamentBuilder(teams)

    # Create a simple 2-round tournament
    builder.add_round(1)

    # Round 1: 1v2, 3v4
    if num_teams >= 4:
        # Team 1 vs Team 2
        board_results = []
        for board in range(1, boards_per_team + 1):
            p1 = 100 + board  # Team 1 players: 101, 102, 103, 104
            p2 = 200 + board  # Team 2 players: 201, 202, 203, 204
            result = "1-0" if board % 2 == 1 else "0-1"  # Alternating wins
            board_results.append((p1, p2, result))
        builder.add_team_match(1, 2, board_results)

        # Team 3 vs Team 4
        board_results = []
        for board in range(1, boards_per_team + 1):
            p1 = 300 + board  # Team 3 players
            p2 = 400 + board  # Team 4 players
            result = "1/2-1/2"  # All draws
            board_results.append((p1, p2, result))
        builder.add_team_match(3, 4, board_results)

    return builder.build()
