from dataclasses import dataclass
from typing import TypeVar

from django.db.models import BooleanField, ExpressionWrapper, Model, QuerySet

from heltour.tournament.api import ACTIVE_ROUND
from heltour.tournament.models import League, Round

Row = TypeVar("Row", bound=Model)


@dataclass(frozen=True)
class LeagueWithRounds:
    league: League
    rounds: QuerySet[Round]


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


def rounds_of(league: League) -> QuerySet[Round]:
    return all_rounds().filter(season__league=league)


def all_rounds() -> QuerySet[Round]:
    return uncached(
        Round.objects.select_related("season")
        .annotate(active=ExpressionWrapper(ACTIVE_ROUND, output_field=BooleanField()))
        .order_by("-season__start_date", "-season__id", "-number")
    )


def uncached(rows: QuerySet[Row]) -> QuerySet[Row]:
    uncached_rows: QuerySet[Row] = rows.nocache()  # type: ignore[attr-defined]
    return uncached_rows
