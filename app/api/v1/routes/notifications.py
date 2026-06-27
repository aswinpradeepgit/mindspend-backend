"""Internal notifications endpoint — triggered by the GitHub Actions cron.

Not user-facing: guarded by a shared secret (INTERNAL_CRON_SECRET) in the
X-Cron-Secret header, NOT a user JWT. Runs the daily targeting/send pass.
"""

import hmac

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import get_db
from app.services.notifications.runner import run_notifications

router = APIRouter()
settings = get_settings()


def _require_cron_secret(x_cron_secret: str = Header(default="")) -> None:
    expected = settings.INTERNAL_CRON_SECRET
    # Constant-time compare; refuse if no secret is configured server-side.
    if not expected or not hmac.compare_digest(x_cron_secret, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing cron secret")


@router.post("/run-notifications", dependencies=[Depends(_require_cron_secret)])
async def run_notifications_endpoint(db: AsyncSession = Depends(get_db)) -> dict:
    """Run the daily notification pass. Returns a summary of what was sent."""
    return await run_notifications(db)
