# Repository delivery rules

- Keep LINE identity server-verified. Never trust a `user_id` from a URL, form,
  webhook payload, or browser storage.
- All user-owned reads and mutations must scope by the authenticated LINE `sub`.
- Use UTC for persisted timestamps and convert to Asia/Bangkok only at display/day
  boundaries.
- Run the isolated test suite before handoff. Do not commit, push, deploy, or use
  real external credentials from local tests.
