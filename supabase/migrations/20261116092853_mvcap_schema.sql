-- MVCAP answering service: rules, directory, status updates and settings.
--
-- The agent reads these tables with the service key when a call starts. The client edits
-- them in the Supabase table editor (or CSV import), so the rules below live in the
-- database itself: a bad row is rejected at edit time, not on a live call.
-- Setting `active = false` takes a row out of service without deleting it.

create or replace function public.set_updated_at() returns trigger
language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

-- ---------------------------------------------------------------- keywords
create table public.keywords (
  id              bigint generated always as identity primary key,
  keyword         text not null,
  alias_of        text references public.keywords (keyword) on update cascade,
  action          text not null
                  check (action in ('alias', 'say_end', 'say_transfer', 'transfer', 'refer', 'followup', 'ask')),
  message         text,
  message_source  text not null default 'script' check (message_source in ('script', 'drafted')),
  question        text,
  target_type     text check (target_type in ('extension', 'phone')),
  target          text,
  voicemail_note  boolean not null default false,
  active          boolean not null default true,
  notes           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  constraint keywords_keyword_key unique (keyword),
  constraint keywords_alias_shape check ((action = 'alias') = (alias_of is not null)),
  constraint keywords_alias_is_bare check (
    action <> 'alias' or (message is null and question is null and target is null)
  ),
  constraint keywords_message_required check (
    action not in ('say_end', 'say_transfer', 'refer', 'followup') or nullif(trim(message), '') is not null
  ),
  constraint keywords_question_required check (
    action <> 'ask' or nullif(trim(question), '') is not null
  ),
  constraint keywords_target_required check (
    (action in ('transfer', 'say_transfer')) = (target is not null)
    or action in ('ask', 'alias')
  ),
  constraint keywords_target_pair check ((target_type is null) = (target is null)),
  constraint keywords_target_format check (
    target is null
    or (target_type = 'extension' and target ~ '^[0-9]{3}$')
    or (target_type = 'phone' and target ~ '^\+1[0-9]{10}$')
  )
);
create unique index keywords_keyword_lower_key on public.keywords (lower(keyword));
create trigger keywords_updated_at before update on public.keywords
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- keyword branches
-- One row per answer to a keyword's follow-up question (a county, yes/no, ...).
-- answer 'other' is the catch-all for answers that match no other row.
create table public.keyword_branches (
  id              bigint generated always as identity primary key,
  keyword         text not null references public.keywords (keyword) on update cascade on delete cascade,
  answer          text not null,
  action          text not null
                  check (action in ('say_end', 'say_transfer', 'transfer', 'refer', 'followup', 'goto')),
  message         text,
  message_source  text not null default 'script' check (message_source in ('script', 'drafted')),
  target_type     text check (target_type in ('extension', 'phone')),
  target          text,
  goto_keyword    text references public.keywords (keyword) on update cascade,
  voicemail_note  boolean not null default false,
  active          boolean not null default true,
  notes           text,
  created_at      timestamptz not null default now(),
  updated_at      timestamptz not null default now(),

  constraint branches_answer_key unique (keyword, answer),
  constraint branches_goto_shape check ((action = 'goto') = (goto_keyword is not null)),
  constraint branches_message_required check (
    action not in ('say_end', 'say_transfer', 'refer', 'followup') or nullif(trim(message), '') is not null
  ),
  constraint branches_target_required check (
    (action in ('transfer', 'say_transfer')) = (target is not null)
    or action = 'goto'
  ),
  constraint branches_target_pair check ((target_type is null) = (target is null)),
  constraint branches_target_format check (
    target is null
    or (target_type = 'extension' and target ~ '^[0-9]{3}$')
    or (target_type = 'phone' and target ~ '^\+1[0-9]{10}$')
  )
);
create index branches_keyword_idx on public.keyword_branches (keyword);
create trigger branches_updated_at before update on public.keyword_branches
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- directory
create table public.directory (
  id               bigint generated always as identity primary key,
  last_name        text not null check (nullif(trim(last_name), '') is not null),
  first_legal      text,
  first_preferred  text,
  title            text,
  extension        text check (extension ~ '^[0-9]{3}$'),
  direct_phone     text check (direct_phone ~ '^\+1[0-9]{10}$'),
  -- Never transferred to; the agent treats the person as unreachable by transfer.
  internal_only    boolean not null default false,
  active           boolean not null default true,
  notes            text,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);
create trigger directory_updated_at before update on public.directory
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- status updates
-- applies_to = keywords whose handling is preceded by this text. Null = background only.
create table public.status_updates (
  id           bigint generated always as identity primary key,
  update_date  date not null,
  text         text not null check (nullif(trim(text), '') is not null),
  applies_to   text[],
  active       boolean not null default true,
  notes        text,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger status_updates_updated_at before update on public.status_updates
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- settings
create table public.settings (
  key         text primary key,
  value       jsonb,
  notes       text,
  updated_at  timestamptz not null default now(),
  constraint settings_human_number check (
    key <> 'human_fallback_number' or value is null or value = 'null'::jsonb
    or (jsonb_typeof(value) = 'string' and value #>> '{}' ~ '^\+1[0-9]{10}$')
  )
);
create trigger settings_updated_at before update on public.settings
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------- access
-- Row level security on, and no policies: the public API keys can read nothing.
-- The agent and the dashboard use the service key, which bypasses RLS.
alter table public.keywords         enable row level security;
alter table public.keyword_branches enable row level security;
alter table public.directory        enable row level security;
alter table public.status_updates   enable row level security;
alter table public.settings         enable row level security;
