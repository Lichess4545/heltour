from __future__ import annotations

from fastapi import HTTPException

from heltour.api.event_setup.schemas import CurrentRoundDTO


def current_round_sync(league_tag: str) -> CurrentRoundDTO:
    """Resolve the "current" published round for a league.

    Picks the latest published round, preferring in-progress over
    completed (so once round N's pairings are published the page jumps
    forward, even if N-1 is still marked complete).
    """
    from heltour.tournament.models import League, Round

    try:
        league = League.objects.get(tag=league_tag)
    except League.DoesNotExist:
        raise HTTPException(status_code=404, detail="league not found")

    rnd = (
        Round.objects.filter(season__league=league, publish_pairings=True)
        .select_related("season")
        .order_by("is_completed", "-number")
        .first()
    )
    if rnd is None:
        raise HTTPException(status_code=404, detail="no published round")

    return CurrentRoundDTO(
        league_tag=league.tag,
        event_tag=rnd.season.tag,
        event_name=rnd.season.name,
        round_id=rnd.pk,
        round_number=rnd.number,
    )
