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
from app.services.llm import complete_json, has_llm, is_rate_limit_error

logger = logging.getLogger(__name__)

NEGATIVE_EMOTIONS = {"anxious", "guilty", "impulsive", "stressed"}


# ── Aggregation ──────────────────────────────────────────────────────────────
def aggregate(expenses: list[Expense], profile: Profile, period: str) -> dict:
    cutoff = date.today() - timedelta(days=7 if period == "weekly" else 30)
    recent = [e for e in expenses if e.date >= cutoff]
    total = sum(e.amount for e in recent)

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

    return {
        "period": period,
        "currency": profile.currency,
        "monthly_budget_minor": profile.monthly_budget,
        "expense_count": n,
        "total_spent_minor": total,
        "by_category_minor": group(lambda e: e.category),
        "by_emotion_minor": group(lambda e: e.emotion),
        "by_intent_minor": group(lambda e: e.intent),
        "regret_rate": round(regret_ct / n, 2) if n else 0,
        "no_regret_rate": round(noregret_ct / n, 2) if n else 0,
    }


# ── LLM ──────────────────────────────────────────────────────────────────────
PROMPT = """You are MindSpend's empathetic financial coach. Analyze this user's \
recent spending, which is tagged with emotions and intent. Give specific, warm, \
non-judgmental, quantified coaching that helps them save and spend mindfully.

All money values are integer MINOR units ({currency}, e.g. paise/cents). When you \
estimate savings, return them as integer minor units too.

Data (JSON):
{data}

Return ONLY valid JSON, no markdown, matching exactly:
{{
  "summary": "2-3 warm sentences on how they did and the trajectory",
  "recommendations": [
    {{"title": "short punchy title",
      "body": "1-2 specific sentences tied to their data",
      "severity": "tip" | "opportunity" | "win",
      "estimated_monthly_saving": <integer minor units, or 0>}}
  ]
}}
Give 2-4 recommendations. Include at least one "win" if they did well."""


def generate_with_llm(stats: dict) -> dict:
    prompt = PROMPT.format(currency=stats["currency"], data=json.dumps(stats))
    data = complete_json(prompt, timeout=25.0)
    # minimal shape guard
    if "recommendations" not in data:
        raise ValueError("bad shape")
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
                "estimated_monthly_saving": int(v * 0.5),
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


def generate_coach(expenses: list[Expense], profile: Profile, period: str) -> dict:
    stats = aggregate(expenses, profile, period)
    if stats["expense_count"] >= 3 and has_llm():
        try:
            return generate_with_llm(stats)
        except Exception as exc:
            if is_rate_limit_error(exc):
                logger.warning("AI Coach: LLM rate-limited (429), using rules fallback")
            else:
                logger.warning("AI Coach: LLM failed (%s), using rules fallback", exc)
    return rules_fallback(stats)
