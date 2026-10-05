-- Sprint 0 foundation schema. Agent/MCP tables arrive in later sprints.

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS investigations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users (id),
    query TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    iteration INTEGER NOT NULL DEFAULT 0,
    max_iterations INTEGER NOT NULL DEFAULT 8,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    final_answer TEXT,
    confidence DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS investigations_started_at_idx
    ON investigations (started_at DESC);

INSERT INTO users (email, display_name)
VALUES ('local@asteria.local', 'Local Operator')
ON CONFLICT (email) DO NOTHING;
