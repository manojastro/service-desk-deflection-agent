REQUIRED_TABLES = {
    "users", "support_sessions", "messages", "intents", "knowledge_documents",
    "retrieval_evidence", "tool_executions", "resolutions", "escalations", "tickets",
    "reopen_events", "model_usage", "audit_events",
}


def test_migration_contains_required_data_model(database):
    rows = database.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    assert REQUIRED_TABLES <= {row["name"] for row in rows}


def test_seed_volume(database):
    assert database.fetchone("SELECT COUNT(*) n FROM users")["n"] >= 25
    assert database.fetchone("SELECT COUNT(*) n FROM support_sessions")["n"] >= 10
    assert database.fetchone("SELECT COUNT(*) n FROM knowledge_documents")["n"] >= 8

