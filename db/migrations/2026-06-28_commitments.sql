-- Migration: commitments (EMIs + subscriptions)
-- Run ONCE in the Supabase SQL Editor. Idempotent.

create table if not exists public.commitments (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  type        text not null,                 -- 'emi' | 'subscription'
  name        text not null,
  amount      bigint not null,               -- minor units, per cycle
  cycle       text not null default 'monthly', -- 'monthly' | 'yearly' | 'weekly'
  due_day     int,                           -- 1-31, optional
  months_left int,                           -- EMI tenure remaining, optional
  icon        text not null default '',
  active      boolean not null default true,
  created_at  timestamptz not null default now()
);
create index if not exists commitments_user_idx on public.commitments (user_id);

alter table public.commitments enable row level security;

do $$
begin
  execute 'drop policy if exists commitments_select on public.commitments';
  execute 'drop policy if exists commitments_insert on public.commitments';
  execute 'drop policy if exists commitments_update on public.commitments';
  execute 'drop policy if exists commitments_delete on public.commitments';
  execute 'create policy commitments_select on public.commitments for select to authenticated using (auth.uid() = user_id)';
  execute 'create policy commitments_insert on public.commitments for insert to authenticated with check (auth.uid() = user_id)';
  execute 'create policy commitments_update on public.commitments for update to authenticated using (auth.uid() = user_id) with check (auth.uid() = user_id)';
  execute 'create policy commitments_delete on public.commitments for delete to authenticated using (auth.uid() = user_id)';
end $$;
