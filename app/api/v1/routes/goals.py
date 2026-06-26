"""Savings goals API — list, create, update, delete.

Completing a goal (PATCH completed=true) awards +100 XP server-side and
unlocks the goal_complete badge — once per goal.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.badge import Badge
from app.models.goal import Goal
from app.schemas.goal import GoalCreate, GoalOut, GoalUpdate
from app.services.levels import level_from_xp
from app.services.profile_service import get_profile

router = APIRouter()


async def _get_owned(db: AsyncSession, user_id: uuid.UUID, goal_id: uuid.UUID) -> Goal:
    goal = await db.get(Goal, goal_id)
    if goal is None or goal.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Goal not found")
    return goal


@router.get("", response_model=list[GoalOut])
async def list_goals(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[Goal]:
    result = await db.execute(
        select(Goal).where(Goal.user_id == user.id).order_by(Goal.created_at.desc())
    )
    return list(result.scalars().all())


@router.post("", response_model=GoalOut, status_code=status.HTTP_201_CREATED)
async def create_goal(
    payload: GoalCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Goal:
    goal = Goal(user_id=user.id, **payload.model_dump())
    db.add(goal)
    await db.commit()
    await db.refresh(goal)
    return goal


@router.patch("/{goal_id}", response_model=GoalOut)
async def update_goal(
    goal_id: uuid.UUID,
    payload: GoalUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Goal:
    goal = await _get_owned(db, user.id, goal_id)
    data = payload.model_dump(exclude_unset=True)
    completing = data.pop("completed", None)

    for field, value in data.items():
        setattr(goal, field, value)

    if completing and goal.completed_at is None:
        goal.completed_at = datetime.now(timezone.utc)
        # Award +100 XP and unlock the goal badge (server-authoritative).
        profile = await get_profile(db, user.id)
        profile.xp += 100
        profile.level = level_from_xp(profile.xp)
        exists = await db.get(Badge, (user.id, "goal_complete"))
        if exists is None:
            db.add(Badge(user_id=user.id, badge_id="goal_complete"))

    await db.commit()
    await db.refresh(goal)
    return goal


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_goal(
    goal_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    goal = await _get_owned(db, user.id, goal_id)
    await db.delete(goal)
    await db.commit()
