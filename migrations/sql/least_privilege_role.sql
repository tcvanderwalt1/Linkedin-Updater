-- Least-privilege Neon role setup (run as project owner / migrator).
-- Replace passwords before executing. Never commit real passwords.

-- 1) Create app role (DML only)
-- CREATE ROLE app LOGIN PASSWORD 'REPLACE_WITH_32_PLUS_CHAR_SECRET';

-- 2) Grant connect + schema usage
-- GRANT CONNECT ON DATABASE neondb TO app;
-- GRANT USAGE ON SCHEMA public TO app;

-- 3) Table privileges (no DDL)
-- GRANT SELECT, INSERT, UPDATE ON TABLE
--   articles, drafts, linkedin_tokens, pipeline_runs TO app;
-- -- No DELETE by default; add if you need reject cleanup:
-- -- GRANT DELETE ON TABLE drafts TO app;

-- 4) Sequence privileges if any serials are added later
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app;

-- 5) Default privileges for future tables created by migrator
-- ALTER DEFAULT PRIVILEGES IN SCHEMA public
--   GRANT SELECT, INSERT, UPDATE ON TABLES TO app;

-- Connection string for the app (prefer PgBouncer pooled host):
-- postgresql://app:SECRET@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require

-- Security notes (Streamlit has dynamic IPs → Neon must allow 0.0.0.0/0):
-- * Strong random password (32+)
-- * sslmode=require always
-- * NullPool / pooler to avoid ghost connections
-- * Streamlit APP_PASSWORD gate; never expose DATABASE_URL in logs
-- * Parameterized ORM queries only — no raw SQL from UI input
