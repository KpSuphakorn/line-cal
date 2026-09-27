# Supabase setup for LINE Cal

This setup keeps Supabase behind FastAPI. The LIFF browser never receives the
database password or a privileged Supabase key.

## 1. Create the project

1. Sign in at the Supabase Dashboard and create a new project.
2. Choose the nearest available region to the users, normally Singapore for a
   Thailand pilot.
3. Generate and safely store a strong database password.
4. Wait until the database reports healthy.

## 2. Copy connection strings

Open the project and click **Connect**. Copy the values shown by Supabase rather
than constructing hostnames manually.

- For a persistent backend with IPv6, use **Direct connection** at runtime.
- For a persistent IPv4-only host, use **Session pooler** on port 5432.
- Use the **Direct connection** for Alembic migrations when the machine can
  reach the IPv6 endpoint.
- Transaction pooler on port 6543 is intended for serverless/transient runtime
  connections and has session/prepared-statement limitations. Do not use it for
  Alembic migrations; use Direct or the approved Session pooler on port 5432.

Append `?sslmode=require` when it is not already present. Percent-encode reserved
characters in the password.

## 3. Configure local secrets

Keep these only in `.env` or the deployment platform's secret manager:

```dotenv
APP_ENV=production
DATABASE_URL=postgresql://runtime-connection-from-supabase?sslmode=require
# Optional when the migration connection must differ from DATABASE_URL:
# MIGRATION_DATABASE_URL=postgresql://direct-connection-from-supabase?sslmode=require

LINE_CHANNEL_SECRET=...
LINE_CHANNEL_ACCESS_TOKEN=...
LINE_LOGIN_CHANNEL_ID=...
LIFF_ID=...
GEMINI_API_KEY=...
WEBAPP_BASE_URL=https://your-production-domain.example/webapp
AI_DAILY_LIMIT=60
```

Never put these values into `dashboard.html`, Git, screenshots or chat.

## 4. Apply the schema (initial setup only)

Use Alembic as the only schema owner. For a new database, load `.env` in the
shell and apply all revisions once through Direct or Session pooler port 5432:

```bash
set -a; source .env; set +a
alembic upgrade head
```

Then inspect the Supabase Table Editor and confirm the expected tables,
constraints and indexes exist. Do not rely on `Base.metadata.create_all()` in
production.

`MIGRATION_DATABASE_URL` is optional in the application configuration and falls
back to `DATABASE_URL`. Set it only when the runtime URL is unsuitable for DDL;
never use Transaction pooler port 6543 for migrations. The application normalizes
both `postgres://` and `postgresql://` to psycopg2 and forces `sslmode=require`.

For later releases, push to `main`: Railway runs `alembic upgrade head` as its
pre-deploy command automatically. Do not run the migration manually before each
push. See the deploy workflow in the [README](../README.md#deploy-to-railway).

## 5. Runtime connection policy

- Keep the SQLAlchemy engine at module scope.
- Use a small application pool for three to five pilot users.
- The default pool is five connections with two overflow connections; tune
  `DB_POOL_SIZE` and `DB_MAX_OVERFLOW` only when deployment metrics justify it.
- Enable `pool_pre_ping` and encrypted connections.
- If deployment is serverless, use the transaction pooler and adapt SQLAlchemy
  pooling for that environment instead of reusing persistent-server settings.

## 6. Cutover

1. Back up any SQLite data that matters.
2. Apply migrations to a new Supabase project.
3. Start with empty pilot data unless existing records are genuinely needed.
4. If importing, write a one-time explicit migration that maps each record to a
   verified LINE user; never copy a shared `default_user`.
5. Switch the deployment secret to the Supabase runtime URL.
6. Confirm Profile, one food capture and one workout for two distinct users
   before inviting friends.

Official reference: [Connect to your database](https://supabase.com/docs/guides/database/connecting-to-postgres).
