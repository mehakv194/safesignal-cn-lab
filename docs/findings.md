# Implementation findings

## Inventory — 18 November 2026

Windows / PowerShell; Python 3.13.9. Existing Git repository on unborn `master`,
no code or commits. All five source Markdown files and original DOCX read.
Original synopsis retained under ignored `starter/` because it includes enrollment
numbers. No existing user code changed. pytest present; Flask/cryptography absent
initially. NS2, OpenSSL and Wireshark not on PATH. GitHub CLI installed but saved
authentication invalid: publication blocked until owner runs `gh auth login`.

User approved MIT licensing and publication after checks pass. No publication yet.
Virtual environment ensurepip failed on this Unicode workspace path; installing
through host pip's `--python .venv/Scripts/python.exe` works around bootstrap.

## Scope and decisions

Use standard library TLS/TCP + SQLite, Flask and plain templates. Shared modules
own validation/framing and store transactions; callers are socket handler, worker,
web adapters and integration tests. Never put tokens in browser source. Local
generated secrets/certificates/databases ignored. Only server owns authoritative
alert state. One synthetic sender principal; no multi-tenant claim. TLS selected
from synopsis alternatives; no custom cryptography. Timestamp freshness must not
reject legitimately queued alerts after an outage; validate UTC timestamps and
future skew, use stable UUID/payload hashes for replay safety.

## Ordered checklist

- Phase 0: source preservation, ignores, package, license, documentation.
- Phase 1: bounded protocol, certificate setup, authenticated persistence, TLS tests.
- Phase 2: durable outbox, recovery/backoff, dedup, separate responder ACK.
- Phase 3: authenticated local web interfaces, CSRF, real timeline.
- Phase 4: guarded faults and measured CSV/chart experiment.
- Phase 5: independent NS2/Wireshark instructions, no invented results.
- Phase 6: complete checks and demo documentation, publish only with working auth.

## Phase 0 / Phase 1

Skeleton commit `da92830`; package import smoke passed. Transport implemented with
bounded exact framing, verified localhost certificate, role tokens, validation,
SQLite commit-before-receipt, dedup/conflict and idempotent responder acknowledgment.
Some shared store/status functionality landed early because the same transaction
paths are exercised by transport acceptance checks.

Command: `.venv/Scripts/python -m pytest -q --basetemp=<writable ASCII path>`:
**7 passed in 4.57s**. Actual temporary loopback TLS connections and SQLite files;
wrong certificate rejected. Sandbox blocks loopback, so test execution required
elevated tool access. Default pytest temp location also inaccessible; explicit
ASCII basetemp used. Initial runs failed on these environment constraints before
test execution; no security fallback added.

## Phase 2

Transport commit `d4b3710` merged to main. Durable outbox saves before submission,
claims sends transactionally, records attempts and timeline, recovers SENDING on
startup, and applies capped jittered exponential backoff. Polling after receipt
does not resubmit; responder terminal state never regresses. One worker per
outbox is the supported orchestration model. SQLite errors surface rather than
silently claiming data saved. Restart test uses a separate Python process.
`python -m pytest -q --basetemp=<ASCII path>`: **11 passed in 6.90s**, including actual lost application receipt after commit and same UUID retry.

## Phase 3
Reliability commit adbf41a merged. Separate authenticated Flask portals with CSRF, escaped templates, strict loopback Host checking, no-store/CSP headers, session login throttling and distinct cookies. Worker independent of browser. Orchestrator starts three processes. Full suite: 12 passed in 8.39s; web adapter tests use live TLS backend. Browser visual verification pending. Local JSON configuration chosen instead of dotenv to avoid another dependency; SAFESIGNAL_* environment overrides supported.

## Phase 4

UI commit `e135025` merged. Guarded app faults default off: use
`scripts/run_demo.py --enable-demo-faults`. Normal resets; delay applies 1500ms
before receipt; lost receipt closes after commit only on first new submission;
disconnect prevents sender connections. Settings shared atomically via ignored
local JSON. Small responder pages (5 alerts) keep responses under 16KiB even for
maximum Unicode payloads; priority ordering happens before pagination.

Full suite **14 passed in 11.96s**. Seeded experiment uses isolated server SQLite
files and actual loopback TLS, fixed repeating fault schedule, per-alert deadline,
client-monotonic confirmation timing, nearest-rank p95, CSV/JSON/SVG. PNG export
uses the browser canvas, avoiding a plotting dependency. Same immutable UUIDs
across isolated policy runs; no production database reused. Retention: local
demo data stays until explicitly archived/reset by owner.

Browser verification: logged into both portals, submitted synthetic alert,
observed SERVER_RECEIVED, clicked responder ACK, observed sender terminal state.
Screenshots saved under docs/screenshots. Requested viewport override 1366x768;
browser capture retained its native 1086px width, so exact-size QA is not claimed.
Chart and metrics visibly rendered in browser. No private data in screenshots.

## Phase 5
Chaos/evidence commit 6308529 merged; 15 tests passed in 11.88s including maximum Unicode payload pagination. Independent four-node NS2 TCL scenarios and strict legacy wired-trace parser added. Parser synthetic fixture: 1 passed in 0.09s. NS2 executable unavailable, so simulation NOT RUN; no trace values claimed. Wireshark instructions added, capture NOT RUN. Verified legacy trace format against official NS2 documentation.
