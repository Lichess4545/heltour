from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, TypeVar

from django.db.models import QuerySet
from rest_framework import serializers
from rest_framework.utils.serializer_helpers import ReturnDict

from heltour.api_v2.selectors import LeagueWithRounds, RoundWithPairings
from heltour.tournament.api import export_time_control
from heltour.tournament.models import (
    League,
    LonePlayerPairing,
    Player,
    PlayerPairing,
    Round,
    Team,
    TeamPairing,
    TeamPlayerPairing,
    get_gamelink_from_gameid,
    result_is_forfeit,
)

Instance = TypeVar("Instance")
Pairing = TypeVar("Pairing", bound=PlayerPairing)


class WithoutNullsSerializer(serializers.Serializer[Instance]):
    def to_representation(self, instance: Instance) -> dict[str, Any]:
        represented = super().to_representation(instance)
        return {key: value for key, value in represented.items() if value is not None}


class EpochMillisecondsField(serializers.Field[datetime, datetime, int, Any]):
    def to_representation(self, value: datetime) -> int:
        return round(value.timestamp() * 1000)


class ActiveQuerySerializer(serializers.Serializer[None]):
    active = serializers.BooleanField(allow_null=True, default=None)


class LeagueSerializer(WithoutNullsSerializer[League]):
    tag = serializers.CharField()
    name = serializers.CharField()
    competitorType = serializers.SerializerMethodField(method_name="competitor_type")
    timeControl = serializers.SerializerMethodField(method_name="time_control")
    variant = serializers.CharField()
    rated = serializers.BooleanField(source="games_are_rated")
    active = serializers.BooleanField(source="is_active")

    def competitor_type(self, league: League) -> Literal["team", "lone"]:
        return "team" if league.is_team_league() else "lone"

    def time_control(self, league: League) -> dict[str, int] | None:
        return export_time_control(league)


class LeaguesSerializer(serializers.Serializer[QuerySet[League]]):
    leagues = LeagueSerializer(many=True, source="*")


class RoundSerializer(WithoutNullsSerializer[Round]):
    id = serializers.IntegerField()
    season = serializers.CharField(source="season.tag")
    number = serializers.IntegerField()
    startsAt = EpochMillisecondsField(source="start_date")
    endsAt = EpochMillisecondsField(source="end_date")
    pairingsPublished = serializers.BooleanField(source="publish_pairings")
    completed = serializers.BooleanField(source="is_completed")
    active = serializers.BooleanField()


class RoundsSerializer(serializers.Serializer[QuerySet[Round]]):
    rounds = RoundSerializer(many=True, source="*")


class LeagueWithRoundsSerializer(serializers.Serializer[LeagueWithRounds]):
    def to_representation(self, instance: LeagueWithRounds) -> dict[str, Any]:
        return {
            **LeagueSerializer(instance.league).data,
            **RoundsSerializer(instance.rounds).data,
        }


@dataclass(frozen=True)
class Side:
    player: Player | None
    rating: int | None
    team: int | None
    points: float | None


@dataclass(frozen=True)
class TeamPoints:
    team: Team
    points: float


class UserSerializer(WithoutNullsSerializer[Player]):
    name = serializers.CharField(source="lichess_username")
    id = serializers.SerializerMethodField(method_name="user_id")

    def user_id(self, player: Player) -> str:
        return player.lichess_username.lower()


class SideSerializer(WithoutNullsSerializer[Side]):
    user = UserSerializer(source="player")
    rating = serializers.IntegerField()
    team = serializers.IntegerField()
    points = serializers.FloatField()


class GameSerializer(WithoutNullsSerializer[str]):
    id = serializers.CharField(source="*")
    url = serializers.SerializerMethodField()

    def get_url(self, game_id: str) -> str:
        url: str = get_gamelink_from_gameid(game_id)
        return url


class TeamPointsSerializer(WithoutNullsSerializer[TeamPoints]):
    number = serializers.IntegerField(source="team.number")
    name = serializers.CharField(source="team.name")
    points = serializers.FloatField()


class TeamMatchSerializer(WithoutNullsSerializer[TeamPairing]):
    teams = serializers.SerializerMethodField()
    boards = serializers.IntegerField(source="round.season.boards")

    def get_teams(self, match: TeamPairing) -> list[ReturnDict[str, Any]]:
        return [
            TeamPointsSerializer(TeamPoints(match.white_team, match.white_points)).data,
            TeamPointsSerializer(TeamPoints(match.black_team, match.black_points)).data,
        ]


class PairingSerializer(WithoutNullsSerializer[Pairing]):
    id = serializers.IntegerField()
    players = serializers.SerializerMethodField()
    game = serializers.SerializerMethodField()
    forfeit = serializers.SerializerMethodField()
    scheduledAt = EpochMillisecondsField(source="scheduled_time")

    def get_game(self, pairing: PlayerPairing) -> ReturnDict[str, Any] | None:
        game_id: str | None = pairing.game_id()
        return None if game_id is None else GameSerializer(game_id).data

    def get_forfeit(self, pairing: PlayerPairing) -> Literal[True] | None:
        return True if result_is_forfeit(pairing.result) else None


class LonePairingSerializer(PairingSerializer[LonePlayerPairing]):
    def get_players(
        self, pairing: LonePlayerPairing
    ) -> dict[str, ReturnDict[str, Any]]:
        return players_of(pairing, pairing.round.season.league)


class TeamBoardSerializer(PairingSerializer[TeamPlayerPairing]):
    board = serializers.IntegerField(source="board_number")
    teamMatch = TeamMatchSerializer(source="team_pairing")

    def get_players(self, board: TeamPlayerPairing) -> dict[str, ReturnDict[str, Any]]:
        league = board.team_pairing.round.season.league
        return players_of(
            board, league, board.white_team().number, board.black_team().number
        )


def players_of(
    pairing: PlayerPairing,
    league: League,
    white_team: int | None = None,
    black_team: int | None = None,
) -> dict[str, ReturnDict[str, Any]]:
    white = Side(
        player=pairing.white,
        rating=None if pairing.white is None else pairing.white_rating_display(league),
        team=white_team,
        points=pairing.white_score(),
    )
    black = Side(
        player=pairing.black,
        rating=None if pairing.black is None else pairing.black_rating_display(league),
        team=black_team,
        points=pairing.black_score(),
    )
    return {"white": SideSerializer(white).data, "black": SideSerializer(black).data}


class RoundWithPairingsSerializer(serializers.Serializer[RoundWithPairings]):
    def to_representation(self, instance: RoundWithPairings) -> dict[str, Any]:
        return {
            **RoundSerializer(instance.round).data,
            "pairings": [
                *(TeamBoardSerializer(board).data for board in instance.team_boards),
                *(LonePairingSerializer(lone).data for lone in instance.lone_pairings),
            ],
        }
