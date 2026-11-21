from __future__ import annotations

import json
import re
import time
from datetime import UTC, datetime
from typing import Any, Callable, TypedDict

from apps.api.app.config import Settings, get_settings
from apps.api.app.db import Database, new_id, utcnow
from packages.shared.schemas import (
    AgentTraceEvent,
    ChatResponse,
    Citation,
    Intent,
    PendingAction,
    Role,
    SessionStatus,
    ToolResult,
    UserContext,
)
from services.agent.providers import LLMProvider, provider_for
from services.retrieval import HybridRetriever
from services.tools import ToolRegistry
from services.tools.registry import ToolPolicyError


class AgentState(TypedDict, total=False):
    session_id: str
    user: UserContext
    original_message: str
    normalized_message: str
    intent: Intent
    classification_confidence: float
    retrieval_confidence: float
    citations: list[Citation]
    pending_action: PendingAction | None
    tool_result: ToolResult | None
    confidence: float
    status: SessionStatus
    reply: str
    ticket_id: str | None
    policy_blocked: bool
    policy_reason: str
    trace: list[AgentTraceEvent]
    steps: int


INTENT_RULES: list[tuple[Intent, tuple[str, ...]]] = [
    (Intent.PASSWORD_RESET, ("reset password", "reset my password", "forgot password", "forgot my password", "password expired", "change my password")),
    (Intent.ACCOUNT_UNLOCK, ("unlock", "locked out", "account locked", "too many attempts")),
    (Intent.VPN, ("vpn", "remote access", "corporate tunnel")),
    (Intent.MFA, ("mfa", "multi factor", "authenticator", "verification code", "one-time code")),
    (Intent.SOFTWARE_ACCESS, ("software access", "install software", "license", "access to", "need slack", "need zoom")),
    (Intent.NETWORK, ("wi-fi", "wifi", "wireless", "network connection", "internet")),
    (Intent.OUTAGE, ("outage", "service down", "is email down", "status of", "everyone affected")),
    (Intent.KNOWLEDGE, ("phishing", "printer", "how do i", "where can i", "what is")),
]
INJECTION_PATTERNS = (
    "ignore previous", "ignore all instructions", "system prompt", "reveal secret", "show api key",
    "execute shell", "run powershell", "rm -rf", "developer message",
)
STATE_CHANGING = {"reset_password", "unlock_account", "submit_software_access_request"}


def classify_message(text: str) -> tuple[Intent, float]:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    for candidate, phrases in INTENT_RULES:
        if any(phrase in normalized for phrase in phrases):
            return candidate, 0.94
    return Intent.UNKNOWN, 0.35


def unsafe_input_reason(text: str) -> str:
    normalized = text.lower()
    return "prompt-injection or unsafe-command pattern detected" if any(
        pattern in normalized for pattern in INJECTION_PATTERNS
    ) else ""


