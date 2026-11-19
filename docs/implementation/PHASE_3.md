# Phase 3 — SafeWalk

Date: 19 November 2026. Branch: codex/v2-walk-room-trust. Gate: PASS for local simulation. User authorized Phases 3–5 and production publication after checks.

## Changes and acceptance

- walks.py: owner-only session start/list/detail/actions over authenticated socket commands; one active walk per user, 5–60 minute duration and 5/10/15 minute intervals, two-minute grace, UTC slot reconciliation in the server worker independent of browser state. Stable UUIDs, transaction-safe action keys and one help/follow-up link per walk prevent duplicate incidents.
- identity submission intents remain the crash-safe bridge to outbox → verified TLS/TCP → authoritative receipt. HELP produces HIGH/SAFETY synthetic incident. SAFE records self-report without creating an incident. ARRIVE/END cancel future slots; incident lifecycle remains independent.
- Late SAFE withdraws unacknowledged follow-up from active queue while retaining records; acknowledged follow-up needs review. A subsequent missed slot restores review attention without generating another case.
- hosted.py/server.py/sender_worker.py wire authenticated walk commands and server maintenance into the existing runtime; server_store.py adds additive links/disposition and attention filtering, preserving legacy hashes/state meanings.
- web.py and walk_list/start/detail templates add real mobile actions, UTC receipts/history and explicit offline/sleep/storage limitations. student_home.html exposes SafeWalk; mobile.css adds usable action spacing.
- tests/test_walks.py adds deterministic clock, concurrent retry, late/restart/ownership/state/limits and real web→TLS queue cases; obsolete My Walks placeholder test now expects an honest backend 503 during outage.

## Actual verification

`.venv/Scripts/python.exe -m pytest -q --basetemp=C:/Users/mehak/.codex/visualizations/2026/11/18/01a1eef0-be7d-75d1-b1ed-8f0bbffef830/v2-phase3-verified`

**50 passed in 36.65s**, exit 0. An earlier added UI test initially failed on an HTML-escaped apostrophe; assertion corrected to decode HTML, then the full suite passed. No failed result hidden.

Browser on isolated synthetic preview: start Hostel→Library; I'm Fine saved with no linked incident; I Need Help opens a HIGH linked queued incident. Screenshots: evidence/phase3-active-walk.png, phase3-help-incident.png. Real TLS receipt progression additionally proved by automated integration test. No real student data/production login used.

## Limits, pending requirements and rollback

No GPS/push/real dispatch or continuous monitoring. Free Render can sleep/reset SQLite; reconciliation works only when rows survive. Latest five journeys displayed. One linked help and one follow-up per walk are intentionally stricter dedupe than per-click creation. Physical phone keyboard not tested. Incident Room/student feedback and Trust Lab remain pending Phases 4–5.

Schema version 2 is additive; existing data untouched in development. Stop writers and back up server/outbox before operational changes; restore matched backups into an isolated directory and verify first. Disable walk routes/maintenance by reverting to accepted Phase 1–2 code if needed, retaining new rows privately. Never reactivate shared public login.

Phase 1–2 deployment: Render dep-dbvipf3l550s73fvbjlg at source f7aec68 reported Live; public registration page verified showing email-unavailable fail-closed state. Service remains Free. Real SMTP remains unconfigured; no public verified accounts invented.

Decision: PASS. Proceed to Phase 4 under user's explicit combined approval; final Phases 3–5 deployment remains pending their checks.
