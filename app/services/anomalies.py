"""Spending anomaly detection — deterministic, LLM-free, fast.

Compares a recent window (last 7 days) to a baseline (prior ~4 weeks) across
several dimensions and surfaces the most notable anomalies. Leans into the app's
emotional angle (stress-spending, regret surges) — not just raw amounts.

All amounts are integer minor units (paise). Returns a ranked list of dicts:
  {type, severity: 'alert'|'warn'|'info', emoji, title, detail}
"""

from collections import defaultdict
from datetime import date, timedelta

from app.models.expense import Expense
from app.models.profile import Profile

_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}
_NEGATIVE_EMOTIONS = {"anxious", "guilty", "impulsive", "stressed"}
_SEV_ORDER = {"alert": 3, "warn": 2, "info": 1}


def _fmt(minor: int, currency: str) -> str:
    return f"{_SYMBOLS.get(currency, currency + ' ')}{round(minor / 100):,}"


def detect_anomalies(
    expenses: list[Expense],
    profile: Profile,
    category_labels: dict[str, str] | None = None,
    today: date | None = None,
) -> list[dict]:
    today = today or date.today()
    cur = profile.currency
    labels = category_labels or {}

    def fmt(m: int) -> str:
        return _fmt(m, cur)

    recent_start = today - timedelta(days=6)  # last 7 days incl. today
    base_start = today - timedelta(days=34)  # prior 4 weeks
    base_end = today - timedelta(days=7)

    recent = [e for e in expenses if recent_start <= e.date <= today]
    base = [e for e in expenses if base_start <= e.date <= base_end]
    total_recent = sum(e.amount for e in recent)
    total_base = sum(e.amount for e in base)

    out: list[dict] = []

    # 1. Category spikes — this week vs the per-week baseline average.
    rec_cat: dict[str, int] = defaultdict(int)
    base_cat: dict[str, int] = defaultdict(int)
    for e in recent:
        rec_cat[e.category] += e.amount
    for e in base:
        base_cat[e.category] += e.amount
    spikes = []
    for c, amt in rec_cat.items():
        weekly_base = base_cat.get(c, 0) / 4.0
        # Needs a real baseline, a 2x+ jump, AND a material absolute delta (>=₹300)
        # so we never flag trivial "₹5 → ₹50" noise.
        if weekly_base >= 5000 and amt >= 2 * weekly_base and (amt - weekly_base) >= 30000:
            spikes.append((amt / weekly_base, c, amt, weekly_base))
    spikes.sort(reverse=True)
    for ratio, c, amt, weekly_base in spikes[:2]:
        name = labels.get(c, c)
        out.append({
            "type": "category_spike",
            "severity": "warn" if ratio >= 3 else "info",
            "emoji": "📈",
            "title": f"{ratio:.1f}× your usual {name}",
            "detail": f"You've spent {fmt(amt)} on {name} this week — vs your usual {fmt(int(weekly_base))}/week.",
        })

    # 2. Emotional surge — share of spend made while feeling low.
    if total_recent >= 50000 and total_base > 0:
        neg_rec = sum(e.amount for e in recent if e.emotion in _NEGATIVE_EMOTIONS)
        neg_base = sum(e.amount for e in base if e.emotion in _NEGATIVE_EMOTIONS)
        rec_share = neg_rec / total_recent
        base_share = neg_base / total_base
        if rec_share >= 0.4 and rec_share >= base_share + 0.2:
            out.append({
                "type": "emotional_surge",
                "severity": "warn",
                "emoji": "😰",
                "title": "More stress-spending than usual",
                "detail": (
                    f"{round(rec_share * 100)}% of this week's spend happened while feeling low "
                    f"— up from your usual {round(base_share * 100)}%. A 10-minute pause could help."
                ),
            })

    # 3. Regret surge — regret rate this week vs baseline.
    rec_reg = [e for e in recent if e.regret is not None]
    if len(rec_reg) >= 3:
        reg_rate = sum(1 for e in rec_reg if e.regret) / len(rec_reg)
        base_reg = [e for e in base if e.regret is not None]
        base_rate = (sum(1 for e in base_reg if e.regret) / len(base_reg)) if base_reg else 0.0
        if reg_rate >= 0.5 and reg_rate >= base_rate + 0.25:
            out.append({
                "type": "regret_surge",
                "severity": "warn",
                "emoji": "💭",
                "title": "Regretting more buys than usual",
                "detail": f"You've regretted {round(reg_rate * 100)}% of this week's purchases. Worth a reflection on what's driving them.",
            })

    # 4. Big single expense — relative to your typical (median) expense.
    amts = sorted(e.amount for e in (base + recent))
    if recent and amts:
        typical = amts[len(amts) // 2]  # median
        biggest = max(recent, key=lambda e: e.amount)
        if typical > 0 and biggest.amount >= 3 * typical and biggest.amount >= 50000:
            name = labels.get(biggest.category, biggest.category)
            out.append({
                "type": "big_expense",
                "severity": "info",
                "emoji": "💥",
                "title": f"Big one: {fmt(biggest.amount)} on {name}",
                "detail": f"About {round(biggest.amount / typical)}× your typical expense — just checking it was intentional!",
            })

    # 5. Budget pace — projected month-end spend vs the monthly budget.
    if profile.monthly_budget and profile.monthly_budget > 0:
        month_start = today.replace(day=1)
        month_exp = sum(e.amount for e in expenses if month_start <= e.date <= today)
        days_elapsed = (today - month_start).days + 1
        next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)
        days_in_month = (next_month - month_start).days
        if days_elapsed >= 3 and month_exp > 0:
            projected = month_exp * days_in_month / days_elapsed
            if projected > profile.monthly_budget * 1.05:
                over = projected - profile.monthly_budget
                out.append({
                    "type": "budget_pace",
                    "severity": "alert",
                    "emoji": "🚨",
                    "title": "On track to exceed your budget",
                    "detail": (
                        f"At this pace you'll spend ~{fmt(int(projected))} this month — about "
                        f"{fmt(int(over))} over your {fmt(profile.monthly_budget)} budget."
                    ),
                })

    out.sort(key=lambda a: _SEV_ORDER[a["severity"]], reverse=True)
    return out[:4]
