from pydantic import BaseModel


class CurrentRoundDTO(BaseModel):
    league_tag: str
    event_tag: str
    event_name: str
    round_id: int
    round_number: int
