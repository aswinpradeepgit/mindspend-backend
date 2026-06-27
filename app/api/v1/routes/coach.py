"""AI Coach API — returns personalized coaching, cached per user+period."""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.ai_insight import AiInsight
from app.models.expense import Expense
from app.services.coach_ai import chat, generate_coach
from app.services.llm import has_llm
from app.services.profile_service import get_category_labels, get_profile

router = APIRouter()
settings = get_settings()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[ChatMessage] = []


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
    labels = await get_category_labels(db, user.id)
    expenses = (
        await db.execute(select(Expense).where(Expense.user_id == user.id))
    ).scalars().all()
    payload = generate_coach(list(expenses), profile, period, labels)

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


@router.post("/chat")
async def coach_chat(
    payload: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """One conversational turn with the coach, grounded in the user's data."""
    message = payload.message.strip()
    if not message:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty message")
    if not has_llm():
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AI chat not available")

    profile = await get_profile(db, user.id)
    labels = await get_category_labels(db, user.id)
    expenses = (
        await db.execute(select(Expense).where(Expense.user_id == user.id))
    ).scalars().all()

    try:
        reply = chat(
            list(expenses),
            profile,
            message,
            [h.model_dump() for h in payload.history],
            labels,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Coach chat failed (%s)", exc)
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Coach is busy — try again in a moment")

    return {"reply": reply}
