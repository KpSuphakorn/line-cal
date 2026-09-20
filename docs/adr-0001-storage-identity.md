# ADR 0001: Supabase/Postgres and verified LINE identity

## Decision

Use Supabase/PostgreSQL in production and keep SQLite as a development fallback.
Use a verified LINE Login ID token for LIFF requests and derive the owner from
its `sub`; use the signed LINE webhook source for webhook requests.

## Rationale

The data is relational and needs foreign keys, unique idempotency keys and
owner-scoped queries. Supabase provides managed PostgreSQL without introducing a
second persistence model. Browser-supplied user IDs are not an authentication
boundary.

## Consequences

Production configuration fails closed when identity/database settings are absent.
Existing local URLs must be replaced with LIFF initialization and bearer tokens.
