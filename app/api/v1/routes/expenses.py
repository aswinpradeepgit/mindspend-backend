"""Expenses API — list, create (with server-side gamification), delete.

Every query is scoped to the authenticated user's id (from the verified JWT).
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate, ExpenseCreateResult, ExpenseOut
from app.services.profile_service import (
    create_expense_with_gamification,
    delete_expense as delete_expense_service,
)

router = APIRouter()


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


@router.delete("/{expense_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_expense(
    expense_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await delete_expense_service(db, user.id, expense_id)
