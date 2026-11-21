from __future__ import annotations

import json
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable

from apps.api.app.db import Database, new_id, utcnow
from packages.shared.schemas import Role, ToolResult, UserContext
from services.tools.adapters import ITSMAdapter, MockITSMAdapter


class ToolPolicyError(PermissionError):
    pass


@dataclass(frozen=True)
class ToolDefinition:
    handler: Callable[..., ToolResult]
    state_changing: bool
    allowed_roles: frozenset[Role]


class ToolRegistry:
    def __init__(self, db: Database, itsm: ITSMAdapter | None = None):
        self.db = db
        self.itsm = itsm or MockITSMAdapter()
        employee_roles = frozenset(Role)
        self.tools: dict[str, ToolDefinition] = {
            "reset_password": ToolDefinition(self._reset_password, True, employee_roles),
            "unlock_account": ToolDefinition(self._unlock_account, True, employee_roles),
            "check_outage": ToolDefinition(self._check_outage, False, employee_roles),
            "check_account_state": ToolDefinition(self._check_account_state, False, employee_roles),
            "check_vpn_profile": ToolDefinition(self._check_vpn_profile, False, employee_roles),
            "submit_software_access_request": ToolDefinition(self._submit_software_access_request, True, employee_roles),
            "create_itsm_ticket": ToolDefinition(self._create_itsm_ticket, True, frozenset({Role.SUPPORT_AGENT, Role.ADMIN})),
        }

    def is_state_changing(self, tool_name: str) -> bool:
        definition = self.tools.get(tool_name)
        if not definition:
            raise ToolPolicyError(f"Tool {tool_name!r} is not allowlisted")
        return definition.state_changing

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        actor: UserContext,
        session_id: str,
        confirmed: bool = False,
        system_call: bool = False,
    ) -> ToolResult:
        definition = self.tools.get(tool_name)
        if not definition:
            raise ToolPolicyError(f"Tool {tool_name!r} is not allowlisted")
        if not system_call and actor.role not in definition.allowed_roles:
            raise ToolPolicyError(f"Role {actor.role} cannot execute {tool_name}")
        if definition.state_changing and not (confirmed or system_call):
            raise ToolPolicyError(f"Tool {tool_name} requires explicit confirmation")
        target_user = arguments.get("user_id")
        if not system_call and actor.role == Role.EMPLOYEE and target_user and target_user != actor.id:
            raise ToolPolicyError("Employees can act only on their own account")
        started = time.perf_counter()
        try:
            result = definition.handler(**arguments)
        except Exception as exc:
            result = ToolResult(success=False, message="Approved tool execution failed", data={"error": type(exc).__name__})
        duration_ms = (time.perf_counter() - started) * 1000
        safe_args = {key: value for key, value in arguments.items() if key not in {"password", "token", "secret"}}
        self.db.execute(
            "INSERT INTO tool_executions VALUES (?,?,?,?,?,?,?,?,?)",
            (
                new_id("tool"), session_id, tool_name, json.dumps(safe_args, sort_keys=True),
                result.model_dump_json(), int(result.success), duration_ms,
                actor.id if confirmed else None, utcnow(),
            ),
        )
        self.db.insert_audit("tool_execution", "success" if result.success else "failure", session_id, actor.id, metadata={"tool": tool_name, "duration_ms": round(duration_ms, 3)})
        return result

    def _reset_password(self, user_id: str) -> ToolResult:
        account = self.db.fetchone("SELECT * FROM mock_accounts WHERE user_id=?", (user_id,))
        if not account:
            return ToolResult(success=False, message="Directory account not found")
        temporary = f"Tmp-{secrets.token_hex(3)}!"
        self.db.execute(
            "UPDATE mock_accounts SET password_version=password_version+1,last_password_reset=? WHERE user_id=?",
            (utcnow(), user_id),
        )
        updated = self.db.fetchone("SELECT password_version FROM mock_accounts WHERE user_id=?", (user_id,))
        return ToolResult(success=True, message="Password reset verified; a change is required at next sign-in.", data={"temporary_password": temporary, "password_version": updated["password_version"], "force_change": True})

    def _unlock_account(self, user_id: str) -> ToolResult:
        account = self.db.fetchone("SELECT * FROM mock_accounts WHERE user_id=?", (user_id,))
        if not account:
            return ToolResult(success=False, message="Directory account not found")
        self.db.execute("UPDATE mock_accounts SET locked=0 WHERE user_id=?", (user_id,))
        return ToolResult(success=True, message="Account unlock verified.", data={"locked": False})

    def _check_account_state(self, user_id: str) -> ToolResult:
        account = self.db.fetchone("SELECT * FROM mock_accounts WHERE user_id=?", (user_id,))
        return ToolResult(success=bool(account), message="Account state retrieved." if account else "Account not found.", data=account or {})

    def _check_vpn_profile(self, user_id: str) -> ToolResult:
        profile = self.db.fetchone("SELECT * FROM mock_vpn_profiles WHERE user_id=?", (user_id,))
        healthy = bool(profile and profile["assigned"] and profile["certificate_valid"])
        return ToolResult(success=healthy, message="VPN profile is healthy." if healthy else "VPN profile needs Network Operations review.", data=profile or {})

    def _check_outage(self, service: str = "all", region: str = "Global") -> ToolResult:
        rows = self.db.fetchall("SELECT * FROM mock_outages WHERE active=1")
        matches = [row for row in rows if service == "all" or service.lower() in row["service"].lower()]
        return ToolResult(success=True, message=matches[0]["message"] if matches else "No matching active outage was found.", data={"active_outages": matches, "query_region": region})

    def _submit_software_access_request(self, user_id: str, software: str) -> ToolResult:
        request_id = new_id("SWR")
        return ToolResult(success=True, message=f"Software access request {request_id} submitted for approval.", data={"request_id": request_id, "software": software, "status": "pending_approval", "user_id": user_id})

    def _create_itsm_ticket(self, diagnostic_summary: dict[str, Any]) -> ToolResult:
        external_id = self.itsm.create_ticket(diagnostic_summary)
        return ToolResult(success=True, message=f"ITSM ticket {external_id} created.", data={"external_id": external_id})
