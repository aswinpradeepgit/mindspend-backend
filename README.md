# MindSpend Backend (FastAPI)

Auth + data API for MindSpend. Supabase = identity + Postgres; FastAPI = business
logic + (later) the AI Coach. All routes are versioned under `/api/v1`.

## Architecture
- **Auth:** Supabase issues JWTs; FastAPI verifies them on every request (`app/core/security.py`).
- **DB:** Async SQLAlchemy over Supabase Postgres (`app/core/db.py`). RLS is on as a second wall; FastAPI enforces ownership in code.
- **Layout:** `core/` (config, db, security) · `models/` (ORM) · `schemas/` (Pydantic) · `services/` (logic, e.g. gamification) · `api/v1/routes/` (endpoints).

---

## Setup — do these in order

### 1. Create the Supabase project
1. Sign up at https://supabase.com → **New project**. Pick a name, a strong **database password** (save it), and a region near you.
2. Wait for it to provision (~2 min).

### 2. Create the schema
1. Dashboard → **SQL Editor** → **New query**.
2. Paste the entire contents of [`db/schema.sql`](db/schema.sql) and **Run**.
3. Dashboard → **Table Editor** — confirm `profiles`, `expenses`, `goals`, etc. exist.

### 3. Grab your secrets
- **DB connection:** Settings → **Database** → Connection string → **URI**. Convert it to the asyncpg form for `DATABASE_URL`:
  `postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres`
- **JWT secret:** Settings → **API** → **JWT Settings** → **JWT Secret** → `SUPABASE_JWT_SECRET`.
- Also note the **Project URL** and **anon public key** (Settings → API) — you'll need these for the *frontend* in the next step (not the backend).

### 4. Run locally
```bash
cd mindspend-backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then fill in DATABASE_URL + SUPABASE_JWT_SECRET
uvicorn app.main:app --reload
```
Open http://localhost:8000/docs. `GET /api/v1/health` should return `{"status":"ok"}`.
`GET /api/v1/me` and the expenses routes require a Bearer token (you'll get one once
frontend auth is wired up, or from the Supabase dashboard for testing).

### 5. Deploy (Render, free, no credit card)
1. Push this folder to its **own** GitHub repo.
2. https://render.com → **New** → **Blueprint** → connect the repo (it reads `render.yaml`).
3. Set the three secret env vars in the Render dashboard: `DATABASE_URL`, `SUPABASE_JWT_SECRET`, `ALLOWED_ORIGINS`.
4. Deploy. Your API is at `https://mindspend-api.onrender.com` (free tier sleeps after ~15 min idle; first request wakes it in ~30–50s).

> Want always-on later? Koyeb / Fly.io free allowances avoid cold starts (they require a card but stay $0 within limits). The Dockerfile here works on both.

---

## Conventions for future work
- New feature area → new module in `app/api/v1/routes/` + register in `app/api/v1/router.py`.
- Business logic goes in `app/services/`, not in route handlers.
- Server owns all trust-sensitive computation (XP, levels, badges) — never accept those from the client.
- From the next schema change, manage migrations with **Alembic** (not by hand-editing `schema.sql`).
- Money is always integer minor units.
