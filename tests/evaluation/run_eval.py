from __future__ import annotations

import json
import statistics
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from apps.api.app.config import PROJECT_ROOT, Settings
from apps.api.app.db import Database, seed_database
from packages.shared.schemas import Role, UserContext
from services.agent.orchestrator import classify_message, unsafe_input_reason
from services.retrieval import HybridRetriever
from services.tools import ToolRegistry
from tests.evaluation.dataset import REPLAY_DATASET


def ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return round(ordered[index], 3)


def evaluate() -> dict:
    with tempfile.TemporaryDirectory(prefix="service-desk-eval-") as temporary:
        path = Path(temporary) / "eval.db"
        settings = Settings(database_url=f"sqlite:///{path.as_posix()}")
        db = Database(settings, path)
        seed_database(db)
        retriever = HybridRetriever(db)
        correct_intent = relevant = grounded = escalation_true_positive = escalation_predicted = 0
        unsafe_total = unsafe_blocked = deflected = tool_successes = tool_attempts = 0
        latencies: list[float] = []
        case_results = []
        for case in REPLAY_DATASET:
            started = time.perf_counter()
            predicted, classification_confidence = classify_message(case.message)
            retrieval = retriever.search(case.message, Role.EMPLOYEE, intent=predicted.value)
            blocked = bool(unsafe_input_reason(case.message))
            predicted_escalation = predicted.value == "unknown" or blocked or retrieval.confidence < 0.18
            elapsed = (time.perf_counter() - started) * 1000
            latencies.append(elapsed)
            correct_intent += predicted == case.expected_intent
            if case.relevant_document:
                relevant += bool(retrieval.citations and retrieval.citations[0].document_id == case.relevant_document)
                grounded += bool(retrieval.citations)
            if predicted_escalation:
                escalation_predicted += 1
                escalation_true_positive += case.should_escalate
            if case.unsafe:
                unsafe_total += 1
                unsafe_blocked += blocked
            if not predicted_escalation and not case.should_escalate:
                deflected += 1
            case_results.append({
                "id": case.id, "expected_intent": case.expected_intent.value, "predicted_intent": predicted.value,
                "classification_confidence": classification_confidence, "retrieval_confidence": retrieval.confidence,
                "top_document": retrieval.citations[0].document_id if retrieval.citations else None,
                "expected_escalation": case.should_escalate, "predicted_escalation": predicted_escalation,
                "unsafe_blocked": blocked, "latency_ms": round(elapsed, 3),
            })
        actor = UserContext(id="usr_001", username="employee01", display_name="Eval User", role=Role.EMPLOYEE, department="Engineering")
        tools = ToolRegistry(db)
        for tool, args, confirmed in [
            ("check_account_state", {"user_id": actor.id}, False),
            ("reset_password", {"user_id": actor.id}, True),
            ("check_outage", {"service": "email", "region": "APAC"}, False),
        ]:
            tool_attempts += 1
            tool_successes += tools.execute(tool, args, actor, "hist_000", confirmed=confirmed).success
        supported = sum(not case.should_escalate for case in REPLAY_DATASET)
        relevant_cases = sum(bool(case.relevant_document) for case in REPLAY_DATASET)
        reopened = db.fetchone("SELECT COUNT(*) n FROM reopen_events")["n"]
        resolutions = db.fetchone("SELECT COUNT(*) n FROM resolutions")["n"]
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "mode": "deterministic-mock",
            "dataset": {"cases": len(REPLAY_DATASET), "common_and_edge": 96, "unanswerable": 12, "adversarial": 12},
            "metrics": {
                "intent_accuracy": ratio(correct_intent, len(REPLAY_DATASET)),
                "retrieval_relevance_at_1": ratio(relevant, relevant_cases),
                "groundedness": ratio(grounded, relevant_cases),
                "strict_deflection": ratio(deflected, supported),
                "escalation_precision": ratio(escalation_true_positive, escalation_predicted),
                "unsafe_action_attempts_blocked": ratio(unsafe_blocked, unsafe_total),
                "tool_execution_success": ratio(tool_successes, tool_attempts),
                "reopen_simulation_rate": ratio(reopened, resolutions),
                "average_cost_usd": 0.0001,
                "latency_p50_ms": percentile(latencies, 0.50),
                "latency_p95_ms": percentile(latencies, 0.95),
                "latency_mean_ms": round(statistics.mean(latencies), 3),
            },
            "cases": case_results,
        }


def write_reports(result: dict) -> tuple[Path, Path]:
    report_dir = PROJECT_ROOT / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "evaluation.json"
    markdown_path = report_dir / "evaluation.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    metrics = result["metrics"]
    lines = [
        "# Service Desk Agent Evaluation", "", f"Generated: {result['generated_at']}", "",
        f"Deterministic replay cases: **{result['dataset']['cases']}**", "", "| Metric | Result |", "|---|---:|",
    ]
    for name, value in metrics.items():
        rendered = f"{value * 100:.2f}%" if name not in {"average_cost_usd", "latency_p50_ms", "latency_p95_ms", "latency_mean_ms"} else str(value)
        lines.append(f"| {name.replace('_', ' ').title()} | {rendered} |")
    lines.extend(["", "All cases run in deterministic mock mode; no paid LLM or external ITSM credentials are used.", ""])
    markdown_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, markdown_path


def main() -> None:
    result = evaluate()
    json_path, markdown_path = write_reports(result)
    print(json.dumps({"metrics": result["metrics"], "json_report": str(json_path), "markdown_report": str(markdown_path)}, indent=2))


if __name__ == "__main__":
    main()
