"""Server-side gamification rules.

XP is computed on the server so the client can never inflate it. This is a
deliberately small starting point; the full engine (levels, badges, streaks,
quests) — ported from the frontend's lib/gamification — will live here as the
app evolves.
"""

from app.schemas.expense import ExpenseCreate

XP_LOG_EXPENSE = 10
XP_COMPLETE_CHECKIN = 15
XP_NO_REGRET = 5


def calculate_expense_xp(expense: ExpenseCreate) -> int:
    xp = XP_LOG_EXPENSE
    if expense.emotion and expense.intent:
        xp += XP_COMPLETE_CHECKIN
    if expense.regret is False:
        xp += XP_NO_REGRET
    return xp
