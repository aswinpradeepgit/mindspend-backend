"""Device tokens API — register/refresh and unregister FCM push tokens.

The Capacitor app calls POST /devices after it obtains an FCM registration
token (on login / token refresh), and DELETE on logout.
"""

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel
from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.security import CurrentUser, get_current_user
from app.models.device_token import DeviceToken

router = APIRouter()


class DeviceRegister(BaseModel):
    token: str
    platform: str = "android"


@router.post("", status_code=status.HTTP_204_NO_CONTENT)
async def register_device(
    payload: DeviceRegister,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Upsert this device's push token for the current user.

    Tokens are globally unique; if the same token reappears (e.g. a different
    user signs in on the device) it's reassigned to the current user and re-enabled.
    """
    stmt = (
        pg_insert(DeviceToken)
        .values(
            user_id=user.id,
            token=payload.token,
            platform=payload.platform,
            enabled=True,
        )
        .on_conflict_do_update(
            index_elements=["token"],
            set_={
                "user_id": user.id,
                "platform": payload.platform,
                "enabled": True,
                "updated_at": func.now(),
            },
        )
    )
    await db.execute(stmt)
    await db.commit()


@router.delete("/{token}", status_code=status.HTTP_204_NO_CONTENT)
async def unregister_device(
    token: str,
    user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Disable a token (e.g. on logout). Soft-disable, not delete; idempotent."""
    await db.execute(
        update(DeviceToken)
        .where(DeviceToken.token == token, DeviceToken.user_id == user.id)
        .values(enabled=False, updated_at=func.now())
    )
    await db.commit()
