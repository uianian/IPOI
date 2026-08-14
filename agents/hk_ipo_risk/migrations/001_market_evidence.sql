CREATE SCHEMA IF NOT EXISTS market_agent;

-- The application initializer creates the same append-only tables and indexes.
-- This file is supplied for DBA-controlled deployments; schema name can be
-- replaced before execution when a non-default namespace is required.
CREATE TABLE IF NOT EXISTS market_agent.market_runs (
  run_id uuid PRIMARY KEY,
  doc_id text NOT NULL,
  stock_code varchar(5) NOT NULL,
  phase text NOT NULL,
  checkpoint text,
  as_of_date date,
  status text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_market_runs_lookup
  ON market_agent.market_runs (doc_id, stock_code, phase, checkpoint, created_at DESC);

CREATE TABLE IF NOT EXISTS market_agent.market_score_versions (
  score_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES market_agent.market_runs(run_id),
  score_name text NOT NULL,
  score_value double precision,
  risk_level text,
  score_version text,
  evidence_ids text[] NOT NULL DEFAULT ARRAY[]::text[],
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_agent.market_evidence (
  evidence_pk uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES market_agent.market_runs(run_id),
  evidence_id text NOT NULL,
  phase text NOT NULL,
  observation_date date,
  source text,
  content_hash char(64) NOT NULL,
  payload jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_market_evidence_lookup
  ON market_agent.market_evidence (run_id, phase, evidence_id);

CREATE TABLE IF NOT EXISTS market_agent.market_artifacts (
  artifact_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES market_agent.market_runs(run_id),
  json_path text,
  report_path text,
  content_hash char(64),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_agent.market_debate_rounds (
  debate_round_id uuid PRIMARY KEY,
  debate_id text NOT NULL,
  run_id uuid NOT NULL REFERENCES market_agent.market_runs(run_id),
  round_number integer NOT NULL,
  challenge text NOT NULL,
  response jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS market_agent.market_tool_calls (
  tool_call_id uuid PRIMARY KEY,
  debate_id text NOT NULL,
  tool_name text NOT NULL,
  arguments jsonb NOT NULL,
  result jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

