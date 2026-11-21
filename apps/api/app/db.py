from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

from apps.api.app.config import PROJECT_ROOT, Settings, get_settings


def utcnow() -> str:
    return datetime.now(UTC).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def password_hash(password: str) -> str:
    return hashlib.sha256(f"service-desk-demo::{password}".encode()).hexdigest()


class Database:
    def __init__(self, settings: Settings | None = None, path: Path | None = None):
        self.settings = settings or get_settings()
        self.path = path or self.settings.sqlite_path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        migration = PROJECT_ROOT / "infra" / "migrations" / "001_initial.sql"
        with self.connect() as connection:
            connection.executescript(migration.read_text(encoding="utf-8"))

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as connection:
            connection.execute(sql, params)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(sql, params).fetchone()
            return dict(row) if row else None

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as connection:
            return [dict(row) for row in connection.execute(sql, params).fetchall()]

    def insert_audit(
        self,
        event_type: str,
        outcome: str,
        session_id: str | None = None,
        actor_user_id: str | None = None,
        request_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.execute(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
            (
                new_id("aud"),
                session_id,
                actor_user_id,
                event_type,
                outcome,
                request_id,
                json.dumps(metadata or {}, sort_keys=True),
                utcnow(),
            ),
        )


KNOWLEDGE = [
    (
        "kb_password",
        "Password reset and credential recovery SOP",
        "Use the approved self-service reset action after verifying the signed-in employee identity. "
        "A reset creates a temporary password and forces a change at next sign-in. Never ask an employee "
        "to send their existing password. Confirm before resetting credentials and verify the password version increased.",
        "password_reset",
    ),
    (
        "kb_unlock",
        "Locked account recovery runbook",
        "Check the directory account state. If it is locked, obtain employee confirmation before unlocking. "
        "After the action, check that locked is false. Repeated lockouts should be escalated for security review.",
        "account_unlock",
    ),
    (
        "kb_vpn",
        "Corporate VPN connection troubleshooting",
        "Confirm the VPN profile is assigned and its certificate is valid. Disconnect and reconnect, verify the system clock, "
        "then retry the corporate gateway. Escalate certificate or profile assignment failures to Network Operations.",
        "vpn_troubleshooting",
    ),
    (
        "kb_mfa",
        "MFA sign-in troubleshooting",
        "Verify automatic date and time, network access, and that the authenticator notification is enabled. "
        "Try a one-time code. Lost devices and MFA enrollment changes require identity verification by the support desk.",
        "mfa_troubleshooting",
    ),
    (
        "kb_software",
        "Software access request policy",
        "Software access is requested through the approved catalog. Employee confirmation is required before submission. "
        "Licensed or privileged software is routed to the manager and application owner; the request receipt must be retained.",
        "software_access_request",
    ),
    (
        "kb_wifi",
        "Office Wi-Fi and network recovery",
        "Forget and rejoin Corp-WiFi, confirm airplane mode is off, renew the DHCP lease, and test another approved network. "
        "Do not disable endpoint security. Multiple affected employees may indicate an outage and should be checked first.",
        "wifi_network_troubleshooting",
    ),
    (
        "kb_outage",
        "Known service outage lookup procedure",
        "Check the authoritative local status adapter for active incidents by service and region. Share the incident message "
        "and avoid unnecessary state changes. If no incident matches, continue normal troubleshooting.",
        "known_outage_lookup",
    ),
    (
        "kb_phishing",
        "Suspicious email reporting guide",
        "Do not click links or open attachments. Use the Report Phishing control and disconnect from the network if a payload ran. "
        "Credential disclosure or malware execution must be escalated immediately to Security Operations.",
        "knowledge_question",
    ),
    (
        "kb_printer",
        "Managed printer basics",
        "Verify the printer is online, clear paused local jobs, and re-add it from the managed printer directory. "
        "Never install an unapproved driver. Hardware errors require a facilities support ticket.",
        "knowledge_question",
    ),
]


def seed_database(db: Database, reset: bool = False) -> dict[str, int]:
    if reset and db.path.exists():
        db.path.unlink()
    db.migrate()
    now = utcnow()
    departments = ["Engineering", "Finance", "Sales", "People", "Operations", "Legal"]
    with db.connect() as connection:
        if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            users = []
            for number in range(1, 31):
                username = f"employee{number:02d}"
                users.append(
                    (
                        f"usr_{number:03d}",
                        username,
                        f"Demo Employee {number:02d}",
                        password_hash("demo123"),
                        "employee",
                        departments[(number - 1) % len(departments)],
                        now,
                    )
                )
            users.extend(
                [
                    ("usr_support", "support", "Demo Support Agent", password_hash("support123"), "support_agent", "IT", now),
                    ("usr_admin", "admin", "Demo Administrator", password_hash("admin123"), "admin", "IT", now),
                ]
            )
            connection.executemany("INSERT INTO users VALUES (?,?,?,?,?,?,?)", users)
            for row in users[:30]:
                number = int(row[0].split("_")[1])
                connection.execute(
                    "INSERT INTO mock_accounts VALUES (?,?,?,?,?)",
                    (row[0], 1 if number in {2, 7, 19} else 0, 1, 0 if number == 9 else 1, None),
                )
                connection.execute(
                    "INSERT INTO mock_vpn_profiles VALUES (?,?,?,?)",
                    (row[0], 0 if number == 11 else 1, 0 if number == 14 else 1, "vpn.demo.corp"),
                )

        for intent in (
            "password_reset", "account_unlock", "vpn_troubleshooting", "mfa_troubleshooting",
            "software_access_request", "wifi_network_troubleshooting", "known_outage_lookup",
            "knowledge_question", "unknown",
        ):
            connection.execute(
                "INSERT OR IGNORE INTO intents VALUES (?,?,?,?)",
                (f"intent_{intent}", intent, intent.replace("_", " ").title(), int(intent in {"password_reset", "account_unlock", "software_access_request"})),
            )
        for doc_id, title, content, intent in KNOWLEDGE:
            connection.execute(
                "INSERT OR REPLACE INTO knowledge_documents VALUES (?,?,?,?,?,?,?,?,?,?)",
                (doc_id, title, content, intent, "demo-tenant", '["employee","support_agent","admin"]', 1, "1.0", f"sop://{doc_id}", now),
            )
        connection.execute(
            "INSERT OR REPLACE INTO mock_outages VALUES (?,?,?,?,?,?)",
            ("outage_email", "email", "APAC", 1, "Email delivery is delayed in APAC. Engineers are mitigating; next update in 30 minutes.", now),
        )
        connection.execute(
            "INSERT OR REPLACE INTO mock_outages VALUES (?,?,?,?,?,?)",
            ("outage_vpn", "vpn", "Global", 0, "No active VPN outage.", now),
        )
        if connection.execute("SELECT COUNT(*) FROM support_sessions").fetchone()[0] == 0:
            for number in range(18):
                session_id = f"hist_{number:03d}"
                intent = ["password_reset", "vpn_troubleshooting", "mfa_troubleshooting", "unknown"][number % 4]
                escalated = number % 6 == 5 or intent == "unknown"
                started = datetime.now(UTC) - timedelta(days=number % 7, hours=number)
                completed = started + timedelta(seconds=35 + number * 4)
                status = "escalated" if escalated else "resolved"
                connection.execute(
                    "INSERT INTO support_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (session_id, f"usr_{(number % 30)+1:03d}", f"Historical {intent}", f"historical {intent}", intent, status, 0.55 if escalated else 0.91, None, '{}', f"TKT-H{number:03d}" if escalated else None, started.isoformat(), completed.isoformat(), (completed-started).total_seconds()*1000, 0.0002),
                )
                if escalated:
                    diagnostic = json.dumps({"user_issue": f"Historical {intent}", "detected_intent": intent, "confidence": 0.55})
                    connection.execute("INSERT INTO tickets VALUES (?,?,?,?,?,?,?)", (new_id("ticket"), f"TKT-H{number:03d}", session_id, "open", "medium", diagnostic, completed.isoformat()))
                    connection.execute("INSERT INTO escalations VALUES (?,?,?,?,?,?)", (new_id("esc"), session_id, f"TKT-H{number:03d}", "Historical low confidence", "Support agent review", completed.isoformat()))
                else:
                    connection.execute("INSERT INTO resolutions VALUES (?,?,?,?,?,?,?)", (new_id("res"), session_id, "automated", "Historical verified resolution", 1, 1, completed.isoformat()))
                connection.execute("INSERT INTO model_usage VALUES (?,?,?,?,?,?,?,?,?)", (new_id("usage"), session_id, "mock", "deterministic-v1", 24, 32, 0.0002, 2.0, completed.isoformat()))
            connection.execute(
                "INSERT INTO reopen_events VALUES (?,?,?,?)",
                (new_id("reopen"), "hist_004", "Issue recurred during replay window", (datetime.now(UTC) - timedelta(hours=12)).isoformat()),
            )
            connection.execute("UPDATE resolutions SET strict_deflected=0 WHERE session_id='hist_004'")
    return {
        "users": db.fetchone("SELECT COUNT(*) AS n FROM users")["n"],
        "knowledge_documents": db.fetchone("SELECT COUNT(*) AS n FROM knowledge_documents")["n"],
        "historical_sessions": db.fetchone("SELECT COUNT(*) AS n FROM support_sessions")["n"],
    }
