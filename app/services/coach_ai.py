"""AI Coach — aggregates spending+emotion data and asks the configured LLM for
personalized, quantified coaching. Falls back to a rules-based result if the LLM
is unavailable (no key, quota, error) so the card never breaks.

All amounts are integer minor units (paise). Only aggregated numbers are sent to
the model — never raw expense rows — for privacy and token efficiency.
"""

import json
import logging
from datetime import date, timedelta

from app.models.expense import Expense
from app.models.profile import Profile
from app.services.llm import complete_json, complete_text, has_llm, is_rate_limit_error

logger = logging.getLogger(__name__)

NEGATIVE_EMOTIONS = {"anxious", "guilty", "impulsive", "stressed"}

_CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£"}


def _months_factor(period: str) -> float:
    """Scale a period total to a monthly figure (weekly → ~4.3×, monthly → 1×)."""
    return 30 / 7 if period == "weekly" else 1.0


def _humanize(stats: dict) -> dict:
    """Model-friendly view of the aggregate: amounts in MAIN currency units (not
    paise) + a currency symbol, so the LLM never sees or echoes raw minor units."""
    sym = _CURRENCY_SYMBOLS.get(stats["currency"], stats["currency"] + " ")

    def major(m: int | None) -> float:
        return round((m or 0) / 100, 2)

    def major_map(d: dict) -> dict:
        return {k: major(v) for k, v in d.items()}

    return {
        "currency": stats["currency"],
        "currency_symbol": sym,
        "period": stats["period"],
        "monthly_budget": major(stats["monthly_budget_minor"]) if stats["monthly_budget_minor"] else None,
        "expense_count": stats["expense_count"],
        "total_spent": major(stats["total_spent_minor"]),
        "by_category": major_map(stats["by_category_minor"]),
        "by_emotion": major_map(stats["by_emotion_minor"]),
        "by_intent": major_map(stats["by_intent_minor"]),
        "regret_percent": round(stats["regret_rate"] * 100),
        "no_regret_percent": round(stats["no_regret_rate"] * 100),
    }


# ── Aggregation ──────────────────────────────────────────────────────────────
def aggregate(
    expenses: list[Expense],
    profile: Profile,
    period: str,
    category_labels: dict[str, str] | None = None,
) -> dict:
    cutoff = date.today() - timedelta(days=7 if period == "weekly" else 30)
    recent = [e for e in expenses if e.date >= cutoff]
    total = sum(e.amount for e in recent)
    labels = category_labels or {}

    def group(key) -> dict[str, int]:
        out: dict[str, int] = {}
        for e in recent:
            k = key(e)
            if k:
                out[k] = out.get(k, 0) + e.amount
        return out

    regret_ct = sum(1 for e in recent if e.regret is True)
    noregret_ct = sum(1 for e in recent if e.regret is False)
    n = len(recent)

    # Group categories by human label (resolves built-in ids + custom UUIDs) so
    # the LLM never sees a raw category id.
    return {
        "period": period,
        "currency": profile.currency,
        "monthly_budget_minor": profile.monthly_budget,
        "expense_count": n,
        "total_spent_minor": total,
        "by_category_minor": group(lambda e: labels.get(e.category, e.category)),
        "by_emotion_minor": group(lambda e: e.emotion),
        "by_intent_minor": group(lambda e: e.intent),
        "regret_rate": round(regret_ct / n, 2) if n else 0,
        "no_regret_rate": round(noregret_ct / n, 2) if n else 0,
    }


# ── LLM ──────────────────────────────────────────────────────────────────────
PROMPT = """You are MindSpend's empathetic financial coach. Analyze this user's \
recent spending, which is tagged with emotions and intent. Give specific, warm, \
non-judgmental, quantified coaching that helps them save and spend mindfully.

Money in the data is in MAIN units of {currency} (NOT paise/cents); the currency \
symbol is "{symbol}". In ALL your text, write money as the symbol followed by the \
amount with thousands separators (e.g. {symbol}11,490). NEVER output a bare number \
without the symbol, and NEVER write "minor units", "paise" or "cents".

The totals cover the user's "{period}" window — when you estimate a MONTHLY saving, \
project it to a full month.

Data (JSON):
{data}

Return ONLY valid JSON, no markdown, matching exactly:
{{
  "summary": "2-3 warm sentences on how they did and the trajectory",
  "recommendations": [
    {{"title": "short punchy title",
      "body": "1-2 specific sentences tied to their data",
      "severity": "tip" | "opportunity" | "win",
      "estimated_monthly_saving": <number in {symbol} main units (NOT paise), or 0>}}
  ]
}}
Give 2-4 recommendations. Include at least one "win" if they did well."""


