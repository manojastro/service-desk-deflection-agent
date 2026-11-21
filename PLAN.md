# Service Desk Deflection Agent — Delivery Plan

## Assumptions

- The default, deterministic local profile uses SQLite and an in-process hybrid index so tests and demos do not require paid APIs or external services.
- The production-shaped Docker profile provides PostgreSQL and Qdrant, while adapters keep the primary flow locally runnable when those services or real ITSM credentials are absent.
- LangGraph is used when installed; the checked-in typed graph definition and deterministic runner preserve the same explicit state transitions in minimal test environments.

## Milestones

1. Establish the monorepo, configuration, shared schemas, persistence model, migrations, and seed data.
2. Implement hybrid retrieval, safe support tools, policy/RBAC, and an explicit bounded agent state machine.
3. Expose authenticated FastAPI conversation, confirmation, dashboard, trace, health, metrics, and administration APIs.
4. Build the React/TypeScript employee chat and operations dashboard with citations and safe decision traces.
5. Add deterministic unit, API, integration, evaluation, and Playwright suites with a 100+ case replay dataset.
6. Add Compose, task automation, documentation, and complete final verification.

## Verification gates

- Seeded employee completes a confirmed state-changing resolution.
- Unknown/low-evidence request creates a diagnostic mock ITSM ticket.
- Dashboard and trace endpoints reflect both outcomes.
- Core pytest suite passes without a paid model.
- Evaluation produces JSON and Markdown reports.
- Frontend production build and Compose configuration validate.

