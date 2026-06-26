import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class GoalCreate(BaseModel):
    name: str = Field(..., max_length=120)
    emoji: str = Field(default="🎯", max_length=16)
    target_amount: int = Field(..., ge=0)
    current_amount: int = Field(default=0, ge=0)
    target_date: date | None = None


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    emoji: str | None = Field(default=None, max_length=16)
    target_amount: int | None = Field(default=None, ge=0)
    current_amount: int | None = Field(default=None, ge=0)
    target_date: date | None = None
    completed: bool | None = None  # mark complete


class GoalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    emoji: str
    target_amount: int
    current_amount: int
    target_date: date | None
    completed_at: datetime | None
