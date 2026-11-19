# SafeSignal final release gates

19 November 2026 (Asia/Calcutta). The owner approved implementation and deployment of the remaining phases. Public registration stays disabled under the owner's prior decision.

## Phase 6 — Reliability and privacy

Frontend polling now checks for drafts, active controls and sends again when a response arrives. The composer protects its submitted text during an in-flight send. Offline form submission stays on the current page with truthful feedback.

The Windows loopback experiment ran `scripts.run_experiments.run` in a temporary directory with a fresh development certificate, seed 7, 12 alerts per policy and a two-second observation window. Application faults were first-attempt disconnect, lost application receipt and normal delivery. The separate delay fixture passed in the regression suite. Timings below describe observed confirmations only. They are local fixture results.

| Policy | Stored | Confirmed | Retries | Duplicates suppressed | Confirmation p50 | Confirmation p95 |
|---|---:|---:|---:|---:|---:|---:|
| One attempt | 8/12 | 4/12 | 0 | 0 | 17.4 ms | 18.3 ms |
| Retry and deduplication | 12/12 | 12/12 | 8 | 4 | 242.3 ms | 282.6 ms |

The full local suite passed 67 tests in 46.69s after the JavaScript fix, preserving wrong-cert and frame rejection, receipt loss, queue recovery, ownership, CSRF and public lab denial. The clean hosted-mode smoke was then extended in `tests/test_walks.py` to exercise a second verified synthetic role and bidirectional messages. The first focused run encountered a test indentation typo. The corrected `pytest -q tests/test_walks.py tests/test_hosted_ingress.py tests/test_evidence.py` passed 9 tests in 11.59s. `node --check safesignal/static/app.js` and `git diff --check` passed. The tracked-file inventory found no SQLite databases, PEMs, private key files or .env.

Gate: local reliability, privacy and integration checks passed. Physical low-end mobile performance and device keyboard/screen reader testing were unavailable. Prior seven-width browser evidence remains in the Phase 2 and 4 reports.

## Phase 7 — Release readiness

Staging used fresh temporary databases with hosted HTTPS routing and private TLS, plus the separate real Waitress ingress test. Anonymous access, registration-off, verified synthetic student/responder workflow and direct lab denial were exercised. No production credentials were copied or used.

For a class demo, start the isolated local app with verified synthetic fixtures. Start a walk as a student, record a safe check-in, then request simulated help. In a separate responder session, open the case, exchange messages, resolve it and record student feedback. Show the receipt and response states separately. For the security walkthrough, use a locally enabled Trust Lab and its redacted outcomes. For the network walkthrough, use the isolated experiment above.

Configuration inventory: one Render Free service, secret-injected sender and responder service credentials and session secret, SQLite under /tmp/safesignal, registration disabled, fault injection disabled, no external database. Real email delivery is deferred. Render Free blocks common SMTP ports, so future mail integration needs a compatible verified delivery path. See [Render Free limitations](https://render.com/docs/free).

Rollback reference: deployed source 9b130a7, Render deploy dep-dbvj82nf3r2c73cdnehg. Verify /healthz and both role login screens after any rollback. A code rollback cannot recover data lost on Render's ephemeral filesystem. For local recovery, stop writers, retain matched private SQLite snapshots, and verify copies before switching. No schema change is required by Phases 6–8.

Readiness gate: passed for the approved registration-off simulation. Production authenticated journeys require existing verified accounts. Render Free sleep and SQLite reset remain operational limits.
