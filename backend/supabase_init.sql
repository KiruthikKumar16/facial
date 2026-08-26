-- Run once in Supabase SQL Editor (Dashboard → SQL → New query)

CREATE EXTENSION IF NOT EXISTS vector;

-- Tables are created automatically by the backend on startup via SQLAlchemy.
-- After first deploy, verify with:
--   SELECT tablename FROM pg_tables WHERE schemaname = 'public';
