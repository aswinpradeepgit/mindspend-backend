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


_REFLECT_PROMPT = """You are MindSpend's emotionally-intelligent journal companion. \
In 2-3 warm, perceptive sentences, reflect on the EMOTIONS behind this week's \
spending — when the user spent feeling good vs. stressed/guilty/impulsive, what that \
hints at, and one kind, non-judgmental observation. Speak directly ("you"). If money \
is mentioned, write it as "{symbol}" + a formatted amount. No "minor units"/"paise".

Data (JSON):
{data}

Return ONLY JSON: {{"reflection": "<2-3 sentences>"}}"""


def reflect(
    expenses: list[Expense],
    profile: Profile,
    category_labels: dict[str, str] | None = None,
) -> dict:
    """Emotion-focused weekly reflection for the Journal (distinct from the
    savings-focused coach/explain)."""
    stats = aggregate(expenses, profile, "weekly", category_labels)
    if stats["expense_count"] >= 1 and has_llm():
        try:
            human = _humanize(stats)
            data = complete_json(
                _REFLECT_PROMPT.format(
                    symbol=human["currency_symbol"],
                    data=json.dumps(human, ensure_ascii=False),
                ),
                timeout=20.0,
            )
            r = str(data.get("reflection") or "").strip()
            if r:
                return {"reflection": r[:600]}
        except Exception as exc:  # noqa: BLE001
            logger.warning("reflection: LLM failed (%s), using fallback", exc)
    n = stats["expense_count"]
    if n == 0:
        return {"reflection": "Your emotional spending story will appear here once you log a few expenses with the check-in. Every entry is a little note to your future self. 💜"}
    return {"reflection": "Keep logging how each spend feels — over a week, the patterns between your mood and money start to tell a story worth reading."}


_PERSONALITY_PROMPT = """Based on this user's recent spending emotions, intent and \
regret, give them a playful but encouraging "money personality" archetype.

Data (JSON):
{data}

Return ONLY JSON:
{{"archetype": "2-4 words, e.g. 'The Mindful Maven', 'The Joyful Giver', 'The Stress \
Spender'", "emoji": "one single emoji that fits", "why": "1-2 warm, specific \
sentences citing their actual pattern"}}
Lean positive and aspirational if they're improving (low regret, mostly positive \
emotions). Never shame them."""


def personality(
    expenses: list[Expense],
    profile: Profile,
    category_labels: dict[str, str] | None = None,
) -> dict:
    """An evolving 'money personality' archetype from emotion/regret patterns."""
    stats = aggregate(expenses, profile, "monthly", category_labels)
    if stats["expense_count"] >= 3 and has_llm():
        try:
            human = _humanize(stats)
            data = complete_json(
                _PERSONALITY_PROMPT.format(data=json.dumps(human, ensure_ascii=False)),
                temperature=0.6,
            )
            arch = str(data.get("archetype") or "").strip()
            if arch:
                return {
                    "archetype": arch[:40],
                    "emoji": (str(data.get("emoji") or "🧬").strip() or "🧬")[:4],
                    "why": str(data.get("why") or "").strip()[:300],
                }
        except Exception as exc:  # noqa: BLE001
            logger.warning("personality: LLM failed (%s), using fallback", exc)

    n = stats["expense_count"]
    if n == 0:
        return {"archetype": "The Blank Slate", "emoji": "🌱", "why": "Log a few expenses with the check-in and your money personality will emerge."}
    regret = stats["regret_rate"]
    if regret >= 0.4:
        return {"archetype": "The Impulse Explorer", "emoji": "⚡", "why": "You spend in the moment and feel it after. A 10-second pause before buying could change the story."}
    if regret <= 0.15:
        return {"archetype": "The Mindful Maven", "emoji": "🧘", "why": "You spend with intention and rarely look back — your future self is grateful."}
    return {"archetype": "The Steady Tracker", "emoji": "📊", "why": "You're building real awareness, one mindful log at a time. Momentum is on your side."}


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
