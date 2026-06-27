"""Insights API — 'Explain my month' narrative, cached per user."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.ai_insight import AiInsight
from app.models.expense import Expense
from app.services.insights_ai import explain
from app.services.profile_service import get_profile

router = APIRouter()
settings = get_settings()

_CACHE_KEY = "explain_monthly"


@router.get("/explain")
async def explain_month(
    refresh: bool = False,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)

    if not refresh:
        cached = (
            await db.execute(
                select(AiInsight).where(
                    AiInsight.user_id == user.id, AiInsight.period == _CACHE_KEY
                )
            )
        ).scalar_one_or_none()
        if cached and cached.expires_at and cached.expires_at > now:
            return {**cached.payload, "generated_at": cached.generated_at.isoformat(), "cached": True}

    profile = await get_profile(db, user.id)
    expenses = (
        await db.execute(select(Expense).where(Expense.user_id == user.id))
    ).scalars().all()
    payload = explain(list(expenses), profile, "monthly")

    await db.execute(
        delete(AiInsight).where(AiInsight.user_id == user.id, AiInsight.period == _CACHE_KEY)
    )
    db.add(
        AiInsight(
            user_id=user.id,
            period=_CACHE_KEY,
            payload=payload,
            expires_at=now + timedelta(hours=settings.COACH_CACHE_HOURS),
        )
    )
    await db.commit()
    return {**payload, "generated_at": now.isoformat(), "cached": False}
