"""
Export Django ORM tournament data to TRF16 format.

Entry point: season_to_trf16(season) → TRF16 string.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from heltour.tournament.models import (
    LonePlayerPairing,
    Player,
    PlayerBye,
    Round,
    Season,
    SeasonPlayer,
    Team,
    TeamMember,
    TeamPlayerPairing,
)
from heltour.tournament_core.trf16 import TRF16Header, TRF16Player, TRF16Team
from heltour.tournament_core.trf16_writer import write_trf16


# Result mapping: (model result, is_white, colors_reversed) → (color, trf_result)
# The "effective white" is: white if not colors_reversed, else black
_RESULT_MAP = {
    "1-0": ("1", "0"),
    "0-1": ("0", "1"),
    "1/2-1/2": ("=", "="),
    "1/2Z-1/2Z": ("=", "="),
    "1X-0F": ("+", "-"),
    "0F-1X": ("-", "+"),
    "0F-0F": ("-", "-"),
}


def season_to_trf16(season: Season) -> str:
    if season.league.competitor_type == "team":
        return _team_season_to_trf16(season)
    return _lone_season_to_trf16(season)


def _team_season_to_trf16(season: Season) -> str:
    rounds = list(Round.objects.filter(season=season).order_by("number"))
    teams = list(
        Team.objects.filter(season=season, is_active=True)
        .prefetch_related("teammember_set__player")
        .order_by("number")
    )

    # Assign start numbers: team order, then board order within team
    player_start_nums: Dict[int, int] = {}  # player.pk → start_number
    start_num_players: Dict[int, _PlayerInfo] = {}  # start_number → info
    trf_teams: Dict[str, TRF16Team] = {}
    current_num = 1

    for team in teams:
        members = list(team.teammember_set.order_by("board_number"))
        team_player_ids: List[int] = []
        for member in members:
            player_start_nums[member.player_id] = current_num
            start_num_players[current_num] = _PlayerInfo(
                player=member.player,
                rating=member.player_rating or member.player.rating_for(season.league) or 0,
            )
            team_player_ids.append(current_num)
            current_num += 1
        trf_teams[team.name] = TRF16Team(name=team.name, player_ids=team_player_ids)

    # Build results per player per round
    num_rounds = len(rounds)
    results_by_player: Dict[int, List[Optional[Tuple[Optional[int], str, str]]]] = {
        sn: [None] * num_rounds for sn in start_num_players
    }

    for round_idx, rnd in enumerate(rounds):
        pairings = TeamPlayerPairing.objects.filter(
            team_pairing__round=rnd
        ).select_related("white", "black", "team_pairing")

        for pp in pairings:
            _record_pairing_result(
                pp, round_idx, player_start_nums, results_by_player
            )

    # Fill unplayed rounds as byes
    _fill_byes(results_by_player)

    # Build TRF16 players
    trf_players = _build_trf_players(start_num_players, results_by_player, num_rounds)

    header = _build_header(season, len(trf_players), len(trf_teams), num_rounds, rounds)
    return write_trf16(header, trf_players, trf_teams)


def _lone_season_to_trf16(season: Season) -> str:
    rounds = list(Round.objects.filter(season=season).order_by("number"))

    # Get all season players, ordered by seed rating (descending)
    season_players = list(
        SeasonPlayer.objects.filter(season=season, is_active=True)
        .select_related("player")
        .order_by("-seed_rating", "player__lichess_username")
    )

    # Assign start numbers by rating seed order
    player_start_nums: Dict[int, int] = {}
    start_num_players: Dict[int, _PlayerInfo] = {}

    for idx, sp in enumerate(season_players, 1):
        player_start_nums[sp.player_id] = idx
        start_num_players[idx] = _PlayerInfo(
            player=sp.player,
            rating=sp.seed_rating or sp.player.rating_for(season.league) or 0,
        )

    num_rounds = len(rounds)
    results_by_player: Dict[int, List[Optional[Tuple[Optional[int], str, str]]]] = {
        sn: [None] * num_rounds for sn in start_num_players
    }

    for round_idx, rnd in enumerate(rounds):
        pairings = LonePlayerPairing.objects.filter(round=rnd).select_related(
            "white", "black"
        )
        for pp in pairings:
            _record_pairing_result(
                pp, round_idx, player_start_nums, results_by_player
            )

        # Explicit byes
        byes = PlayerBye.objects.filter(round=rnd)
        for bye in byes:
            sn = player_start_nums.get(bye.player_id)
            if sn and results_by_player[sn][round_idx] is None:
                results_by_player[sn][round_idx] = (None, "-", "-")

    _fill_byes(results_by_player)

    trf_players = _build_trf_players(start_num_players, results_by_player, num_rounds)

    header = _build_header(season, len(trf_players), 0, num_rounds, rounds)
    return write_trf16(header, trf_players)


class _PlayerInfo:
    __slots__ = ("player", "rating")

    def __init__(self, player: Player, rating: int):
        self.player = player
        self.rating = rating


def _record_pairing_result(
    pp,
    round_idx: int,
    player_start_nums: Dict[int, int],
    results_by_player: Dict[int, List[Optional[Tuple[Optional[int], str, str]]]],
) -> None:
    if not pp.result or pp.result not in _RESULT_MAP:
        return

    white_sn = player_start_nums.get(pp.white_id) if pp.white_id else None
    black_sn = player_start_nums.get(pp.black_id) if pp.black_id else None
    white_trf, black_trf = _RESULT_MAP[pp.result]

    # colors_reversed swaps effective colors
    if pp.colors_reversed:
        white_color, black_color = "b", "w"
        white_trf, black_trf = black_trf, white_trf
    else:
        white_color, black_color = "w", "b"

    # Forfeits: no real opponent, use special TRF16 encoding
    is_forfeit = pp.result in ("1X-0F", "0F-1X", "0F-0F")

    if white_sn and white_sn in results_by_player:
        if is_forfeit:
            results_by_player[white_sn][round_idx] = (0, "-", white_trf)
        else:
            opp = black_sn if black_sn else 0
            results_by_player[white_sn][round_idx] = (opp, white_color, white_trf)

    if black_sn and black_sn in results_by_player:
        if is_forfeit:
            results_by_player[black_sn][round_idx] = (0, "-", black_trf)
        else:
            opp = white_sn if white_sn else 0
            results_by_player[black_sn][round_idx] = (opp, black_color, black_trf)


def _fill_byes(
    results_by_player: Dict[int, List[Optional[Tuple[Optional[int], str, str]]]],
) -> None:
    for sn, results in results_by_player.items():
        for i, r in enumerate(results):
            if r is None:
                results[i] = (None, "-", "-")


def _build_trf_players(
    start_num_players: Dict[int, _PlayerInfo],
    results_by_player: Dict[int, List[Optional[Tuple[Optional[int], str, str]]]],
    num_rounds: int,
) -> Dict[int, TRF16Player]:
    trf_players: Dict[int, TRF16Player] = {}

    # Calculate points and rank
    points_map: Dict[int, float] = {}
    for sn, results in results_by_player.items():
        total = 0.0
        for r in results:
            if r is not None:
                total += _result_points(r[2])
        points_map[sn] = total

    # Rank by points descending, then by start number ascending
    ranked = sorted(points_map.keys(), key=lambda sn: (-points_map[sn], sn))
    rank_map = {sn: rank for rank, sn in enumerate(ranked, 1)}

    for sn, info in start_num_players.items():
        trf_players[sn] = TRF16Player(
            team_number=sn,
            board_number=0,
            title="-",
            name=info.player.lichess_username,
            rating=info.rating,
            federation="---",
            fide_id="0",
            birth_year=0,
            points=points_map.get(sn, 0.0),
            rank=rank_map.get(sn, 0),
            start_number=sn,
            results=results_by_player.get(sn, []),
        )

    return trf_players


def _result_points(trf_result: str) -> float:
    if trf_result == "1":
        return 1.0
    if trf_result in ("=", "1/2"):
        return 0.5
    if trf_result == "+":
        return 1.0
    return 0.0


def _build_header(
    season: Season,
    num_players: int,
    num_teams: int,
    num_rounds: int,
    rounds: List[Round],
) -> TRF16Header:
    now = datetime.now()
    start_date = season.start_date or now
    round_dates = [r.start_date for r in rounds if r.start_date]

    return TRF16Header(
        tournament_name=f"{season.league.name} - {season.name}",
        city="Internet",
        federation="INT",
        start_date=start_date,
        end_date=rounds[-1].end_date if rounds and rounds[-1].end_date else start_date,
        num_players=num_players,
        num_rated_players=num_players,
        num_teams=num_teams,
        tournament_type="Team Swiss" if num_teams > 0 else "Swiss",
        chief_arbiter="",
        deputy_arbiters=[],
        time_control=season.league.time_control or "",
        num_rounds=num_rounds,
        round_dates=round_dates,
    )