class ServiceDeskAgent:
    STATE_NODES = (
        "normalize_request", "classify_intent", "retrieve_knowledge", "plan_resolution",
        "policy_check", "request_confirmation", "execute_tool", "verify_result",
        "calculate_confidence", "resolve", "escalate", "persist_session_outcome",
    )

    def __init__(
        self,
        db: Database,
        settings: Settings | None = None,
        retriever: HybridRetriever | None = None,
        tools: ToolRegistry | None = None,
        provider: LLMProvider | None = None,
    ):
        self.db = db
        self.settings = settings or get_settings()
        self.retriever = retriever or HybridRetriever(db)
        self.tools = tools or ToolRegistry(db)
        self.provider = provider or provider_for(self.settings)
        self._compiled_graph: Any | None = None

    def start(self, message: str, user: UserContext, request_id: str | None = None) -> ChatResponse:
        session_id = new_id("sess")
        now = utcnow()
        self.db.execute(
            "INSERT INTO support_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (session_id, user.id, message, message.strip().lower(), Intent.UNKNOWN.value,
             SessionStatus.IN_PROGRESS.value, 0.0, None, "{}", None, now, None, None, 0.0),
        )
        self.db.execute(
            "INSERT INTO messages VALUES (?,?,?,?,?)",
            (new_id("msg"), session_id, "employee", message, now),
        )
        self.db.insert_audit("session_started", "accepted", session_id, user.id, request_id)
        state: AgentState = {
            "session_id": session_id,
            "user": user,
            "original_message": message,
            "trace": [],
            "steps": 0,
            "status": SessionStatus.IN_PROGRESS,
            "intent": Intent.UNKNOWN,
            "citations": [],
            "confidence": 0.0,
            "policy_blocked": False,
        }
        final_state = self._run_graph(state)
        return self._response(final_state)

    def confirm(self, session_id: str, approved: bool, user: UserContext) -> ChatResponse:
        row = self.db.fetchone("SELECT * FROM support_sessions WHERE id=?", (session_id,))
        if not row:
            raise KeyError("Support session not found")
        if row["user_id"] != user.id and user.role == Role.EMPLOYEE:
            raise PermissionError("Employees can confirm only their own session")
        if row["status"] != SessionStatus.AWAITING_CONFIRMATION.value:
            raise ValueError("Session is not awaiting confirmation")
        state = self._deserialize_state(row["state_json"], user)
        if not approved:
            state["status"] = SessionStatus.CANCELLED
            state["reply"] = "Action cancelled. No account or request state was changed."
            self._trace(state, "request_confirmation", "employee declined the proposed action")
            self._persist_session_outcome(state)
            self.db.insert_audit("action_confirmation", "declined", session_id, user.id)
            return self._response(state)
        self.db.insert_audit("action_confirmation", "approved", session_id, user.id)
        self._execute_tool(state, confirmed=True)
        self._verify_result(state)
        self._calculate_confidence(state)
        if state.get("tool_result") and state["tool_result"].success and state["confidence"] >= 0.60:
            self._resolve(state)
        else:
            self._escalate(state)
        self._persist_session_outcome(state)
        return self._response(state)

    def _run_graph(self, state: AgentState) -> AgentState:
        try:
            graph = self._get_langgraph()
        except ImportError:
            graph = None
        if graph is not None:
            return graph.invoke(state, {"recursion_limit": self.settings.max_agent_steps + 4})
        # Minimal-environment fallback follows the exact graph order and bounded routing.
        for node in (self._normalize_request, self._classify_intent, self._retrieve_knowledge,
                     self._plan_resolution, self._policy_check):
            self._guard_steps(state)
            node(state)
        route = self._route_after_policy(state)
        if route == "request_confirmation":
            self._request_confirmation(state)
            return state
        if route == "escalate":
            self._escalate(state)
            self._persist_session_outcome(state)
            return state
        if route == "execute_tool":
            self._execute_tool(state)
            self._verify_result(state)
        self._calculate_confidence(state)
        if self._route_after_confidence(state) == "resolve":
            self._resolve(state)
        else:
            self._escalate(state)
        self._persist_session_outcome(state)
        return state

    def _get_langgraph(self) -> Any:
        if self._compiled_graph is not None:
            return self._compiled_graph
        from langgraph.graph import END, START, StateGraph

        graph = StateGraph(AgentState)
        graph.add_node("normalize_request", self._normalize_request)
        graph.add_node("classify_intent", self._classify_intent)
        graph.add_node("retrieve_knowledge", self._retrieve_knowledge)
        graph.add_node("plan_resolution", self._plan_resolution)
        graph.add_node("policy_check", self._policy_check)
        graph.add_node("request_confirmation", self._request_confirmation)
        graph.add_node("execute_tool", self._execute_tool)
        graph.add_node("verify_result", self._verify_result)
        graph.add_node("calculate_confidence", self._calculate_confidence)
        graph.add_node("resolve", self._resolve)
        graph.add_node("escalate", self._escalate)
        graph.add_node("persist_session_outcome", self._persist_session_outcome)
        graph.add_edge(START, "normalize_request")
        graph.add_edge("normalize_request", "classify_intent")
        graph.add_edge("classify_intent", "retrieve_knowledge")
        graph.add_edge("retrieve_knowledge", "plan_resolution")
        graph.add_edge("plan_resolution", "policy_check")
        graph.add_conditional_edges("policy_check", self._route_after_policy, {
            "request_confirmation": "request_confirmation", "execute_tool": "execute_tool",
            "calculate_confidence": "calculate_confidence", "escalate": "escalate",
        })
        graph.add_edge("request_confirmation", END)
        graph.add_edge("execute_tool", "verify_result")
        graph.add_edge("verify_result", "calculate_confidence")
        graph.add_conditional_edges("calculate_confidence", self._route_after_confidence, {
            "resolve": "resolve", "escalate": "escalate",
        })
        graph.add_edge("resolve", "persist_session_outcome")
        graph.add_edge("escalate", "persist_session_outcome")
        graph.add_edge("persist_session_outcome", END)
        self._compiled_graph = graph.compile()
        return self._compiled_graph

    def _guard_steps(self, state: AgentState) -> None:
        state["steps"] = state.get("steps", 0) + 1
        if state["steps"] > self.settings.max_agent_steps:
            state["policy_blocked"] = True
            state["policy_reason"] = "maximum agent step count reached"
            raise RuntimeError("Maximum agent step count reached")

    def _node(self, state: AgentState, name: str, decision: str, started: float, metadata: dict[str, Any] | None = None) -> AgentState:
        self._trace(state, name, decision, (time.perf_counter() - started) * 1000, metadata)
        return state

    def _trace(self, state: AgentState, name: str, decision: str, duration_ms: float = 0.0, metadata: dict[str, Any] | None = None) -> None:
        state.setdefault("trace", []).append(AgentTraceEvent(state=name, decision=decision, duration_ms=round(duration_ms, 3), at=utcnow(), safe_metadata=metadata or {}))

    def _normalize_request(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        normalized = re.sub(r"\s+", " ", state["original_message"].strip().lower())
        state["normalized_message"] = normalized
        return self._node(state, "normalize_request", "input normalized and validated", started, {"characters": len(normalized)})

    def _classify_intent(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        text = state["normalized_message"]
        intent, confidence = classify_message(text)
        state["intent"], state["classification_confidence"] = intent, confidence
        usage = self.provider.structured("Classify only approved IT support intents.", text, "IntentClassification")
        self.db.execute(
            "INSERT INTO model_usage VALUES (?,?,?,?,?,?,?,?,?)",
            (new_id("usage"), state["session_id"], self.settings.llm_provider,
             self.settings.llm_model if self.settings.llm_provider != "mock" else "deterministic-v1",
             usage.input_tokens, usage.output_tokens, usage.cost_usd, usage.latency_ms, utcnow()),
        )
        return self._node(state, "classify_intent", f"classified as {intent.value}", started, {"confidence": confidence})

    def _retrieve_knowledge(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        result = self.retriever.search(state["normalized_message"], state["user"].role, intent=state["intent"].value)
        state["citations"] = result.citations
        state["retrieval_confidence"] = result.confidence
        for rank, citation in enumerate(result.citations, 1):
            self.db.execute(
                "INSERT INTO retrieval_evidence VALUES (?,?,?,?,?,?,?,?,?)",
                (new_id("evidence"), state["session_id"], citation.document_id, rank,
                 citation.score, citation.score, citation.score, citation.excerpt, result.latency_ms),
            )
        return self._node(state, "retrieve_knowledge", f"retrieved {len(result.citations)} approved sources", started, {"confidence": result.confidence, "latency_ms": round(result.latency_ms, 3)})

    def _plan_resolution(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        user_id = state["user"].id
        action: PendingAction | None = None
        intent = state["intent"]
        if intent == Intent.PASSWORD_RESET:
            action = PendingAction(tool="reset_password", arguments={"user_id": user_id}, description="Reset your directory password and issue a temporary credential")
        elif intent == Intent.ACCOUNT_UNLOCK:
            action = PendingAction(tool="unlock_account", arguments={"user_id": user_id}, description="Unlock your directory account")
        elif intent == Intent.SOFTWARE_ACCESS:
            software = self._extract_software(state["normalized_message"])
            action = PendingAction(tool="submit_software_access_request", arguments={"user_id": user_id, "software": software}, description=f"Submit an access request for {software}")
        elif intent == Intent.VPN:
            action = PendingAction(tool="check_vpn_profile", arguments={"user_id": user_id}, description="Check your assigned VPN profile and certificate")
        elif intent == Intent.OUTAGE:
            action = PendingAction(tool="check_outage", arguments={"service": self._extract_service(state["normalized_message"]), "region": "APAC"}, description="Check authoritative active outage records")
        state["pending_action"] = action
        return self._node(state, "plan_resolution", f"planned {action.tool if action else 'knowledge-only response'}", started)

    def _policy_check(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        text = state["normalized_message"]
        reason = ""
        if unsafe_input_reason(text):
            reason = unsafe_input_reason(text)
        elif state["intent"] == Intent.UNKNOWN:
            reason = "unsupported or unknown issue"
        elif not state["citations"] or state.get("retrieval_confidence", 0) < 0.18:
            reason = "insufficient approved knowledge evidence"
        action = state.get("pending_action")
        if action and action.tool not in self.tools.tools:
            reason = "planned tool is not allowlisted"
        state["policy_blocked"] = bool(reason)
        state["policy_reason"] = reason
        return self._node(state, "policy_check", f"blocked: {reason}" if reason else "policy checks passed", started)

    def _route_after_policy(self, state: AgentState) -> str:
        if state.get("policy_blocked"):
            return "escalate"
        action = state.get("pending_action")
        if not action:
            return "calculate_confidence"
        return "request_confirmation" if action.tool in STATE_CHANGING else "execute_tool"

    def _request_confirmation(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        action = state["pending_action"]
        state["status"] = SessionStatus.AWAITING_CONFIRMATION
        state["reply"] = f"Please confirm: {action.description}. No change will occur until you approve."
        self._node(state, "request_confirmation", "explicit confirmation required before state change", started, {"tool": action.tool})
        self._save_state(state)
        self.db.execute(
            "UPDATE support_sessions SET status=?,detected_intent=?,confidence=?,pending_action_json=? WHERE id=?",
            (state["status"].value, state["intent"].value, state.get("confidence", state["classification_confidence"]), action.model_dump_json(), state["session_id"]),
        )
        self.db.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (new_id("msg"), state["session_id"], "agent", state["reply"], utcnow()))
        return state

    def _execute_tool(self, state: AgentState, confirmed: bool = False) -> AgentState:
        started = time.perf_counter()
        action = state.get("pending_action")
        if not action:
            return self._node(state, "execute_tool", "no tool required", started)
        try:
            state["tool_result"] = self.tools.execute(action.tool, action.arguments, state["user"], state["session_id"], confirmed=confirmed)
            decision = f"{action.tool} returned {'success' if state['tool_result'].success else 'failure'}"
        except ToolPolicyError as exc:
            state["tool_result"] = ToolResult(success=False, message="Action blocked by tool policy", data={"policy": str(exc)})
            decision = "tool execution blocked by policy"
        return self._node(state, "execute_tool", decision, started, {"tool": action.tool})

    def _verify_result(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        result = state.get("tool_result")
        verified = bool(result and result.success)
        return self._node(state, "verify_result", "tool outcome verified" if verified else "tool outcome could not be verified", started, {"verified": verified})

    def _calculate_confidence(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        classification = state.get("classification_confidence", 0)
        retrieval = state.get("retrieval_confidence", 0)
        tool_component = 0.1 if state.get("tool_result") and state["tool_result"].success else 0.0
        confidence = min(0.99, 0.60 * classification + 0.30 * retrieval + tool_component)
        state["confidence"] = round(confidence, 4)
        return self._node(state, "calculate_confidence", "combined classification, evidence, and verification signals", started, {"confidence": state["confidence"]})

    def _route_after_confidence(self, state: AgentState) -> str:
        result = state.get("tool_result")
        if result is not None and not result.success:
            return "escalate"
        return "resolve" if state.get("confidence", 0) >= 0.60 else "escalate"

    def _resolve(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        result = state.get("tool_result")
        if result:
            reply = result.message
            if result.data.get("temporary_password"):
                reply += f" Temporary password: {result.data['temporary_password']} (change it immediately)."
        else:
            reply = self._knowledge_reply(state)
        state["status"] = SessionStatus.RESOLVED
        state["reply"] = reply
        state["ticket_id"] = None
        return self._node(state, "resolve", "request resolved and outcome verified", started)

    def _escalate(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        evidence = [citation.model_dump() for citation in state.get("citations", [])]
        tool_rows = self.db.fetchall("SELECT tool_name,result_json,success FROM tool_executions WHERE session_id=?", (state["session_id"],))
        diagnostic = {
            "user_issue": state["original_message"],
            "detected_intent": state["intent"].value,
            "troubleshooting_performed": [event.decision for event in state.get("trace", []) if event.state in {"retrieve_knowledge", "execute_tool", "verify_result"}],
            "knowledge_references": evidence,
            "tool_calls_and_results": tool_rows,
            "confidence": state.get("confidence", state.get("classification_confidence", 0)),
            "policy_reason": state.get("policy_reason", "resolution could not be verified"),
            "recommended_next_action": "Support agent should validate scope, identity, and the attached evidence before any further action.",
        }
        result = self.tools.execute("create_itsm_ticket", {"diagnostic_summary": diagnostic}, state["user"], state["session_id"], confirmed=True, system_call=True)
        ticket_id = result.data["external_id"]
        self.db.execute(
            "INSERT INTO tickets VALUES (?,?,?,?,?,?,?)",
            (new_id("ticket"), ticket_id, state["session_id"], "open", "medium", json.dumps(diagnostic, sort_keys=True), utcnow()),
        )
        self.db.execute(
            "INSERT INTO escalations VALUES (?,?,?,?,?,?)",
            (new_id("esc"), state["session_id"], ticket_id, diagnostic["policy_reason"], diagnostic["recommended_next_action"], utcnow()),
        )
        state["status"] = SessionStatus.ESCALATED
        state["ticket_id"] = ticket_id
        state["reply"] = f"I could not safely resolve this from approved evidence. Ticket {ticket_id} was created with the diagnostic trace."
        return self._node(state, "escalate", "created diagnostic ITSM ticket", started, {"ticket_id": ticket_id})

    def _persist_session_outcome(self, state: AgentState) -> AgentState:
        started = time.perf_counter()
        row = self.db.fetchone("SELECT started_at FROM support_sessions WHERE id=?", (state["session_id"],))
        elapsed = (datetime.now(UTC) - datetime.fromisoformat(row["started_at"])).total_seconds() * 1000
        completed = utcnow()
        self._trace(state, "persist_session_outcome", f"persisted {state['status'].value} outcome")
        self._save_state(state)
        usage = self.db.fetchone("SELECT COALESCE(SUM(cost_usd),0) AS cost FROM model_usage WHERE session_id=?", (state["session_id"],))
        self.db.execute(
            "UPDATE support_sessions SET detected_intent=?,status=?,confidence=?,pending_action_json=NULL,ticket_id=?,completed_at=?,duration_ms=?,cost_usd=? WHERE id=?",
            (state["intent"].value, state["status"].value, state.get("confidence", 0), state.get("ticket_id"), completed, elapsed, usage["cost"], state["session_id"]),
        )
        if state["status"] == SessionStatus.RESOLVED:
            self.db.execute(
                "INSERT OR REPLACE INTO resolutions VALUES (?,?,?,?,?,?,?)",
                (new_id("res"), state["session_id"], "automated", state["reply"], 1, 1, completed),
            )
        self.db.execute("INSERT INTO messages VALUES (?,?,?,?,?)", (new_id("msg"), state["session_id"], "agent", state["reply"], completed))
        self.db.insert_audit("session_outcome", state["status"].value, state["session_id"], state["user"].id, metadata={"confidence": state.get("confidence", 0), "duration_ms": round(elapsed, 3)})
        return self._node(state, "persist_session_outcome", "outcome transaction complete", started)

    def _save_state(self, state: AgentState) -> None:
        serializable = {
            **state,
            "user": state["user"].model_dump(mode="json"),
            "intent": state["intent"].value,
            "status": state["status"].value,
            "citations": [item.model_dump(mode="json") for item in state.get("citations", [])],
            "pending_action": state.get("pending_action").model_dump(mode="json") if state.get("pending_action") else None,
            "tool_result": state.get("tool_result").model_dump(mode="json") if state.get("tool_result") else None,
            "trace": [item.model_dump(mode="json") for item in state.get("trace", [])],
        }
        self.db.execute("UPDATE support_sessions SET state_json=? WHERE id=?", (json.dumps(serializable, sort_keys=True), state["session_id"]))

    def _deserialize_state(self, raw: str, user: UserContext) -> AgentState:
        data = json.loads(raw)
        data["user"] = user
        data["intent"] = Intent(data["intent"])
        data["status"] = SessionStatus(data["status"])
        data["citations"] = [Citation.model_validate(item) for item in data.get("citations", [])]
        data["pending_action"] = PendingAction.model_validate(data["pending_action"]) if data.get("pending_action") else None
        data["tool_result"] = ToolResult.model_validate(data["tool_result"]) if data.get("tool_result") else None
        data["trace"] = [AgentTraceEvent.model_validate(item) for item in data.get("trace", [])]
        return data

    def _response(self, state: AgentState) -> ChatResponse:
        return ChatResponse(
            session_id=state["session_id"], status=state["status"], intent=state["intent"],
            reply=state["reply"], confidence=state.get("confidence", state.get("classification_confidence", 0)),
            citations=state.get("citations", []),
            requires_confirmation=state["status"] == SessionStatus.AWAITING_CONFIRMATION,
            pending_action=state.get("pending_action") if state["status"] == SessionStatus.AWAITING_CONFIRMATION else None,
            ticket_id=state.get("ticket_id"), resolved=state["status"] == SessionStatus.RESOLVED,
            deflected=state["status"] == SessionStatus.RESOLVED,
        )

    def _knowledge_reply(self, state: AgentState) -> str:
        citation = state["citations"][0]
        return f"Based on the approved SOP “{citation.title}”: {citation.excerpt}"

    @staticmethod
    def _extract_service(message: str) -> str:
        for service in ("email", "vpn", "wifi", "network"):
            if service in message:
                return service
        return "all"

    @staticmethod
    def _extract_software(message: str) -> str:
        match = re.search(r"(?:access to|install|license for|need)\s+([a-z0-9 ._-]{2,40})", message)
        return match.group(1).strip().title() if match else "Requested software"
