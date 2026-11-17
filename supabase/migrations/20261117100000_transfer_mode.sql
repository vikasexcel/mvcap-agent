-- How the agent transfers a caller:
--   bridge: dial the destination into the call, send the extension as tones, keep both legs open
--   blind:  SIP REFER hands the caller over and the agent leaves (extension rides as post-dial digits)
--   hybrid: blind for phone numbers, bridge for extensions
insert into public.settings (key, value, notes) values
  ('transfer_mode', '"bridge"'::jsonb,
   'bridge | blind | hybrid. blind closes the agent session at hand-off; an extension is sent as post-dial digits, which the provider may ignore. Test before using blind or hybrid in production')
on conflict (key) do nothing;

alter table public.settings add constraint settings_transfer_mode check (
  key <> 'transfer_mode'
  or (jsonb_typeof(value) = 'string' and value #>> '{}' in ('bridge', 'blind', 'hybrid'))
);
