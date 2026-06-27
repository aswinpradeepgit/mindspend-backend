-- MindSpend — initial schema + Row-Level Security
-- Run this in the Supabase SQL Editor (Dashboard → SQL Editor → New query).
--
-- Notes:
--  * Money is stored as integer minor units (paise/cents) — never floats.
--  * RLS is enabled on every user-owned table. The FastAPI backend connects as
--    the table owner (which bypasses RLS) and enforces ownership in code; these
--    policies are the second wall that protects any *direct* client access.
--  * From the next schema change onward we manage migrations with Alembic.

-- ── Extensions ───────────────────────────────────────────────────────────────
create extension if not exists "pgcrypto";  -- gen_random_uuid()

-- ── profiles ─────────────────────────────────────────────────────────────────
-- One row per auth user. Auto-created on signup via the trigger below.
create table if not exists public.profiles (
  id              uuid primary key references auth.users(id) on delete cascade,
  name            text not null default 'You',
  currency        text not null default 'INR',
  monthly_budget  bigint,
  xp              integer not null default 0,
  level           integer not null default 1,
  streak_days     integer not null default 0,
  last_log_date   date,
  created_at      timestamptz not null default now()
);

-- ── expenses ─────────────────────────────────────────────────────────────────
create table if not exists public.expenses (
  id                 uuid primary key default gen_random_uuid(),
  user_id            uuid not null references auth.users(id) on delete cascade,
  amount             bigint not null,            -- minor units
  category           text not null,              -- built-in id or custom id
  description        text not null default '',
  date               date not null,
  emotion            text,
  intent             text,
  regret             boolean,
  would_spend_less   boolean,
  xp_awarded         integer not null default 0,
  created_at         timestamptz not null default now()
);
create index if not exists expenses_user_date_idx on public.expenses (user_id, date desc);

-- ── custom_categories ────────────────────────────────────────────────────────
create table if not exists public.custom_categories (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users(id) on delete cascade,
  label     text not null,
  icon      text not null,
  color     text not null,
  created_at timestamptz not null default now()
);
create index if not exists custom_categories_user_idx on public.custom_categories (user_id);

-- ── goals ────────────────────────────────────────────────────────────────────
create table if not exists public.goals (
  id              uuid primary key default gen_random_uuid(),
  user_id         uuid not null references auth.users(id) on delete cascade,
  name            text not null,
  emoji           text not null default '🎯',
  target_amount   bigint not null,
  current_amount  bigint not null default 0,
  target_date     date,
  completed_at    timestamptz,
  created_at      timestamptz not null default now()
);
create index if not exists goals_user_idx on public.goals (user_id);

-- ── badges ───────────────────────────────────────────────────────────────────
create table if not exists public.badges (
  user_id      uuid not null references auth.users(id) on delete cascade,
  badge_id     text not null,
  unlocked_at  timestamptz not null default now(),
  primary key (user_id, badge_id)
);

-- ── ai_insights (cache for future AI Coach output) ───────────────────────────
create table if not exists public.ai_insights (
  id           uuid primary key default gen_random_uuid(),
  user_id      uuid not null references auth.users(id) on delete cascade,
  period       text not null,           -- 'daily' | 'weekly' | 'monthly'
  payload      jsonb not null,
  generated_at timestamptz not null default now(),
  expires_at   timestamptz
);
create index if not exists ai_insights_user_period_idx on public.ai_insights (user_id, period);

-- ── device_tokens (push notifications) ───────────────────────────────────────
-- One row per (user, device push token). Used to send FCM push notifications.
create table if not exists public.device_tokens (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  token       text not null unique,          -- FCM registration token
  platform    text not null default 'android',
  enabled     boolean not null default true,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index if not exists device_tokens_user_idx on public.device_tokens (user_id);

-- ── notification_log ─────────────────────────────────────────────────────────
-- One row per push sent. Used for frequency capping (max 1/day) + analytics.
create table if not exists public.notification_log (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users(id) on delete cascade,
  type      text not null,                   -- 'streak_rescue' | 'nightly_wrapup' | ...
  title     text not null default '',
  body      text not null default '',
  sent_at   timestamptz not null default now()
);
create index if not exists notification_log_user_sent_idx on public.notification_log (user_id, sent_at desc);

-- ── Row-Level Security ───────────────────────────────────────────────────────
alter table public.profiles          enable row level security;
alter table public.expenses          enable row level security;
alter table public.custom_categories enable row level security;
alter table public.goals             enable row level security;
alter table public.badges            enable row level security;
alter table public.ai_insights       enable row level security;
alter table public.device_tokens     enable row level security;
alter table public.notification_log  enable row level security;

-- Owner-only access for the `authenticated` role. (auth.uid() is the JWT subject.)
do $$
declare t text;
begin
  foreach t in array array['expenses','custom_categories','goals','badges','ai_insights','device_tokens','notification_log']
  loop
    execute format($f$
      create policy %1$s_select on public.%1$s for select to authenticated using (auth.uid() = user_id);
      create policy %1$s_insert on public.%1$s for insert to authenticated with check (auth.uid() = user_id);
      create policy %1$s_update on public.%1$s for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
      create policy %1$s_delete on public.%1$s for delete to authenticated using (auth.uid() = user_id);
    $f$, t);
  end loop;
end $$;

-- profiles keys on id (= auth user id), not user_id
create policy profiles_select on public.profiles for select to authenticated using (auth.uid() = id);
create policy profiles_update on public.profiles for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

-- ── Auto-create a profile row when a new auth user signs up ───────────────────
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, name)
  values (new.id, coalesce(new.raw_user_meta_data->>'name', 'You'))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();
