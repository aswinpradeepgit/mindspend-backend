"""Pydantic request/response schemas for expenses.

These are the API contract — deliberately separate from the ORM model so the
wire format can evolve independently of the database.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ExpenseCreate(BaseModel):
    amount: int = Field(..., ge=0, description="Amount in minor units (paise/cents)")
    category: str = Field(..., max_length=64)
    description: str = Field(default="", max_length=2000)
    date: date
    emotion: str | None = Field(default=None, max_length=32)
    intent: str | None = Field(default=None, max_length=32)
    regret: bool | None = None
    would_spend_less: bool | None = None


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    amount: int
    category: str
    description: str
    date: date
    emotion: str | None
    intent: str | None
    regret: bool | None
    would_spend_less: bool | None
    xp_awarded: int
    created_at: datetime


# Returned by POST /expenses — the new expense plus the server-computed
# profile state and any badges that just unlocked. Avoids extra round-trips.
class ExpenseCreateResult(BaseModel):
    expense: ExpenseOut
    profile: "ProfileOut"
    new_badges: list[str]


from app.schemas.profile import ProfileOut  # noqa: E402  (avoid circular import at top)

ExpenseCreateResult.model_rebuild()
