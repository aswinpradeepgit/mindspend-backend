"""'Explain my month' — narrate the user's spending story in a few warm lines.

Reuses the coach aggregation (aggregated numbers only, never raw rows) and the
provider-agnostic LLM layer, with a rules-based fallback so it never breaks.
"""

import json
import logging

from app.models.expense import Expense
from app.models.profile import Profile
from app.services.coach_ai import _CURRENCY_SYMBOLS, _humanize, aggregate
from app.services.llm import complete_json, has_llm

logger = logging.getLogger(__name__)

_PROMPT = """You are MindSpend's warm, encouraging money coach. In EXACTLY 3 short \
sentences (~45 words total), narrate this user's {period} spending story: what stood \
out, the emotional pattern behind it, and one gentle, specific suggestion. Speak \
directly to them ("you"). Write money as "{symbol}" + a formatted amount (e.g. \
{symbol}11,490) — never a bare number, never the words "minor units"/"paise".

Data (JSON):
{data}

Return ONLY JSON: {{"narrative": "<3 sentences>"}}"""


def _fallback(stats: dict) -> dict:
    sym = _CURRENCY_SYMBOLS.get(stats["currency"], stats["currency"] + " ")
    total = stats["total_spent_minor"] // 100
    n = stats["expense_count"]
    if n == 0:
        return {"narrative": "No spending logged this month yet — add a few expenses with the emotion check-in and I'll tell your money story here."}
    return {
        "narrative": (
            f"You logged {n} expense{'s' if n != 1 else ''} this month, totalling {sym}{total:,}. "
            "Keep tracking with the emotion check-in so I can spot your patterns. "
            "Try a 10-minute pause before any non-essential buy this week."
        )
    }


def explain(
    expenses: list[Expense],
    profile: Profile,
    period: str = "monthly",
    category_labels: dict[str, str] | None = None,
) -> dict:
    stats = aggregate(expenses, profile, period, category_labels)
    if stats["expense_count"] >= 1 and has_llm():
        try:
            human = _humanize(stats)
            data = complete_json(
                _PROMPT.format(
                    period=period,
                    symbol=human["currency_symbol"],
                    data=json.dumps(human, ensure_ascii=False),
                ),
                timeout=20.0,
            )
            narrative = str(data.get("narrative") or "").strip()
            if narrative:
                return {"narrative": narrative[:600]}
        except Exception as exc:  # noqa: BLE001
            logger.warning("explain-month: LLM failed (%s), using fallback", exc)
    return _fallback(stats)
