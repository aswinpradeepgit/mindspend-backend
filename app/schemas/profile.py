import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.custom_category import CustomCategoryOut


class BadgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    badge_id: str
    unlocked_at: datetime


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    currency: str | None = Field(default=None, max_length=8)
    monthly_budget: int | None = Field(default=None, ge=0)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    currency: str
    monthly_budget: int | None
    xp: int
    level: int
    streak_days: int
    last_log_date: date | None = None
    badges: list[BadgeOut] = []
    custom_categories: list[CustomCategoryOut] = []
