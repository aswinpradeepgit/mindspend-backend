"""Insights over the user's EMIs + subscriptions.

Deterministic totals (always correct) + an optional LLM "audit" that spots
redundant/overlapping subscriptions and savings — with a static fallback.
All amounts are integer minor units (paise).
"""

import json
import logging

from app.models.commitment import Commitment
from app.models.profile import Profile
from app.services.llm import complete_json, has_llm

logger = logging.getLogger(__name__)

_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def _fmt(m: int, c: str) -> str:
    return f"{_SYMBOLS.get(c, c + ' ')}{round(m / 100):,}"


def monthly_equiv(amount: int, cycle: str) -> float:
    if cycle == "yearly":
        return amount / 12
    if cycle == "weekly":
        return amount * 52 / 12
    return float(amount)


_AUDIT_PROMPT = """You are MindSpend's money coach. The user has these recurring \
commitments (monthly-equivalent amounts in {symbol}):
{items}

Give 1-3 short, specific, friendly suggestions to save money: spot overlapping or \
redundant subscriptions (e.g. two music services or two video services), flag \
pricey ones worth reviewing, and mention the total yearly subscription cost if \
notable. Always format money as {symbol} + amount. Return ONLY JSON:
{{"suggestions": ["...", "..."]}}"""


def _audit(commitments: list[Commitment], cur: str, annual_subs: int) -> list[str]:
    subs = [c for c in commitments if c.type == "subscription"]
    if has_llm() and commitments:
        try:
            items = "\n".join(
                f"- {c.type}: {c.name} ({_fmt(round(monthly_equiv(c.amount, c.cycle)), cur)}/mo)"
                for c in commitments
            )
            data = complete_json(_AUDIT_PROMPT.format(symbol=_SYMBOLS.get(cur, cur), items=items))
            sug = [str(s).strip() for s in data.get("suggestions", []) if str(s).strip()]
            if sug:
                return sug[:3]
        except Exception as exc:  # noqa: BLE001
            logger.warning("commitments audit LLM failed (%s)", exc)
    # Fallback
    out = []
    if subs:
        out.append(f"You're spending about {_fmt(annual_subs, cur)}/year on subscriptions — cancel any you rarely use.")
    if len(subs) >= 4:
        out.append(f"That's {len(subs)} subscriptions. Pick the 2-3 you truly value and trim the rest.")
    return out


def commitments_insights(commitments: list[Commitment], profile: Profile) -> dict:
    cur = profile.currency
    active = [c for c in commitments if c.active]
    emi_monthly = round(sum(monthly_equiv(c.amount, c.cycle) for c in active if c.type == "emi"))
    subs_monthly = round(
        sum(monthly_equiv(c.amount, c.cycle) for c in active if c.type == "subscription")
    )
    total_monthly = emi_monthly + subs_monthly
    annual_subs = subs_monthly * 12
    budget = profile.monthly_budget
    percent = round(total_monthly / budget * 100) if budget else None

    if total_monthly == 0:
        summary = "No EMIs or subscriptions added yet — add them to see how much is locked in each month."
    elif percent is not None:
        summary = (
            f"{_fmt(total_monthly, cur)}/month is committed to EMIs & subscriptions "
            f"— that's {percent}% of your {_fmt(budget, cur)} budget."
        )
    else:
        summary = f"{_fmt(total_monthly, cur)}/month is committed to EMIs & subscriptions."

    return {
        "monthly_emi_minor": emi_monthly,
        "monthly_subs_minor": subs_monthly,
        "monthly_total_minor": total_monthly,
        "annual_subs_minor": annual_subs,
        "budget_minor": budget,
        "percent_of_budget": percent,
        "summary": summary,
        "suggestions": _audit(active, cur, annual_subs),
    }
