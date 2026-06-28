"""Commitments API — EMIs & subscriptions: list, create, delete, insights."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.commitment import Commitment
from app.services.commitments_ai import commitments_insights
from app.services.profile_service import get_profile

router = APIRouter()


class CommitmentIn(BaseModel):
    type: str  # 'emi' | 'subscription'
    name: str
    amount: int  # minor units, per cycle
    cycle: str = "monthly"
    due_day: int | None = None
    months_left: int | None = None
    icon: str = ""


class CommitmentOut(CommitmentIn):
    id: uuid.UUID
    active: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[CommitmentOut])
async def list_commitments(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Commitment]:
    rows = await db.execute(
        select(Commitment).where(Commitment.user_id == user.id).order_by(Commitment.created_at)
    )
    return list(rows.scalars().all())


@router.post("", response_model=CommitmentOut, status_code=status.HTTP_201_CREATED)
async def create_commitment(
    payload: CommitmentIn,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Commitment:
    if payload.type not in ("emi", "subscription"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "type must be emi or subscription")
    c = Commitment(user_id=user.id, **payload.model_dump())
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


@router.delete("/{commitment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_commitment(
    commitment_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    c = await db.get(Commitment, commitment_id)
    if c is None or c.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Commitment not found")
    await db.delete(c)
    await db.commit()


@router.get("/insights")
async def insights(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    profile = await get_profile(db, user.id)
    rows = (
        await db.execute(select(Commitment).where(Commitment.user_id == user.id))
    ).scalars().all()
    return commitments_insights(list(rows), profile)
