"""Expenses API — list, create (with server-side gamification), delete.

Every query is scoped to the authenticated user's id (from the verified JWT).
"""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.custom_category import CustomCategory
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseCreateResult, ExpenseOut
from app.services.nl_parse import (
    BUILTIN_CATEGORIES,
    is_rate_limit_error,
    parse_expense,
    regex_parse_expense,
)

logger = logging.getLogger(__name__)
from app.services.profile_service import (
    create_expense_with_gamification,
    delete_expense as delete_expense_service,
)

router = APIRouter()
settings = get_settings()


class ParseRequest(BaseModel):
    text: str


class ParseResult(BaseModel):
    amount: int
    category: str
    description: str
    emotion: str | None
    intent: str | None
    # False when the LLM was unavailable (no key / quota / error) and the result
    # came from the regex fallback — the client uses this to soften its message.
    ai_used: bool = True


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 500,
    offset: int = 0,
) -> list[Expense]:
    result = await db.execute(
        select(Expense)
        .where(Expense.user_id == user.id)
        .order_by(Expense.date.desc(), Expense.created_at.desc())
        .limit(min(limit, 1000))
        .offset(offset)
    )
    return list(result.scalars().all())


@router.post("", response_model=ExpenseCreateResult, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExpenseCreateResult:
    return await create_expense_with_gamification(db, user.id, payload)


@router.post("/parse", response_model=ParseResult)
async def parse_natural_language(
    payload: ParseRequest,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ParseResult:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Empty text")

    custom = (
        await db.execute(select(CustomCategory).where(CustomCategory.user_id == user.id))
    ).scalars().all()
    categories = BUILTIN_CATEGORIES + [{"id": str(c.id), "label": c.label} for c in custom]

    # Try the LLM; on any failure (no key, quota/429, parse error) fall back to a
    # regex parse so the user still gets a pre-filled form instead of a dead end.
    if settings.GEMINI_API_KEY:
        try:
            return ParseResult(ai_used=True, **parse_expense(text, categories))
        except Exception as exc:
            if is_rate_limit_error(exc):
                logger.warning("NL parse: Gemini rate-limited (429), using regex fallback")
            else:
                logger.warning("NL parse: Gemini failed (%s), using regex fallback", exc)

    return ParseResult(ai_used=False, **regex_parse_expense(text, categories))


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_expense_service(db, user.id, expense_id)
