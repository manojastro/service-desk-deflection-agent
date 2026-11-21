# Threat Model

## Assets and trust boundaries

Protected assets include employee account state, temporary credentials, software approvals, support content, diagnostic tickets, session history, audit records, tokens, and provider secrets. Boundaries exist between browser/API, API/agent, agent/retrieval, agent/tools, and adapters/external providers.

## Key threats and controls

| Threat | Implemented control | Residual risk / production action |
|---|---|---|
| Prompt injection requests arbitrary actions | Pattern screening, approved-content-only retrieval, fixed intent/tool mapping, allowlisted tools, no shell tool | Add a dedicated injection classifier and adversarial gateway policy |
| Retrieved content contains malicious instructions | Only approved documents are indexed; content is evidence, never an executable tool plan; tenant/role filters run before ranking | Add signed publishing workflow and content provenance checks |
| Unauthorized account mutation | Bearer authentication, RBAC, employee ownership checks, serialized confirmation gate | Integrate enterprise IdP, MFA, short-lived asymmetric tokens, and step-up auth |
| Confirmation replay or confused deputy | Session status must be awaiting confirmation and the stored action is executed; employees can confirm only their own session | Add nonce, expiration, single-use DB transaction, and CSRF protection if cookies are adopted |
| Secret leakage | Environment-only secrets, no secret fields in logs, sensitive tool args removed | Use a secrets manager and automated secret scanning |
| Temporary credential exposure | Returned once in a local demo result; not stored in tool arguments | In production use secure out-of-band reset links, never return passwords in chat |
| Cross-tenant knowledge exposure | Tenant and allowed-role metadata filters | Derive tenant from verified identity and enforce row-level security/vector payload filters |
| Denial of service | Payload limits, graph step bound, per-client rate window | Distributed rate limiting, budgets, timeouts, queues, circuit breakers |
| Audit tampering | Structured append-only audit records for auth, session, tools, confirmations, outcomes | Export to immutable SIEM storage with signing and retention controls |
| XSS/data disclosure | React output encoding, validated payloads, Nginx security headers, safe trace field selection | Add CSP nonces, dependency scanning, browser security regression tests |
| External adapter compromise | Mock default, explicit interfaces, no arbitrary URLs from model output | Egress allowlists, mTLS, credential scoping, retries/idempotency keys |

## Explicit non-capabilities

The agent cannot run shell commands, choose arbitrary HTTP destinations, install software directly, change another employee's state, bypass confirmation, read unapproved knowledge, or expose hidden model reasoning.

