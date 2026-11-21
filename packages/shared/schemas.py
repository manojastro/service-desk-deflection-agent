from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Role(StrEnum):
    EMPLOYEE = "employee"
    SUPPORT_AGENT = "support_agent"
    ADMIN = "admin"


class Intent(StrEnum):
    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    VPN = "vpn_troubleshooting"
    MFA = "mfa_troubleshooting"
    SOFTWARE_ACCESS = "software_access_request"
    NETWORK = "wifi_network_troubleshooting"
    OUTAGE = "known_outage_lookup"
    KNOWLEDGE = "knowledge_question"
    UNKNOWN = "unknown"


class SessionStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class Citation(BaseModel):
    document_id: str
    title: str
    excerpt: str
    score: float = Field(ge=0, le=1)


class PendingAction(BaseModel):
    tool: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    description: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class ConfirmationRequest(BaseModel):
    approved: bool


class ChatResponse(BaseModel):
    session_id: str
    status: SessionStatus
    intent: Intent
    reply: str
    confidence: float = Field(ge=0, le=1)
    citations: list[Citation] = Field(default_factory=list)
    requires_confirmation: bool = False
    pending_action: PendingAction | None = None
    ticket_id: str | None = None
    resolved: bool = False
    deflected: bool = False


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Role
    display_name: str


class UserContext(BaseModel):
    id: str
    username: str
    display_name: str
    role: Role
    department: str


class ToolResult(BaseModel):
    success: bool
    message: str
    data: dict[str, Any] = Field(default_factory=dict)


class AgentTraceEvent(BaseModel):
    state: str
    decision: str
    duration_ms: float
    at: str
    safe_metadata: dict[str, Any] = Field(default_factory=dict)

