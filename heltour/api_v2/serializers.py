from datetime import datetime
from typing import Any, Literal, TypeVar

from django.db.models import QuerySet
from rest_framework import serializers

from heltour.api_v2.selectors import LeagueWithRounds
from heltour.tournament.api import export_time_control
from heltour.tournament.models import League, Round

Instance = TypeVar("Instance")


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
