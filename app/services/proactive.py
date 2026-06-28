"""Proactive / predictive insights — deterministic, LLM-free, fast.

Bundles four features:
  * forecast            — month-end spend projection vs budget
  * budget_suggestions  — suggested per-category budgets from history
  * recurring           — repeated same-amount charges (subscriptions/EMIs)
  * goal_motivation     — motivational goal progress (framing > raw numbers)

All amounts are integer minor units (paise).
"""

import re
from collections import defaultdict
from datetime import date, timedelta

from app.models.expense import Expense
from app.models.goal import Goal
from app.models.profile import Profile

_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def _fmt(m: int, c: str) -> str:
    return f"{_SYMBOLS.get(c, c + ' ')}{round(m / 100):,}"


def _days_in_month(d: date) -> int:
    nm = (d.replace(day=28) + timedelta(days=4)).replace(day=1)
    return (nm - d.replace(day=1)).days


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


# ── Forecast ─────────────────────────────────────────────────────────────────
def forecast(expenses: list[Expense], profile: Profile, today: date) -> dict | None:
    cur = profile.currency
    ms = today.replace(day=1)
    month_exp = sum(e.amount for e in expenses if ms <= e.date <= today)
    elapsed = (today - ms).days + 1
    dim = _days_in_month(today)
    if elapsed < 2 or month_exp == 0:
        return None

    projected = round(month_exp * dim / elapsed)
    budget = profile.monthly_budget
    out = {
        "projected_minor": projected,
        "spent_minor": month_exp,
        "budget_minor": budget,
        "days_left": dim - elapsed,
    }
    if budget and budget > 0:
        if projected <= budget * 0.9:
            out["status"] = "under"
            out["headline"] = "On track 🎯"
            out["detail"] = (
                f"At this pace you'll spend about {_fmt(projected, cur)} this month — "
                f"comfortably under your {_fmt(budget, cur)} budget."
            )
        elif projected <= budget:
            out["status"] = "close"
            out["headline"] = "Cutting it close ⚠️"
            out["detail"] = (
                f"At this pace you'll spend about {_fmt(projected, cur)} — right up against "
                f"your {_fmt(budget, cur)} budget."
            )
        else:
            out["status"] = "over"
            out["headline"] = "Heading over budget 🚨"
            out["detail"] = (
                f"At this pace you'll spend about {_fmt(projected, cur)} — about "
                f"{_fmt(projected - budget, cur)} over your {_fmt(budget, cur)} budget."
            )
    else:
        out["status"] = "no_budget"
        out["headline"] = "Month-end forecast"
        out["detail"] = (
            f"At this pace you'll spend about {_fmt(projected, cur)} this month. "
            "Set a monthly budget to track against it."
        )
    return out


# ── Budget suggestions ───────────────────────────────────────────────────────
def budget_suggestions(
    expenses: list[Expense], profile: Profile, labels: dict[str, str], today: date
) -> list[dict]:
    if not expenses:
        return []
    months = {(e.date.year, e.date.month) for e in expenses}
    nmonths = max(1, len(months))
    cat_total: dict[str, int] = defaultdict(int)
    for e in expenses:
        cat_total[e.category] += e.amount

    out = []
    for c, total in cat_total.items():
        avg = total / nmonths
        if avg < 20000:  # skip categories under ~₹200/mo
            continue
        suggested = round(avg / 10000) * 10000  # nearest ₹100
        out.append({
            "category": c,
            "label": labels.get(c, c),
            "monthly_avg_minor": round(avg),
            "suggested_minor": max(suggested, 10000),
        })
    out.sort(key=lambda x: x["monthly_avg_minor"], reverse=True)
    return out[:6]


# ── Recurring / subscriptions ────────────────────────────────────────────────
def recurring(expenses: list[Expense], labels: dict[str, str]) -> list[dict]:
    groups: dict[tuple, list[Expense]] = defaultdict(list)
    for e in expenses:
        name = _norm(e.description) or labels.get(e.category, e.category)
        groups[(name, e.amount)].append(e)

    out = []
    for (name, amt), items in groups.items():
        months = {(e.date.year, e.date.month) for e in items}
        if len(months) >= 2 and amt >= 5000:  # ≥2 distinct months, ≥₹50
            out.append({
                "name": name.title(),
                "amount_minor": amt,
                "months": len(months),
                "last_date": max(e.date for e in items).isoformat(),
            })
    out.sort(key=lambda x: (x["months"], x["amount_minor"]), reverse=True)
    return out[:6]


# ── Goal motivation ──────────────────────────────────────────────────────────
def goal_motivation(goals: list[Goal], profile: Profile, today: date) -> list[dict]:
    cur = profile.currency
    out = []
    for g in goals:
        if g.completed_at is not None or g.target_amount <= 0:
            continue
        pct = min(1.0, g.current_amount / g.target_amount)
        remaining = max(0, g.target_amount - g.current_amount)
        item = {
            "name": g.name,
            "emoji": g.emoji,
            "percent": round(pct * 100),
            "remaining_minor": remaining,
        }
        if pct >= 1.0:
            item["message"] = f"You did it! {g.name} is fully funded 🎉"
        elif pct >= 0.85:
            item["message"] = f"So close — just {_fmt(remaining, cur)} more and {g.name} is yours! 🔥"
        elif g.target_date:
            days_left = (g.target_date - today).days
            when = g.target_date.strftime("%b %Y")
            pct_txt = round(pct * 100)
            if days_left <= 0:
                item["message"] = (
                    f"{g.name}'s date has passed — {_fmt(remaining, cur)} to go. "
                    "Reset the date and keep going 💪"
                )
            elif days_left < 14:
                item["message"] = (
                    f"{pct_txt}% there — just {_fmt(remaining, cur)} left before {when}. Home stretch! 🏁"
                )
            elif days_left < 45:
                per_week = remaining / (days_left / 7)
                item["message"] = (
                    f"{pct_txt}% there! Save about {_fmt(round(per_week), cur)}/week "
                    f"to reach {g.name} by {when} 🎯"
                )
            else:
                per_month = remaining / (days_left / 30)
                item["message"] = (
                    f"{pct_txt}% there! Save about {_fmt(round(per_month), cur)}/month "
                    f"to reach {g.name} by {when} 🎯"
                )
        else:
            item["message"] = (
                f"{round(pct * 100)}% of the way to {g.name} — {_fmt(remaining, cur)} left. "
                "Every save counts 💜"
            )
        out.append(item)
    out.sort(key=lambda x: x["percent"], reverse=True)
    return out[:3]


# ── Combined ─────────────────────────────────────────────────────────────────
def proactive_insights(
    expenses: list[Expense],
    goals: list[Goal],
    profile: Profile,
    labels: dict[str, str] | None = None,
    today: date | None = None,
) -> dict:
    today = today or date.today()
    labels = labels or {}
    return {
        "forecast": forecast(expenses, profile, today),
        "budget_suggestions": budget_suggestions(expenses, profile, labels, today),
        "recurring": recurring(expenses, labels),
        "goals": goal_motivation(goals, profile, today),
    }
