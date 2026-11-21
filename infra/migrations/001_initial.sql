PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
  id TEXT PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  display_name TEXT NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('employee','support_agent','admin')),
  department TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS intents (
  id TEXT PRIMARY KEY,
  name TEXT UNIQUE NOT NULL,
  description TEXT NOT NULL,
  requires_confirmation INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS support_sessions (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id),
  original_message TEXT NOT NULL,
  normalized_message TEXT NOT NULL,
  detected_intent TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence REAL NOT NULL DEFAULT 0,
  pending_action_json TEXT,
  state_json TEXT NOT NULL DEFAULT '{}',
  ticket_id TEXT,
  started_at TEXT NOT NULL,
  completed_at TEXT,
  duration_ms REAL,
  cost_usd REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES support_sessions(id),
  sender TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
  id TEXT PRIMARY KEY,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  intent TEXT NOT NULL,
  tenant_id TEXT NOT NULL DEFAULT 'demo-tenant',
  allowed_roles TEXT NOT NULL DEFAULT '["employee","support_agent","admin"]',
  approved INTEGER NOT NULL DEFAULT 1,
  version TEXT NOT NULL DEFAULT '1.0',
  source_uri TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retrieval_evidence (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES support_sessions(id),
  document_id TEXT NOT NULL REFERENCES knowledge_documents(id),
  rank INTEGER NOT NULL,
  keyword_score REAL NOT NULL,
  vector_score REAL NOT NULL,
  hybrid_score REAL NOT NULL,
  excerpt TEXT NOT NULL,
  latency_ms REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_executions (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES support_sessions(id),
  tool_name TEXT NOT NULL,
  arguments_json TEXT NOT NULL,
  result_json TEXT NOT NULL,
  success INTEGER NOT NULL,
  duration_ms REAL NOT NULL,
  confirmed_by TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS resolutions (
  id TEXT PRIMARY KEY,
  session_id TEXT UNIQUE NOT NULL REFERENCES support_sessions(id),
  resolution_type TEXT NOT NULL,
  summary TEXT NOT NULL,
  strict_deflected INTEGER NOT NULL,
  verified INTEGER NOT NULL,
  resolved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS escalations (
  id TEXT PRIMARY KEY,
  session_id TEXT UNIQUE NOT NULL REFERENCES support_sessions(id),
  ticket_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  recommended_next_action TEXT NOT NULL,
  escalated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tickets (
  id TEXT PRIMARY KEY,
  external_id TEXT UNIQUE NOT NULL,
  session_id TEXT NOT NULL REFERENCES support_sessions(id),
  status TEXT NOT NULL,
  priority TEXT NOT NULL,
  diagnostic_summary_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reopen_events (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES support_sessions(id),
  reason TEXT NOT NULL,
  reopened_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_usage (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES support_sessions(id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cost_usd REAL NOT NULL,
  latency_ms REAL NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
  id TEXT PRIMARY KEY,
  session_id TEXT,
  actor_user_id TEXT,
  event_type TEXT NOT NULL,
  outcome TEXT NOT NULL,
  request_id TEXT,
  safe_metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mock_accounts (
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  locked INTEGER NOT NULL DEFAULT 0,
  password_version INTEGER NOT NULL DEFAULT 1,
  mfa_enrolled INTEGER NOT NULL DEFAULT 1,
  last_password_reset TEXT
);

CREATE TABLE IF NOT EXISTS mock_vpn_profiles (
  user_id TEXT PRIMARY KEY REFERENCES users(id),
  assigned INTEGER NOT NULL DEFAULT 1,
  certificate_valid INTEGER NOT NULL DEFAULT 1,
  gateway TEXT NOT NULL DEFAULT 'vpn.demo.corp'
);

CREATE TABLE IF NOT EXISTS mock_outages (
  id TEXT PRIMARY KEY,
  service TEXT NOT NULL,
  region TEXT NOT NULL,
  active INTEGER NOT NULL DEFAULT 0,
  message TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sessions_status ON support_sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_intent ON support_sessions(detected_intent);
CREATE INDEX IF NOT EXISTS idx_evidence_session ON retrieval_evidence(session_id);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_events(session_id);

