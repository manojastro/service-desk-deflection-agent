# Architecture

## Goals

The POC optimizes for safe, measurable support outcomes: evidence precedes answers, mutations require confirmation, every tool call is allowlisted and auditable, and unresolved work reaches a human with useful context.

## Runtime components

The React client contains two experiences: employee support and the operations cockpit. FastAPI authenticates seeded local identities, enforces role checks, validates Pydantic payloads, assigns request IDs, applies an in-memory per-client rate window, and exposes health/readiness/metrics.

`ServiceDeskAgent` owns orchestration. Its state is typed, nodes are explicit, graph recursion is bounded, and the saved operational trace contains states, decisions, timing, evidence, tools, confidence, and outcome—never hidden model chain-of-thought. LangGraph is the normal runtime; a matching bounded sequential fallback keeps minimal offline environments deterministic.

`HybridRetriever` chunks approved synthetic SOPs and combines a BM25-style overlap signal, lexical-vector cosine similarity, and intent agreement. It filters tenant and role metadata before ranking. A query without sufficient evidence is escalated rather than completed from model memory.

`ToolRegistry` is an allowlist and authorization boundary. It enforces role, ownership, and confirmation, redacts sensitive arguments before persistence, measures duration, and records audit events. A deployment can replace `MockITSMAdapter` with Jira Service Management or ServiceNow implementations.

SQLite provides a zero-credential demo datastore. The migration covers users, sessions, messages, intents, knowledge, evidence, tool execution, resolution, escalation, tickets, reopen events, model usage, and audit. PostgreSQL and Qdrant are declared in Compose as the production migration targets; their adapter wiring is called out as a hardening gap.

## Data flow

1. The authenticated employee submits a validated support request.
2. The API persists a session and user message, then invokes the bounded graph.
3. The graph classifies the request and retrieves role-permitted, approved evidence.
4. Policy rejects unsafe, unknown, unsupported, or weakly grounded plans.
5. Read-only tools may run immediately. State-changing tools pause and serialize the exact pending action.
6. A later confirmation request reauthorizes the same user and executes the stored allowlisted action.
7. Tool success is verified, confidence is calculated, and the interaction resolves or escalates.
8. Resolution/ticket, usage, evidence, tool, trace, and audit records feed the dashboard.

## Reliability choices

- Deterministic mock provider for CI and demos.
- Maximum graph recursion and no model-generated shell or dynamic tool names.
- Transactions per repository operation with foreign keys enabled.
- Idempotent migration and seed.
- External-provider boundaries isolated behind adapters.
- Readiness tests datastore access; request IDs correlate structured HTTP/audit logs.

