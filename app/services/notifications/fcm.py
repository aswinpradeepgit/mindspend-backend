"""Firebase Cloud Messaging (HTTP v1) sender.

Auth uses the service-account JSON (set as FCM_SERVICE_ACCOUNT_JSON in the Render
env). We mint a short-lived OAuth access token by signing a JWT with the account's
private key (RS256) and exchanging it at Google's token endpoint — this reuses the
already-present PyJWT/cryptography deps, so no firebase-admin/google-auth needed.

send_push() returns a small result so the caller can prune dead tokens (FCM
returns 404 / UNREGISTERED for tokens that are no longer valid).
"""

import json
import time
from dataclasses import dataclass

import httpx
import jwt

from app.core.config import get_settings

settings = get_settings()

_TOKEN_URL = "https://oauth2.googleapis.com/token"
_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# Cached OAuth access token: (token, expiry_epoch).
_access_token: tuple[str, float] | None = None


@dataclass
class SendResult:
    ok: bool
    # True when FCM says the token is permanently invalid → caller should disable it.
    invalid_token: bool = False
    error: str = ""


def _service_account() -> dict:
    raw = settings.FCM_SERVICE_ACCOUNT_JSON.strip()
    if not raw:
        raise RuntimeError("FCM_SERVICE_ACCOUNT_JSON is not set")
    return json.loads(raw)


def _get_access_token() -> str:
    global _access_token
    now = time.time()
    if _access_token and _access_token[1] - 60 > now:
        return _access_token[0]

    sa = _service_account()
    iat = int(now)
    exp = iat + 3600
    assertion = jwt.encode(
        {
            "iss": sa["client_email"],
            "scope": _SCOPE,
            "aud": _TOKEN_URL,
            "iat": iat,
            "exp": exp,
        },
        sa["private_key"],
        algorithm="RS256",
    )
    resp = httpx.post(
        _TOKEN_URL,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": assertion,
        },
        timeout=15.0,
    )
    resp.raise_for_status()
    body = resp.json()
    token = body["access_token"]
    _access_token = (token, now + int(body.get("expires_in", 3600)))
    return token


def send_push(token: str, title: str, body: str, data: dict | None = None) -> SendResult:
    """Send one notification to one device token via FCM HTTP v1."""
    if not settings.FCM_PROJECT_ID:
        return SendResult(ok=False, error="FCM_PROJECT_ID not set")
    url = f"https://fcm.googleapis.com/v1/projects/{settings.FCM_PROJECT_ID}/messages:send"
    message = {
        "message": {
            "token": token,
            "notification": {"title": title, "body": body},
            "data": {k: str(v) for k, v in (data or {}).items()},
            "android": {"priority": "high", "notification": {"default_sound": True}},
        }
    }
    try:
        access = _get_access_token()
        resp = httpx.post(
            url,
            headers={"Authorization": f"Bearer {access}"},
            json=message,
            timeout=15.0,
        )
    except Exception as exc:  # noqa: BLE001 — surface to caller, never crash the run
        return SendResult(ok=False, error=str(exc))

    if resp.status_code == 200:
        return SendResult(ok=True)
    # 404 = token unregistered; 400 with INVALID_ARGUMENT on the token also means prune.
    invalid = resp.status_code == 404 or "UNREGISTERED" in resp.text or "INVALID_ARGUMENT" in resp.text
    return SendResult(ok=False, invalid_token=invalid, error=f"{resp.status_code}: {resp.text[:200]}")
