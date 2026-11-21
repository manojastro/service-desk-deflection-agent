# API Guide

Interactive OpenAPI is served at `/docs`; the raw schema is `/openapi.json`.

## Authentication

`POST /api/auth/login` accepts `username` and `password`, returning a signed local bearer token. Send `Authorization: Bearer <token>` on protected routes. The demo token is HMAC-signed and expires after eight hours.

## Employee routes

- `POST /api/chat` — start a support session with `{ "message": "..." }`.
- `POST /api/chat/{session_id}/confirm` — continue a paused session with `{ "approved": true|false }`.
- `GET /api/sessions/{session_id}/trace` — owner-visible safe operational trace.
- `GET /api/users/me` — current identity and role.

`POST /api/chat` returns intent, status, user-facing reply, confidence, approved citations, confirmation requirements, pending action description, ticket ID, and resolution/deflection flags.

## Operations routes

- `GET /api/dashboard` — support-agent/admin summary and distributions.
- `GET /api/tickets` — latest diagnostic tickets.
- `GET /api/sessions/{session_id}/trace` — full safe trace for authorized operations roles.

## Platform routes

- `GET /health` — process liveness.
- `GET /ready` — database readiness and active model provider.
- `GET /metrics` — Prometheus text exposition.

Every response contains `X-Request-ID`. Clients may provide an `X-Request-ID` of at most 80 characters. Errors use FastAPI's `{ "detail": ... }` envelope.

