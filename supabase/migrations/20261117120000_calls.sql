-- One row per phone call, written by the agent when the call ends.
-- Holds the caller details the client asked for: time, caller ID, whether the caller used
-- directory assistance or a keyword, which keyword, and the total duration.
-- No transcript or audio is stored.
create table public.calls (
  id               uuid primary key default gen_random_uuid(),
  started_at       timestamptz not null,
  ended_at         timestamptz not null,
  duration_seconds integer not null check (duration_seconds >= 0),
  caller_id        text,
  request_type     text not null check (request_type in ('directory', 'keyword', 'none')),
  keywords         text[] not null default '{}',
  people           text[] not null default '{}',
  outcome          text not null check (
    outcome in ('transferred', 'escalated', 'ended', 'transfer_failed', 'caller_hung_up')
  ),
  transfer_target  text,
  room_name        text,
  created_at       timestamptz not null default now()
);

comment on column public.calls.request_type is
  'directory = asked for a person by name; keyword = matched a keyword; none = neither (for example hung up or escalated)';
comment on column public.calls.keywords is 'Keywords the agent matched, exactly as listed in public.keywords';
comment on column public.calls.people is 'Staff members the caller confirmed (directory assistance)';
comment on column public.calls.caller_id is 'Caller phone number from SIP (E.164); null when withheld';

create index calls_started_at_idx on public.calls (started_at desc);

-- The agent uses the service key, which bypasses RLS. No policies: nobody else can read call data.
alter table public.calls enable row level security;
