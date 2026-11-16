-- Extension transfers now dial the main number, pause, then send the extension as tones.
-- Replaces the unused pbx_transfer_template setting. Real phone numbers are set in the table
-- editor, not here, so no number is stored in the repository.

delete from public.settings where key = 'pbx_transfer_template';

insert into public.settings (key, value, notes) values
  ('pbx_main_number', null,
   'PENDING CLIENT: main office number in E.164. Extension transfers dial this number, wait pbx_dtmf_pause_seconds, then send the extension as keypad tones'),
  ('pbx_dtmf_pause_seconds', '3'::jsonb,
   'Seconds to wait after the main number answers before sending the extension'),
  ('transfer_override_number', null,
   'TEST SWITCH: when set (E.164), every transfer rings this number instead of the real target. Leave empty in production')
on conflict (key) do nothing;

alter table public.settings drop constraint settings_human_number;
alter table public.settings add constraint settings_phone_numbers check (
  key not in ('human_fallback_number', 'pbx_main_number', 'transfer_override_number')
  or value is null or value = 'null'::jsonb
  or (jsonb_typeof(value) = 'string' and value #>> '{}' ~ '^\+1[0-9]{10}$')
);
alter table public.settings add constraint settings_pause_seconds check (
  key <> 'pbx_dtmf_pause_seconds'
  or (jsonb_typeof(value) = 'number' and (value #>> '{}')::numeric between 0 and 10)
);
