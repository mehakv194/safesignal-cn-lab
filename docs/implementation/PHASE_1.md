# Phase 1 — Individual verified identity and ownership

Date: 19 November 2026. Branch: codex/v2-identity-mobile. Status: PASS for local implementation; not production release approval.

User authorized Phase 1 and Phase 2 together after Gate 0. Phase 2 begins only after this report.

## Implemented and files

- identity.py: exact ASCII enrollment email, Argon2id (64 MiB, time cost 3, parallelism 4), hashed 15-minute single-use verification/reset challenges, generic account recovery, SMTP STARTTLS adapter, captured mail only when explicitly injected in local/tests, server-side opaque sessions (30-minute idle/8-hour absolute), revocation, current-password verified password change, persistent bounded account/IP throttling and redacted security events.
- web.py / identity.html: signup, verify/resend, email/password login, logout, reset/change password, profile; public token login replaced in v2; role and owner checks, CSRF, scoped queue reads, retry denial and student evidence-export denial. Existing report/actions remain.
- server.py: command-bound short-lived HMAC principal context over verified TLS; current account/session lookup; denies token-only access in v2 except service health; scoped reads, actions and queue permissions.
- server_store.py: additive nullable owner column, owner-bound deduplication, scoped list/dashboard/audit and transaction-checked team actions; restricted NULL-owner legacy records; existing payload/hash preserved.
- sender_store.py / sender_worker.py: owner-bound idempotent queue insertion; authoritative durable submission intents reconcile after a crash before enqueue; retained retries and receipts; legacy queue entries not reassigned.
- hosted.py / run_app.py: identity enabled in actual hosted/local single-app entrypoints; consistent pre-v2 SQLite backups before migration; protected service credentials remain separate from human identity. Isolated original labs retain compatibility for networking demonstrations.
- provision_responder.py: maintainer-only local CLI requires already verified eligible account, sets team/optional explicit legacy permission and revokes sessions. No HTTP provisioning route.
- requirements.txt: argon2-cffi 25.1.0. tests/test_identity.py adds identity/privacy/migration/runtime tests; hosted ingress expectation now asserts email login instead of removed token form.

## Tests actually executed

`.venv/Scripts/python.exe -m pytest -q --basetemp=C:/Users/mehak/.codex/visualizations/2026/11/18/01a1eef0-be7d-75d1-b1ed-8f0bbffef830/v2-phase1-final`

**42 passed in 28.67s**, exit 0. Earlier intermediate run: 40 passed in 29.56s; two further runtime/mail tests added before final run.

Includes exact email rejection, unverified/wrong role/password denial, token expiry/reuse, Argon2id storage, reset/logout/idle revocation, tampered/expired command contexts, two-student HTTP/socket denials, scoped counts, role self-promotion denial, team restriction, durable intent reconciliation, owner-bound duplicate receipt, legacy hash preservation and actual pre-v2 backup restore. Existing 28 regression cases remain exercised (ingress text updated for intentional login replacement).

Browser: synthetic verified individual signed into the unchanged reporting dashboard; proof: evidence/phase1-individual-login.png. Full signup/verification/denied-object proof is automated HTTP/socket evidence rather than a screen recording. No actual enrollment inbox or production token was inspected.

## Acceptance and remaining scope

- PASS: eligible individual account, mailbox challenge gating, local test delivery, password/session protections, protected provisioning, HTTP/socket privacy and legacy segregation.
- PASS: baseline queue/TLS/framing/retry/receipt/dedup/lifecycle tests.
- PASS: migration backup/restore into separate test DB.
- Not release-ready: real SMTP/inbox proof not configured or tested. Public signup disables without transport; local mock is never presented as live email.
- Walk/message object tests await those modules (Phases 3–4); existing incident privacy is tested now. No SafeWalk/chat/Trust Lab implemented here.
- No real mobile keyboard/screen reader audit yet; Phase 2 handles shell checks.

## Rollback

No production or existing user database was migrated. Isolated tests/previews only. Runtime backups under data-dir/pre-v2-backup preserve pre-change SQLite; before actual operations stop all writers, make off-host private copies, restore both files into a separate directory and verify before switching. Backups on ephemeral host are themselves ephemeral. Do not roll back publicly to shared human token authentication. Revert code on this feature branch or disable signup; retain restricted data. Version 1 schema ledger tracks identity; legacy stores retain idempotent additive schema initialization.

Decision: PASS for local Gate 1 with recorded mail/release limits.
Approval for Phase 2: APPROVED by user's instruction to complete both phases.
Deployment approval for Phase 1/2: NOT GIVEN.
