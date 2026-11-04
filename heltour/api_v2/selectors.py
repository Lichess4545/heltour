from dataclasses import dataclass
from typing import TypeVar

from django.db.models import BooleanField, ExpressionWrapper, Model, QuerySet

from heltour.tournament.api import ACTIVE_ROUND
from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    Round,
    TeamPlayerPairing,
)

Row = TypeVar("Row", bound=Model)


@dataclass(frozen=True)
class LeagueWithRounds:
    league: League
    rounds: QuerySet[Round]


@dataclass(frozen=True)
class RoundWithPairings:
    round: Round
    team_boards: QuerySet[TeamPlayerPairing]
    lone_pairings: QuerySet[LonePlayerPairing]


def leagues(active: bool | None) -> QuerySet[League]:
    ordered = League.objects.order_by("display_order", "tag")
    return ordered if active is None else ordered.filter(is_active=active)


def league(tag: str) -> League | None:
    return League.objects.filter(tag=tag).first()


def league_with_rounds(tag: str) -> LeagueWithRounds | None:
    found = league(tag)
    if found is None:
        return None
    return LeagueWithRounds(found, rounds_of(found))


def rounds_of(league: League, active: bool | None = None) -> QuerySet[Round]:
    rounds = all_rounds().filter(season__league=league)
    return rounds if active is None else rounds.filter(active=active)


def round_with_pairings(tag: str, round_id: int) -> RoundWithPairings | None:
    round_ = all_rounds().filter(season__league__tag=tag, pk=round_id).first()
    if round_ is None:
        return None
    return RoundWithPairings(round_, team_boards_of(round_), lone_pairings_of(round_))


def all_rounds() -> QuerySet[Round]:
    return uncached(
        Round.objects.select_related("season")
        .annotate(active=ExpressionWrapper(ACTIVE_ROUND, output_field=BooleanField()))
        .order_by("-season__start_date", "-season__id", "-number")
    )


def team_boards_of(round_: Round) -> QuerySet[TeamPlayerPairing]:
    return uncached(
        TeamPlayerPairing.objects.filter(team_pairing__round=round_)
        .select_related(
            "white",
            "black",
            "team_pairing__round__season__league",
            "team_pairing__white_team",
            "team_pairing__black_team",
        )
        .order_by("team_pairing__pairing_order", "board_number")
    )


def lone_pairings_of(round_: Round) -> QuerySet[LonePlayerPairing]:
    return uncached(
        LonePlayerPairing.objects.filter(round=round_)
        .select_related("white", "black", "round__season__league")
        .order_by("pairing_order")
    )


def uncached(rows: QuerySet[Row]) -> QuerySet[Row]:
    uncached_rows: QuerySet[Row] = rows.nocache()  # type: ignore[attr-defined]
    return uncached_rows
