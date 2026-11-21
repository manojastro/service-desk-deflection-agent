from apps.api.app.config import Settings
from apps.api.app.dashboard import dashboard_snapshot, metrics_text


def test_dashboard_exposes_required_metrics(database):
    snapshot = dashboard_snapshot(database, Settings())
    required = {
        "total_conversations", "strict_deflection_rate", "loose_automation_rate",
        "escalation_rate", "reopen_rate", "average_resolution_time_ms",
        "cost_per_conversation_usd", "cost_per_resolved_request_usd",
    }
    assert required <= snapshot["summary"].keys()
    assert snapshot["resolution_by_intent"]
    assert snapshot["daily_trend"]
    assert snapshot["latest_escalated_tickets"]


def test_prometheus_metrics(database):
    text = metrics_text(database)
    assert "service_desk_conversations_total" in text
    assert "service_desk_strict_deflections_total" in text

