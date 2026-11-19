# Phase 5 — Local Trust & Security Lab

Date: 19 November 2026. Branch: codex/v2-walk-room-trust. Gate: PASS for local acceptance; final public deployment verification pending.

## Implemented / files

- trust_lab.py: five allowlisted bounded fixtures: real HMAC verification, modified content rejection, actual socket-dispatch cross-owner denial, actual responder-role denial and six in-process failed logins triggering one application detector event. Non-crypto fixtures use isolated temporary SQLite and locally captured test mail. No external attack requests, real users or public control endpoint.
- identity.py: redacted structured audit metadata, five-failures/60-second detector with capped per-key markers, existing login throttling preserved. Password hashing/verifying concurrency capped at two to avoid multiplying 64 MiB Argon2 allocations across every Waitress thread on Free hosting.
- web.py / trust_lab.html / shell_v2.html: explicit local config, loopback host and peer restriction, authenticated responder-only access, CSRF POSTs, bounded runs, clear result cards and last 20 redacted events. No challenge/key/session/private message body exported. Normal public mode returns 404 before login for direct lab URLs.
- hosted.py: public mode unconditionally disables application faults, even if ENABLE_DEMO_FAULTS=1 is requested. main does not read a Trust Lab enabling environment setting. Owner explicitly chose to keep registration disabled; SAFESIGNAL_REGISTRATION_ENABLED defaults off and render.yaml pins 0. No real mail provider configured or paid service added.
- run_app.py: explicit --enable-trust-lab flag for local simulation only; default off.
- server.py / rooms.py audit role/object access denials without copying private content.
- database.py plus identity/server/outbox stores: shared context manager now commits/rolls back AND closes connections. Tests exposed Windows temporary fixture cleanup failures because the old sqlite3 context manager only ended transactions; fixed root resource handling after checking all callers. Outbox owned enqueue also uses BEGIN IMMEDIATE to serialize concurrent web/worker reconciliation.
- tests/test_trust_lab.py / test_database.py cover outcomes, public/direct/role/CSRF denial, fake signatures, false positives, window expiry, connection commit/rollback/closure, concurrent queue reconciliation, and explicit signup-off behavior. No test disabled to obtain a pass.

## Tests actually executed

First full Phase 5 run: 3 failed, 61 passed in 52.29s; all three failures were Windows file locks on temporary fixture database cleanup. After shared cleanup correction: **65 passed in 49.38s**.

Final integrated release command:

`.venv/Scripts/python.exe -m pytest -q --basetemp=C:/Users/mehak/.codex/visualizations/2026/11/18/01a1eef0-be7d-75d1-b1ed-8f0bbffef830/v2-phases345-release`

**66 passed in 51.36s**, exit 0. This includes the extra concurrent reconciliation regression. Subsequently the owner chose signup-off explicitly; added one focused test:

`.venv/Scripts/python.exe -m pytest -q tests/test_trust_lab.py::test_owner_can_keep_registration_disabled_even_with_mail --basetemp=C:/Users/mehak/.codex/visualizations/2026/11/18/01a1eef0-be7d-75d1-b1ed-8f0bbffef830/v2-signup-off`

**1 passed in 0.83s**, exit 0. Cross-platform CI for the combined final 67-case suite is a further release check, not invented here.

## Actual browser evidence

All five local fixture buttons produced VERIFIED / REJECTED / DENIED / DENIED / DETECTED. Captured evidence/phase5-five-outcomes.json and phase5-trust-lab.png. Controls tested in isolated preview only. No generated traffic to external infrastructure, no authentic institutional account credentials used. Existing SafeWalk/chat/UI/network regression cases remained passing.

## Completed, pending and rollback

PASS: genuine cryptographic outcomes, actual access-control fixture outcomes, bounded failed-login detector, redacted audit, local-only server gate and forced public fault denial. PASS: shared resource regression tests and signup-off test. Simulation-only scope retained.

Pending: final publication and public smoke verification; real inbox delivery deliberately off by owner; no actual mobile-device keyboard or screen-reader certification. Full Phase 6 hardening/performance/experiments and Phase 7 readiness package are not marked complete merely because the user authorized a simulated release.

Schema version 4 adds audit/failure data non-destructively. Stop writers before coordinated restore. Keep private matched server/outbox backups and restore to an isolated directory with integrity/regression checks before switching. Never turn public shared-token login back on as fallback. Local fixtures clean up their own temporary files; production reports are never deleted to make tests pass. Free host backup/files remain ephemeral and monitoring is not guaranteed.

Decision: PASS for local Gate 5. User explicitly authorized production publication after successful checks. Trust Lab controls must stay absent publicly; login/security defenses remain active.
