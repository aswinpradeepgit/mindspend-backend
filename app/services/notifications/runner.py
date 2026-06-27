"""Daily notification run: pick eligible users → plan → write copy → send → log.

Called by the secret-protected /internal/run-notifications endpoint (triggered by
the GitHub Actions cron). Designed to never raise on a single user/token failure.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.device_token import DeviceToken
from app.models.expense import Expense
from app.models.notification_log import NotificationLog
from app.models.profile import Profile
from app.services.notifications import fcm
from app.services.notifications.copy import generate_copy
from app.services.notifications.targeting import plan_notification

settings = get_settings()
logger = logging.getLogger(__name__)

# Frequency cap: skip a user who already got a push within this many hours.
_CAP_HOURS = 18


def _app_today():
    return (
        datetime.now(timezone.utc) + timedelta(minutes=settings.APP_TZ_OFFSET_MINUTES)
    ).date()


async def run_notifications(db: AsyncSession) -> dict:
    today = _app_today()
    summary = {
        "date": today.isoformat(),
        "candidates": 0,
        "sent": 0,
        "skipped_capped": 0,
        "no_plan": 0,
        "failed": 0,
        "tokens_disabled": 0,
    }

    if not settings.NOTIFICATIONS_ENABLED:
        summary["disabled"] = True
        return summary

    # Group enabled device tokens by user.
    tokens = (
        await db.execute(select(DeviceToken).where(DeviceToken.enabled.is_(True)))
    ).scalars().all()
    tokens_by_user: dict = {}
    for t in tokens:
        tokens_by_user.setdefault(t.user_id, []).append(t)

    cap_cutoff = datetime.now(timezone.utc) - timedelta(hours=_CAP_HOURS)

    for user_id, user_tokens in tokens_by_user.items():
        summary["candidates"] += 1

        # Frequency cap — at most one push per user per ~day.
        recent = (
            await db.execute(
                select(NotificationLog.id)
                .where(
                    NotificationLog.user_id == user_id,
                    NotificationLog.sent_at >= cap_cutoff,
                )
                .limit(1)
            )
        ).first()
        if recent:
            summary["skipped_capped"] += 1
            continue

        profile = await db.get(Profile, user_id)
        if profile is None:
            continue
        todays = (
            await db.execute(
                select(Expense).where(
                    Expense.user_id == user_id, Expense.date == today
                )
            )
        ).scalars().all()

        plan = plan_notification(profile, list(todays), today)
        if plan is None:
            summary["no_plan"] += 1
            continue

        copy = generate_copy(plan)
        sent_any = False
        for t in user_tokens:
            res = fcm.send_push(t.token, copy["title"], copy["body"], data={"type": plan.type})
            if res.ok:
                sent_any = True
            elif res.invalid_token:
                t.enabled = False
                summary["tokens_disabled"] += 1
            else:
                logger.warning("FCM send failed for user %s: %s", user_id, res.error)

        if sent_any:
            db.add(
                NotificationLog(
                    user_id=user_id, type=plan.type, title=copy["title"], body=copy["body"]
                )
            )
            summary["sent"] += 1
        else:
            summary["failed"] += 1

    await db.commit()
    return summary
