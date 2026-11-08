from typing import TypeVar

from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from heltour.api_v2 import selectors
from heltour.api_v2.serializers import (
    ActiveQuerySerializer,
    LeaguesSerializer,
    LeagueWithRoundsSerializer,
    RoundsSerializer,
    RoundWithPairingsSerializer,
)

Found = TypeVar("Found")


class LeaguesView(APIView):
    def get(self, request: Request) -> Response:
        leagues = selectors.leagues(active_filter(request))
        return Response(LeaguesSerializer(leagues).data)


class LeagueView(APIView):
    def get(self, request: Request, tag: str) -> Response:
        league = found(selectors.league_with_rounds(tag))
        return Response(LeagueWithRoundsSerializer(league).data)


class RoundsView(APIView):
    def get(self, request: Request, tag: str) -> Response:
        league = found(selectors.league(tag))
        rounds = selectors.rounds_of(league, active_filter(request))
        return Response(RoundsSerializer(rounds).data)


class RoundView(APIView):
    def get(self, request: Request, tag: str, round_id: int) -> Response:
        round_ = found(selectors.round_with_pairings(tag, round_id))
        return Response(RoundWithPairingsSerializer(round_).data)


def active_filter(request: Request) -> bool | None:
    query = ActiveQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    active: bool | None = query.validated_data["active"]
    return active


def found(value: Found | None) -> Found:
    if value is None:
        raise NotFound
    return value
