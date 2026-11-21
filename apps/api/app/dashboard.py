from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from apps.api.app.config import Settings
from apps.api.app.db import Database


def dashboard_snapshot(db: Database, settings: Settings) -> dict[str, Any]:
    sessions = db.fetchall("SELECT * FROM support_sessions ORDER BY started_at DESC")
    resolutions = db.fetchall("SELECT * FROM resolutions")
    tickets = db.fetchall("SELECT * FROM tickets ORDER BY created_at DESC")
    reopens = db.fetchall("SELECT * FROM reopen_events")
    tools = db.fetchall("SELECT * FROM tool_executions")
    total = len(sessions)
    strict = sum(int(row["strict_deflected"]) for row in resolutions)
    loose = len(resolutions)
    escalated = sum(row["status"] == "escalated" for row in sessions)
    total_cost = sum(float(row["cost_usd"] or 0) for row in sessions)
    resolved_by_intent: Counter[str] = Counter(
        row["detected_intent"] for row in sessions if row["status"] == "resolved"
    )
    unresolved_by_intent: Counter[str] = Counter(
        row["detected_intent"] for row in sessions if row["status"] == "escalated"
    )
    durations = [float(row["duration_ms"]) for row in sessions if row["duration_ms"] is not None]
    buckets = {"low_0_49": 0, "medium_50_79": 0, "high_80_100": 0}
    for row in sessions:
        confidence = float(row["confidence"])
        buckets["low_0_49" if confidence < 0.5 else "medium_50_79" if confidence < 0.8 else "high_80_100"] += 1
    trends: dict[str, dict[str, int]] = defaultdict(lambda: {"conversations": 0, "resolved": 0, "escalated": 0})
    for row in sessions:
        day = row["started_at"][:10]
        trends[day]["conversations"] += 1
        if row["status"] in {"resolved", "escalated"}:
            trends[day][row["status"]] += 1
    latest_tickets = []
    for row in tickets[:10]:
        diagnostic = json.loads(row["diagnostic_summary_json"])
        latest_tickets.append({
            "external_id": row["external_id"], "status": row["status"], "priority": row["priority"],
            "created_at": row["created_at"], "session_id": row["session_id"],
            "issue": diagnostic.get("user_issue", ""), "intent": diagnostic.get("detected_intent", "unknown"),
        })
    return {
        "window": {"reopen_hours": settings.reopen_window_hours, "generated_at": datetime.now(UTC).isoformat()},
        "summary": {
            "total_conversations": total,
            "strict_deflection_rate": round(strict / total, 4) if total else 0,
            "loose_automation_rate": round(loose / total, 4) if total else 0,
            "escalation_rate": round(escalated / total, 4) if total else 0,
            "reopen_rate": round(len(reopens) / loose, 4) if loose else 0,
            "average_resolution_time_ms": round(sum(durations) / len(durations), 2) if durations else 0,
            "cost_per_conversation_usd": round(total_cost / total, 6) if total else 0,
            "cost_per_resolved_request_usd": round(total_cost / loose, 6) if loose else 0,
        },
        "resolution_by_intent": dict(resolved_by_intent),
        "tool_outcomes": {"success": sum(bool(row["success"]) for row in tools), "failure": sum(not bool(row["success"]) for row in tools)},
        "confidence_distribution": buckets,
        "top_unresolved_intents": [{"intent": key, "count": value} for key, value in unresolved_by_intent.most_common(5)],
        "daily_trend": [{"date": day, **values} for day, values in sorted(trends.items())],
        "latest_escalated_tickets": latest_tickets,
    }


def metrics_text(db: Database) -> str:
    total = db.fetchone("SELECT COUNT(*) AS n FROM support_sessions")["n"]
    resolved = db.fetchone("SELECT COUNT(*) AS n FROM resolutions WHERE strict_deflected=1")["n"]
    escalated = db.fetchone("SELECT COUNT(*) AS n FROM escalations")["n"]
    tool_success = db.fetchone("SELECT COUNT(*) AS n FROM tool_executions WHERE success=1")["n"]
    return "\n".join([
        "# HELP service_desk_conversations_total Total support conversations.",
        "# TYPE service_desk_conversations_total counter",
        f"service_desk_conversations_total {total}",
        "# HELP service_desk_strict_deflections_total Verified automated resolutions not reopened in the window.",
        "# TYPE service_desk_strict_deflections_total gauge",
        f"service_desk_strict_deflections_total {resolved}",
        "# TYPE service_desk_escalations_total counter",
        f"service_desk_escalations_total {escalated}",
        "# TYPE service_desk_tool_success_total counter",
        f"service_desk_tool_success_total {tool_success}",
        "",
    ])

