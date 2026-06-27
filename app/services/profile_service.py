"""Profile assembly + the authoritative expense-create flow.

Keeps the gamification side effects (XP, streak, level, badges) in one place so
every write path stays consistent and server-controlled.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.badge import Badge
from app.models.custom_category import CustomCategory
from app.models.expense import Expense
from app.models.profile import Profile
from app.schemas.custom_category import CustomCategoryOut
from app.schemas.expense import ExpenseCreate, ExpenseCreateResult, ExpenseOut
from app.schemas.profile import BadgeOut, ProfileOut
from app.services.badges import evaluate_badges
from app.services.gamification import calculate_xp, update_streak
from app.services.levels import level_from_xp
from app.services.nl_parse import BUILTIN_CATEGORIES


async def get_category_labels(db: AsyncSession, user_id: uuid.UUID) -> dict[str, str]:
    """Map every category id (built-in + the user's custom UUIDs) → its label,
    so AI features show names instead of raw ids."""
    labels = {c["id"]: c["label"] for c in BUILTIN_CATEGORIES}
    rows = (
        await db.execute(select(CustomCategory).where(CustomCategory.user_id == user_id))
    ).scalars().all()
    for c in rows:
        labels[str(c.id)] = c.label
    return labels


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> Profile:
    profile = await db.get(Profile, user_id)
    if profile is None:
        # Should exist via the signup trigger; create defensively.
        profile = Profile(id=user_id)
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
    return profile


async def build_profile_out(db: AsyncSession, user_id: uuid.UUID) -> ProfileOut:
    profile = await get_profile(db, user_id)
    badges = (
        await db.execute(select(Badge).where(Badge.user_id == user_id))
    ).scalars().all()
    cats = (
        await db.execute(
            select(CustomCategory).where(CustomCategory.user_id == user_id)
        )
    ).scalars().all()

    return ProfileOut(
        id=profile.id,
        name=profile.name,
        currency=profile.currency,
        monthly_budget=profile.monthly_budget,
        xp=profile.xp,
        level=profile.level,
        streak_days=profile.streak_days,
        last_log_date=profile.last_log_date,
        badges=[BadgeOut.model_validate(b) for b in badges],
        custom_categories=[CustomCategoryOut.model_validate(c) for c in cats],
    )


async def create_expense_with_gamification(
    db: AsyncSession, user_id: uuid.UUID, payload: ExpenseCreate
) -> ExpenseCreateResult:
    profile = await get_profile(db, user_id)

    existing = (
        await db.execute(
            select(Expense)
            .where(Expense.user_id == user_id)
            .order_by(Expense.date.desc(), Expense.created_at.desc())
        )
    ).scalars().all()

    # 1. Streak (mirrors the frontend order: streak first, then XP).
    new_streak, new_last_log = update_streak(
        profile.last_log_date, profile.streak_days, payload.date
    )
    profile.streak_days = new_streak
    profile.last_log_date = new_last_log

    # 2. XP for this expense (uses the post-streak streak_days).
    xp_awarded = calculate_xp(payload, profile.streak_days, list(existing))

    expense = Expense(
        user_id=user_id,
        amount=payload.amount,
        category=payload.category,
        description=payload.description,
        date=payload.date,
        emotion=payload.emotion,
        intent=payload.intent,
        regret=payload.regret,
        would_spend_less=payload.would_spend_less,
        xp_awarded=xp_awarded,
    )
    db.add(expense)

    # 3. Apply XP + recompute level.
    profile.xp += xp_awarded
    profile.level = level_from_xp(profile.xp)

    # 4. Evaluate badges over the full set (new expense first) + updated profile.
    already = {
        b.badge_id
        for b in (
            await db.execute(select(Badge).where(Badge.user_id == user_id))
        ).scalars()
    }
    new_badges = evaluate_badges([expense, *existing], profile, already)
    for badge_id in new_badges:
        db.add(Badge(user_id=user_id, badge_id=badge_id))

    await db.commit()
    await db.refresh(expense)

    profile_out = await build_profile_out(db, user_id)
    return ExpenseCreateResult(
        expense=ExpenseOut.model_validate(expense),
        profile=profile_out,
        new_badges=new_badges,
    )


async def delete_expense(db: AsyncSession, user_id: uuid.UUID, expense_id: uuid.UUID) -> None:
    expense = await db.get(Expense, expense_id)
    if expense is None or expense.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Expense not found")
    await db.delete(expense)
    await db.commit()
