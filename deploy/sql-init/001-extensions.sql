-- Runs once, on first initialization of an empty data directory.
-- Alembic migration 0001 also creates this extension (idempotently), so a
-- database created outside compose is not left without it.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
