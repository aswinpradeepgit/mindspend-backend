"""Server-authoritative gamification — XP, streak, level.

Ported from frontend lib/gamification/xp.ts + the store's updateStreak. The
server computes these so the client can never inflate XP/level/badges.
"""

import math
from datetime import date

from app.models.expense import Expense
from app.schemas.expense import ExpenseCreate


def update_streak(
    last_log_date: date | None, streak_days: int, today: date
) -> tuple[int, date]:
    """Return (new_streak_days, new_last_log_date)."""
    if last_log_date is None:
        return 1, today
    diff = (today - last_log_date).days
    if diff == 0:
        return streak_days, last_log_date  # same day, no change
    if diff == 1:
        return streak_days + 1, today
    return 1, today  # streak broken


def calculate_xp(
    payload: ExpenseCreate,
    streak_days: int,
    existing_expenses: list[Expense],
) -> int:
    """`streak_days` is the value AFTER the streak update (mirrors the frontend)."""
    xp = 10  # base for logging

    if payload.emotion and payload.intent:
        xp += 15
    if payload.regret is False:
        xp += 5

    used_categories = {e.category for e in existing_expenses}
    if payload.category not in used_categories:
        xp += 30

    streak_multiplier = min(1 + streak_days * 0.05, 3.0)
    xp += math.floor(20 * streak_multiplier)

    if streak_days > 0 and (streak_days + 1) % 7 == 0:
        xp += 50

    return xp
