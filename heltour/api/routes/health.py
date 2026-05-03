from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthDTO(BaseModel):
    ok: bool


@router.get("/health", response_model=HealthDTO)
def health() -> HealthDTO:
    return HealthDTO(ok=True)
