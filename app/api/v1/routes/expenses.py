"""Expenses API — the first authenticated, DB-backed resource.

Every query is scoped to the authenticated user's id (from the verified JWT),
never from the request body. XP is computed server-side.
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseOut
from app.services.gamification import calculate_expense_xp

router = APIRouter()


@router.get("", response_model=list[ExpenseOut])
async def list_expenses(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[Expense]:
    result = await db.execute(
        select(Expense)
        .where(Expense.user_id == user.id)
        .order_by(Expense.date.desc(), Expense.created_at.desc())
        .limit(min(limit, 500))
        .offset(offset)
    )
    return list(result.scalars().all())


@router.post("", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(
    payload: ExpenseCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Expense:
    expense = Expense(
        user_id=user.id,
        amount=payload.amount,
        category=payload.category,
        description=payload.description,
        date=payload.date,
        emotion=payload.emotion,
        intent=payload.intent,
        regret=payload.regret,
        would_spend_less=payload.would_spend_less,
        xp_awarded=calculate_expense_xp(payload),
    )
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    return expense
