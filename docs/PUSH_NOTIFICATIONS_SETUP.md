# Smart Push Notifications — Setup Guide

Everything the **code** needs is already built (backend targeting/copy/FCM sender,
`/devices` + `/internal/run-notifications` endpoints, the GitHub Actions cron, and
the Capacitor push wiring). This guide is the **one-time external setup** you do so
it actually delivers pushes. Do the steps in order.

> v1 sends at most **one** notification per user per day, at **20:00 IST**:
> - **streak_rescue** — you have an active streak and haven't logged today
> - **nightly_wrapup** — you logged today; a warm summary of the day
> Copy is written by the LLM (Groq) with a static fallback. Targeting is server-side.

---

## A. Database (Supabase)
Run **`db/migrations/2026-06-27_notifications.sql`** once in the Supabase SQL Editor
(Dashboard → SQL Editor → New query → paste → Run). It adds `device_tokens` and
`notification_log` (+ RLS). Idempotent.

## B. Firebase / FCM project
1. **console.firebase.google.com** → **Add project** (e.g. "MindSpend"). You can
   reuse an existing Google Cloud project or make a new one.
2. In the project → **Add app → Android**. Use package name **`com.mindspend.app`**
   (must match `applicationId` exactly). Register the app.
3. **Download `google-services.json`** and place it at:
   `expense-tracker/android/app/google-services.json`
   This file is *client config*, not a secret — committing it is standard and the
   simplest path. (Privacy-conscious alternative: inject it in the APK workflow from
   a base64 GitHub secret instead of committing.)
4. **Backend service account** (for sending via FCM HTTP v1): Firebase Console →
   **Project settings → Service accounts → Generate new private key** → downloads a
   JSON. **This one IS secret** — never commit it.

## C. Backend env vars (Render → `mindspend-api` → Environment)
| Var | Value |
|---|---|
| `FCM_PROJECT_ID` | your Firebase project id (the `project_id` field in `google-services.json`) |
| `FCM_SERVICE_ACCOUNT_JSON` | the **entire** service-account JSON from B4, pasted as one value (Render supports multi-line) |
| `INTERNAL_CRON_SECRET` | a long random string — generate with `openssl rand -hex 32` |
| `APP_TZ_OFFSET_MINUTES` | `330` (IST) — optional, this is the default |
| `NOTIFICATIONS_ENABLED` | `true` — optional kill switch, default true |

Save → Render redeploys.

## D. GitHub Actions cron secret (the **`mindspend-backend`** repo)
Repo → **Settings → Secrets and variables → Actions → New repository secret**:
- Name: **`INTERNAL_CRON_SECRET`**
- Value: the **same** string you put in Render (C).

The workflow `.github/workflows/notifications-cron.yml` runs daily at 14:30 UTC
(20:00 IST) and can also be run on demand from the Actions tab.

## E. Frontend / APK (the `mindspace` repo)
- `@capacitor/push-notifications` is already in `package.json`. The APK workflow runs
  `android:sync` + `assembleDebug`, so the next build picks up push automatically.
- Make sure `android/app/google-services.json` is in place (B3).
- Push to `main` → download the new **MindSpend-debug-apk** artifact → install on your
  phone → sign in. On login the app requests notification permission and registers its
  FCM token to `POST /api/v1/devices`.

## F. Test it end-to-end
1. **Wake the backend + trigger a run manually:** `mindspend-backend` → **Actions** →
   "Daily push notifications" → **Run workflow**. The run log prints `HTTP 200` and a
   JSON summary like `{"candidates":1,"sent":1,...}`.
   (Or: `curl -X POST https://mindspend-api.onrender.com/api/v1/internal/run-notifications -H "X-Cron-Secret: <secret>"`)
2. **Make yourself a target:** log an expense today → you qualify for **nightly_wrapup**.
   (Or, to test **streak_rescue**, have a streak where your last log was *yesterday* and
   don't log today.)
3. Re-run the workflow → you should get a push on the phone.

### Troubleshooting
- `"candidates":0` → no enabled device tokens. Confirm the app registered (sign in on
  the APK; check the `device_tokens` table in Supabase).
- `"sent":0,"no_plan":N` → you don't currently match a targeting rule (see F2).
- `"failed"` / token disabled → check `FCM_PROJECT_ID` / `FCM_SERVICE_ACCOUNT_JSON`; an
  invalid/stale token is auto-disabled.
- Nothing at 8pm but manual run works → GitHub schedules can lag a few minutes, and the
  free Render instance cold-starts (~50s); the workflow's 120s timeout covers it.
