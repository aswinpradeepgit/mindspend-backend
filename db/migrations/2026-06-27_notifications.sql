-- Migration: push-notification tables (device_tokens, notification_log)
-- Run ONCE in the Supabase SQL Editor (Dashboard → SQL Editor → New query).
-- Idempotent: safe to re-run (uses IF NOT EXISTS / drop-then-create policies).

-- ── device_tokens ────────────────────────────────────────────────────────────
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
create table if not exists public.notification_log (
  id        uuid primary key default gen_random_uuid(),
  user_id   uuid not null references auth.users(id) on delete cascade,
  type      text not null,
  title     text not null default '',
  body      text not null default '',
  sent_at   timestamptz not null default now()
);
create index if not exists notification_log_user_sent_idx on public.notification_log (user_id, sent_at desc);

-- ── RLS (owner-only; backend connects as owner and bypasses these) ────────────
alter table public.device_tokens    enable row level security;
alter table public.notification_log enable row level security;

do $$
declare t text;
begin
  foreach t in array array['device_tokens','notification_log']
  loop
    execute format('drop policy if exists %1$s_select on public.%1$s', t);
    execute format('drop policy if exists %1$s_insert on public.%1$s', t);
    execute format('drop policy if exists %1$s_update on public.%1$s', t);
    execute format('drop policy if exists %1$s_delete on public.%1$s', t);
    execute format($f$
      create policy %1$s_select on public.%1$s for select to authenticated using (auth.uid() = user_id);
      create policy %1$s_insert on public.%1$s for insert to authenticated with check (auth.uid() = user_id);
      create policy %1$s_update on public.%1$s for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id);
      create policy %1$s_delete on public.%1$s for delete to authenticated using (auth.uid() = user_id);
    $f$, t);
  end loop;
end $$;
