"""Badge evaluators — ported from frontend lib/gamification/badges.ts.

The backend only stores unlocked badge ids; the frontend has the display
definitions (name/emoji/rarity). `evaluate_badges` returns newly-unlocked ids.

Event-driven badges (goal_complete, under_budget_month) are unlocked by their
own flows (e.g. completing a goal), not here.
"""

from collections.abc import Iterable
from datetime import date, timedelta

from app.models.expense import Expense
from app.models.profile import Profile


def _recent_regret_rate(expenses: list[Expense], count: int) -> float:
    recent = expenses[:count]
    if not recent:
        return 0.0
    return sum(1 for e in recent if e.regret is True) / len(recent)


def _weekly_regret_count(expenses: list[Expense]) -> int:
    week_ago = date.today() - timedelta(days=7)
    return sum(1 for e in expenses if e.date >= week_ago and e.regret is True)


def _unique(expenses: list[Expense], attr: str) -> int:
    return len({getattr(e, attr) for e in expenses if getattr(e, attr) is not None})


# id -> predicate(expenses_desc, profile) -> bool
EVALUATORS = {
    "first_expense": lambda e, p: len(e) >= 1,
    "streak_3": lambda e, p: p.streak_days >= 3,
    "streak_7": lambda e, p: p.streak_days >= 7,
    "streak_30": lambda e, p: p.streak_days >= 30,
    "mindful_spender": lambda e, p: len(e) >= 30 and _recent_regret_rate(e, 30) < 0.1,
    "no_regret_week": lambda e, p: len(e) >= 3 and _weekly_regret_count(e) == 0,
    "century_expenses": lambda e, p: len(e) >= 100,
    "emotional_awareness": lambda e, p: _unique(e, "emotion") >= 6,
    "variety_spender": lambda e, p: _unique(e, "category") >= 8,
}


def evaluate_badges(
    expenses_desc: list[Expense],
    profile: Profile,
    already_unlocked: Iterable[str],
) -> list[str]:
    unlocked = set(already_unlocked)
    newly: list[str] = []
    for badge_id, predicate in EVALUATORS.items():
        if badge_id in unlocked:
            continue
        if predicate(expenses_desc, profile):
            newly.append(badge_id)
    return newly
