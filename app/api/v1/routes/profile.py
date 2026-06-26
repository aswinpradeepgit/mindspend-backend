"""Profile API — read the full profile (XP, level, streak, badges, categories)
and update editable fields (name, currency, monthly budget)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.schemas.profile import ProfileOut, ProfileUpdate
from app.services.profile_service import build_profile_out, get_profile

router = APIRouter()


@router.get("", response_model=ProfileOut)
async def read_profile(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    return await build_profile_out(db, user.id)


@router.patch("", response_model=ProfileOut)
async def update_profile(
    payload: ProfileUpdate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ProfileOut:
    profile = await get_profile(db, user.id)
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(profile, field, value)
    await db.commit()
    return await build_profile_out(db, user.id)
