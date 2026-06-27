"""Natural-language expense parsing via Groq (OpenAI-compatible, free tier).

Turns a sentence like "320 coffee with friends, felt happy" into structured
fields: amount, category, description, emotion, intent. Server-side key only.

If the LLM is unavailable (no key, quota/429, or any error) the route falls back
to ``regex_parse_expense`` below — a best-effort, dependency-free parse so the
add form still pre-fills the amount/description and the user can finish manually.
"""

import json
import re

# Provider-agnostic LLM call + 429 detection. ``is_rate_limit_error`` is
# re-exported so the expenses route can keep importing it from here.
from app.services.llm import complete_json, is_rate_limit_error  # noqa: F401

BUILTIN_CATEGORIES = [
    {"id": "food", "label": "Food & Drink"},
    {"id": "transport", "label": "Transport"},
    {"id": "entertainment", "label": "Entertainment"},
    {"id": "health", "label": "Health"},
    {"id": "shopping", "label": "Shopping"},
    {"id": "bills", "label": "Bills"},
    {"id": "education", "label": "Education"},
    {"id": "other", "label": "Other"},
]

EMOTIONS = {"joyful", "content", "neutral", "anxious", "guilty", "impulsive", "celebratory", "stressed"}
INTENTS = {"need", "want", "treat", "social_pressure", "habit", "investment", "emergency"}

PROMPT = """Extract a single expense from this phrase. Return ONLY JSON.

Phrase: "{text}"

Valid categories (pick the best matching id): {categories}
Valid emotions: {emotions}
Valid intents: {intents}

JSON shape (use null if unknown):
{{
  "amount": <number, the spend amount in major currency units, e.g. 320>,
  "category": "<one category id from the list>",
  "description": "<short clean description, e.g. 'Coffee with friends'>",
  "emotion": "<one emotion or null>",
  "intent": "<one intent or null>"
}}"""


def parse_expense(text: str, categories: list[dict]) -> dict:
    prompt = PROMPT.format(
        text=text.replace('"', "'")[:300],
        categories=json.dumps(categories),
        emotions=sorted(EMOTIONS),
        intents=sorted(INTENTS),
    )
    data = complete_json(prompt)  # raises (incl. 429) → caught by the route

    valid_ids = {c["id"] for c in categories}
    category = data.get("category")
    if category not in valid_ids:
        category = "other"

    amount = data.get("amount")
    amount_minor = round(float(amount) * 100) if isinstance(amount, (int, float)) else 0

    emotion = data.get("emotion")
    intent = data.get("intent")

    return {
        "amount": amount_minor,
        "category": category,
        "description": (data.get("description") or "").strip()[:200],
        "emotion": emotion if emotion in EMOTIONS else None,
        "intent": intent if intent in INTENTS else None,
    }


# --- Regex fallback (no LLM) -------------------------------------------------

# Keyword → built-in category id. First match wins (checked in this order).
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("food", ("food", "eat", "lunch", "dinner", "breakfast", "coffee", "snack",
              "restaurant", "swiggy", "zomato", "grocer", "drink", "cafe", "tea",
              "pizza", "burger", "meal", "biryani")),
    ("transport", ("transport", "uber", "ola", "cab", "taxi", "bus", "train",
                   "metro", "fuel", "petrol", "diesel", "auto", "ride", "flight",
                   "rapido")),
    ("entertainment", ("movie", "game", "netflix", "spotify", "concert", "party",
                       "entertainment", "fun", "cinema")),
    ("health", ("health", "medicine", "doctor", "hospital", "gym", "pharmacy",
                "medical", "clinic")),
    ("shopping", ("shopping", "clothes", "amazon", "flipkart", "shoes", "shop",
                  "dress", "myntra")),
    ("bills", ("bill", "rent", "electricity", "recharge", "subscription", "wifi",
               "internet", "water", "broadband")),
    ("education", ("education", "course", "book", "class", "tuition", "udemy",
                   "fees", "fee")),
]

# Keyword → emotion (must be a value in EMOTIONS).
_EMOTION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("joyful", ("happy", "joy", "glad", "excited", "great")),
    ("celebratory", ("celebrat", "treat")),
    ("guilty", ("guilt", "regret")),
    ("impulsive", ("impulse", "impulsive")),
    ("stressed", ("stress", "tired", "overwhelm", "frustrat")),
    ("anxious", ("anxious", "worried", "nervous", "sad", "down")),
    ("content", ("content", "satisfied", "fine", "okay", "calm")),
]


def regex_parse_expense(text: str, categories: list[dict]) -> dict:
    """Best-effort parse without the LLM. Always succeeds (fields may be empty)."""
    lower = text.lower()

    # Amount: first number in the text (e.g. "540", "12.50").
    m = re.search(r"\d+(?:\.\d{1,2})?", text)
    amount_minor = round(float(m.group()) * 100) if m else 0

    # Category: first keyword hit; default "other". Custom categories aren't
    # keyword-matched here — the user can adjust the picker.
    category = "other"
    for cat_id, words in _CATEGORY_KEYWORDS:
        if any(w in lower for w in words):
            category = cat_id
            break

    emotion = None
    for emo, words in _EMOTION_KEYWORDS:
        if any(w in lower for w in words):
            emotion = emo
            break

    # Description: the text minus the leading amount, tidied up.
    desc = text
    if m:
        desc = (text[: m.start()] + text[m.end():]).strip(" ,.-")
    desc = re.sub(r"\s+", " ", desc).strip()[:200]

    return {
        "amount": amount_minor,
        "category": category,
        "description": desc[:1].upper() + desc[1:] if desc else "",
        "emotion": emotion,
        "intent": None,
    }
