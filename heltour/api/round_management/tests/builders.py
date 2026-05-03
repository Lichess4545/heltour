"""Test data builders for round-management tests.

Kept in a sibling module so both the sync-service tests and the HTTP
integration tests share the same fixtures. The shape mirrors what
``tournament_core.builder`` does for pure-Python tests, but here we go
all the way to the Django ORM so we can exercise the real query path.
"""

from __future__ import annotations

from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    Player,
    Round,
    Season,
    Team,
    TeamMember,
    TeamPairing,
    TeamPlayerPairing,
)


def make_team_round(
    *,
    league_tag: str,
    season_tag: str,
    boards: int,
    team_count: int,
    publish: bool = True,
    show_fide_names: bool = False,
):
    """Build a single team Round with `team_count // 2` team matches and
    `boards` boards each. Returns the created Round.
    """
    league = League.objects.create(
        name=f"League {league_tag}",
        tag=league_tag,
        competitor_type="team",
        rating_type="classical",
        show_fide_names=show_fide_names,
    )
    season = Season.objects.create(
        league=league,
        name=f"Season {season_tag}",
        tag=season_tag,
        rounds=1,
        boards=boards,
    )
    rnd = Round.objects.get(season=season, number=1)
    rnd.publish_pairings = publish
    rnd.save()

    teams = []
    player_n = 0
    for t in range(1, team_count + 1):
        team = Team.objects.create(season=season, number=t, name=f"{league_tag}-T{t}")
        for b in range(1, boards + 1):
            player_n += 1
            p = Player.objects.create(
                lichess_username=f"{league_tag}_p{player_n}",
                profile={"perfs": {"classical": {"rating": 1500 + player_n}}},
            )
            TeamMember.objects.create(team=team, player=p, board_number=b)
        teams.append(team)

    pairing_order = 0
    for i in range(0, team_count, 2):
        pairing_order += 1
        white_team = teams[i]
        black_team = teams[i + 1]
        tp = TeamPairing.objects.create(
            white_team=white_team,
            black_team=black_team,
            round=rnd,
            pairing_order=pairing_order,
        )
        wm = list(white_team.teammember_set.order_by("board_number"))
        bm = list(black_team.teammember_set.order_by("board_number"))
        for b in range(boards):
            TeamPlayerPairing.objects.create(
                team_pairing=tp,
                board_number=b + 1,
                white=wm[b].player,
                black=bm[b].player,
                result="1-0" if b % 2 == 0 else "0-1",
                game_link="",
            )
    return rnd


def make_lone_round(
    *,
    league_tag: str,
    season_tag: str,
    pairing_count: int,
    publish: bool = True,
):
    league = League.objects.create(
        name=f"Lone {league_tag}",
        tag=league_tag,
        competitor_type="individual",
        rating_type="classical",
    )
    season = Season.objects.create(
        league=league, name=f"Season {season_tag}", tag=season_tag, rounds=1,
    )
    rnd = Round.objects.get(season=season, number=1)
    rnd.publish_pairings = publish
    rnd.save()

    for i in range(1, pairing_count + 1):
        white = Player.objects.create(
            lichess_username=f"{league_tag}_w{i}",
            profile={"perfs": {"classical": {"rating": 1700 + i}}},
        )
        black = Player.objects.create(
            lichess_username=f"{league_tag}_b{i}",
            profile={"perfs": {"classical": {"rating": 1600 + i}}},
        )
        LonePlayerPairing.objects.create(
            round=rnd,
            white=white,
            black=black,
            pairing_order=i,
            result="1-0",
            game_link="",
        )
    return rnd