def generate_with_llm(stats: dict) -> dict:
    human = _humanize(stats)
    prompt = PROMPT.format(
        currency=human["currency"],
        symbol=human["currency_symbol"],
        period=human["period"],
        data=json.dumps(human, ensure_ascii=False),
    )
    data = complete_json(prompt, timeout=25.0)
    if "recommendations" not in data:
        raise ValueError("bad shape")
    # Model returns savings in MAIN units; convert back to minor units for the
    # client (which formats with formatMoney(minorUnits)).
    for r in data["recommendations"]:
        v = r.get("estimated_monthly_saving")
        r["estimated_monthly_saving"] = int(round(float(v) * 100)) if isinstance(v, (int, float)) else 0
    return data


# ── Rules fallback ───────────────────────────────────────────────────────────
def rules_fallback(stats: dict) -> dict:
    recs: list[dict] = []
    total = stats["total_spent_minor"] or 1

    # Top negative-emotion spend
    emo = stats["by_emotion_minor"]
    neg = [(k, v) for k, v in emo.items() if k in NEGATIVE_EMOTIONS]
    if neg:
        k, v = max(neg, key=lambda x: x[1])
        share = v / total
        if share > 0.25:
            recs.append({
                "title": f"You spend most when {k}",
                "body": f"{round(share*100)}% of recent spending happened while feeling {k}. "
                        "Try a 10-minute pause before buying in that mood.",
                "severity": "opportunity",
                # Half the emotion-driven spend, projected to a full month.
                "estimated_monthly_saving": int(v * 0.5 * _months_factor(stats["period"])),
            })

    if stats["no_regret_rate"] > 0.7:
        recs.append({
            "title": f"{round(stats['no_regret_rate']*100)}% of spending feels worth it 🎉",
            "body": "You're spending with intention — keep it up, your future self thanks you.",
            "severity": "win",
            "estimated_monthly_saving": 0,
        })

    if not recs:
        recs.append({
            "title": "Keep logging — your coach is learning",
            "body": "Add a few more expenses with the emotion check-in and I'll spot your patterns.",
            "severity": "tip",
            "estimated_monthly_saving": 0,
        })

    return {"summary": "Here's a quick read on your recent spending.", "recommendations": recs}


# ── Conversational coach ─────────────────────────────────────────────────────
_CHAT_SYSTEM = """You are MindSpend's warm, encouraging money coach, chatting with \
the user. Answer their question using the spending data below — be specific and \
reference real numbers when relevant. Keep replies short (2-4 sentences), friendly \
and non-judgmental, never preachy. Money is in {symbol}; always format as the symbol \
+ amount (e.g. {symbol}1,200), never raw numbers or "minor units". If they ask \
something unrelated to their money/spending, gently steer back.

User's recent spending data (JSON): {data}"""


def chat(
    expenses: list[Expense],
    profile: Profile,
    message: str,
    history: list[dict],
    category_labels: dict[str, str] | None = None,
) -> str:
    """One conversational turn, grounded in the user's aggregated data."""
    human = _humanize(aggregate(expenses, profile, "monthly", category_labels))
    system = _CHAT_SYSTEM.format(
        symbol=human["currency_symbol"], data=json.dumps(human, ensure_ascii=False)
    )
    messages = [{"role": "system", "content": system}]
    for h in history[-8:]:  # cap history to control tokens
        role = h.get("role")
        content = (h.get("content") or "")[:1000]
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message[:1000]})
    return complete_text(messages, timeout=30.0)


def generate_coach(
    expenses: list[Expense],
    profile: Profile,
    period: str,
    category_labels: dict[str, str] | None = None,
) -> dict:
    stats = aggregate(expenses, profile, period, category_labels)
    if stats["expense_count"] >= 3 and has_llm():
        try:
            return generate_with_llm(stats)
        except Exception as exc:
            if is_rate_limit_error(exc):
                logger.warning("AI Coach: LLM rate-limited (429), using rules fallback")
            else:
                logger.warning("AI Coach: LLM failed (%s), using rules fallback", exc)
    return rules_fallback(stats)
