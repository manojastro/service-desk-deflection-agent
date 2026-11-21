# Production Gaps

This repository is a locally runnable POC, not a production authorization system.

## Highest-priority hardening

1. Replace local HMAC authentication with enterprise OIDC/SAML, SCIM role mapping, step-up authentication, asymmetric token validation, and centralized session revocation.
2. Implement PostgreSQL repositories with migrations, connection pooling, row-level tenant security, transactionally consumed confirmation nonces, and encrypted sensitive columns.
3. Implement Qdrant ingestion/retrieval with approved-document lifecycle, payload authorization filters, embedding versioning, tombstones, and relevance monitoring.
4. Complete Jira Service Management and ServiceNow adapters with scoped credentials, field mappings, idempotency keys, retries, timeouts, circuit breaking, and reconciliation.
5. Replace returned temporary passwords with expiring out-of-band identity-provider reset links.
6. Move rate limits, graph checkpoints, and locks to Redis or another shared durable store; add queues and cancellation for long-running tools.
7. Add an approval service for privileged/licensed access, separation of duties, and policy-as-code review.
8. Export OpenTelemetry traces and immutable audit events to the organization's observability/SIEM stack; define alerts and SLOs.
9. Add signed knowledge publishing, DLP/PII controls, retention/deletion workflows, prompt-injection scanning, and red-team regression sets.
10. Run load, chaos, accessibility, cross-browser, disaster-recovery, penetration, and privacy testing; produce SBOMs and signed images.

## POC-specific limitations

- SQLite and in-process lexical-vector retrieval are the active demo adapters; Compose PostgreSQL and Qdrant are not yet wired into request processing.
- Rate limiting is per API process and resets on restart.
- The deterministic classifier covers the seeded intent vocabulary; production language variability needs a calibrated model plus monitoring.
- Strict deflection is set at verified resolution and cleared by seeded reopen events; a production scheduler must finalize the metric after the replay window.
- Local audit data is mutable by a host administrator.
- The OpenAI-compatible provider adapter expects JSON output but needs deployment-specific schema enforcement, retries, budgets, and safety review.

