"""Custom categories API — list, create, delete."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.custom_category import CustomCategory
from app.schemas.custom_category import CustomCategoryCreate, CustomCategoryOut

router = APIRouter()


@router.get("", response_model=list[CustomCategoryOut])
async def list_categories(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[CustomCategory]:
    result = await db.execute(
        select(CustomCategory).where(CustomCategory.user_id == user.id)
    )
    return list(result.scalars().all())


@router.post("", response_model=CustomCategoryOut, status_code=status.HTTP_201_CREATED)
async def create_category(
    payload: CustomCategoryCreate,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CustomCategory:
    cat = CustomCategory(user_id=user.id, **payload.model_dump())
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    cat = await db.get(CustomCategory, category_id)
    if cat is None or cat.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Category not found")
    await db.delete(cat)
    await db.commit()
