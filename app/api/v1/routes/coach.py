"""AI Coach API — returns personalized coaching, cached per user+period."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.ai_insight import AiInsight
from app.models.expense import Expense
from app.services.coach_ai import generate_coach
from app.services.profile_service import get_profile

router = APIRouter()
settings = get_settings()


@router.get("")
async def get_coach(
    period: str = "weekly",
    refresh: bool = False,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    period = period if period in ("weekly", "monthly") else "weekly"
    now = datetime.now(timezone.utc)

    # 1. Serve a fresh cached insight unless a refresh was requested.
    if not refresh:
        cached = (
            await db.execute(
                select(AiInsight).where(
                    AiInsight.user_id == user.id, AiInsight.period == period
                )
            )
        ).scalar_one_or_none()
        if cached and cached.expires_at and cached.expires_at > now:
            return {**cached.payload, "generated_at": cached.generated_at.isoformat(), "cached": True}

    # 2. Generate (Gemini, or rules fallback).
    profile = await get_profile(db, user.id)
    expenses = (
        await db.execute(select(Expense).where(Expense.user_id == user.id))
    ).scalars().all()
    payload = generate_coach(list(expenses), profile, period)

    # 3. Replace the cache for this period.
    await db.execute(
        delete(AiInsight).where(AiInsight.user_id == user.id, AiInsight.period == period)
    )
    db.add(
        AiInsight(
            user_id=user.id,
            period=period,
            payload=payload,
            expires_at=now + timedelta(hours=settings.COACH_CACHE_HOURS),
        )
    )
    await db.commit()

    return {**payload, "generated_at": now.isoformat(), "cached": False}
