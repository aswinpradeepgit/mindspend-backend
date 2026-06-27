"""Decide whether (and what) to nudge a user. v1 types: streak_rescue, nightly_wrapup.

Pure functions over already-loaded data so they're easy to reason about/test.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from app.models.expense import Expense
from app.models.profile import Profile

_CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def fmt_money(minor: int, currency: str) -> str:
    """Format integer minor units as a display string, e.g. 54000 → '₹540'."""
    sym = _CURRENCY_SYMBOLS.get(currency, currency + " ")
    return f"{sym}{minor // 100:,}"


@dataclass
class NotificationPlan:
    type: str  # 'streak_rescue' | 'nightly_wrapup'
    ctx: dict = field(default_factory=dict)


def plan_notification(
    profile: Profile, todays_expenses: list[Expense], today: date
) -> NotificationPlan | None:
    """Pick the one notification (if any) this user should get today.

    ``todays_expenses`` must already be filtered to ``today``.
    """
    name = (profile.name or "there").split()[0] if profile.name else "there"
    last = profile.last_log_date

    # Logged today → wrap up / celebrate the day.
    if last == today:
        total = sum(e.amount for e in todays_expenses)
        emo_counts: dict[str, int] = {}
        for e in todays_expenses:
            if e.emotion:
                emo_counts[e.emotion] = emo_counts.get(e.emotion, 0) + 1
        top_emotion = max(emo_counts, key=emo_counts.get) if emo_counts else None
        return NotificationPlan(
            "nightly_wrapup",
            {
                "name": name,
                "count": len(todays_expenses),
                "total": fmt_money(total, profile.currency),
                "top_emotion": top_emotion,
                "streak_days": profile.streak_days,
            },
        )

    # Active streak, logged yesterday but not yet today → rescue it this evening.
    if profile.streak_days >= 1 and last == today - timedelta(days=1):
        return NotificationPlan(
            "streak_rescue",
            {"name": name, "streak_days": profile.streak_days},
        )

    return None
