"""Notification copy — LLM-written via the provider-agnostic layer, with a static
per-type fallback so a push always has sensible text even if the LLM is down.
"""

import json
import logging

from app.services.llm import complete_json, has_llm
from app.services.notifications.targeting import NotificationPlan

logger = logging.getLogger(__name__)

_PROMPT = """You write ONE push notification for MindSpend, a playful, warm,
emotion-aware expense tracker for Indian users (₹). Tone: encouraging, concise,
a little fun (Swiggy/Zomato style) — never preachy, never guilt-trippy.

Notification type: {type}
Context (JSON): {ctx}

Return ONLY JSON: {{"title": "<=40 chars, may include one emoji", "body": "<=120 chars"}}"""


def _fallback(plan: NotificationPlan) -> dict:
    c = plan.ctx
    name = c.get("name", "there")
    if plan.type == "streak_rescue":
        d = c.get("streak_days", 0)
        return {
            "title": f"🔥 Keep your {d}-day streak!",
            "body": f"Hey {name}, log today's spend before midnight to keep your streak alive.",
        }
    # nightly_wrapup
    if c.get("count"):
        total = c.get("total", "")
        return {
            "title": "🌙 Your day, wrapped",
            "body": f"You logged {c['count']} expense(s) today ({total}). Nice mindful tracking, {name}!",
        }
    return {
        "title": "🌙 How was today?",
        "body": f"Take 10 seconds, {name} — log what you spent and how it felt.",
    }


def generate_copy(plan: NotificationPlan) -> dict:
    """Return {'title', 'body'} for a notification plan (LLM, else static fallback)."""
    if not has_llm():
        return _fallback(plan)
    try:
        data = complete_json(
            _PROMPT.format(type=plan.type, ctx=json.dumps(plan.ctx)), timeout=15.0
        )
        title = str(data.get("title") or "").strip()[:80]
        body = str(data.get("body") or "").strip()[:200]
        if title and body:
            return {"title": title, "body": body}
    except Exception as exc:  # noqa: BLE001
        logger.warning("notif copy: LLM failed (%s), using fallback", exc)
    return _fallback(plan)
