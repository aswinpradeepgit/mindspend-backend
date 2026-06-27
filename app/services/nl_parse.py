"""Natural-language expense parsing via Gemini.

Turns a sentence like "320 coffee with friends, felt happy" into structured
fields: amount, category, description, emotion, intent. Server-side key only.
"""

import json

from app.core.config import get_settings

settings = get_settings()

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
    from google import genai  # lazy import

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    prompt = PROMPT.format(
        text=text.replace('"', "'")[:300],
        categories=json.dumps(categories),
        emotions=sorted(EMOTIONS),
        intents=sorted(INTENTS),
    )
    resp = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    raw = (resp.text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    data = json.loads(raw)

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
