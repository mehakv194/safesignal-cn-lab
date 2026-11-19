# Phase 4 — Private Incident Room

Date: 19 November 2026. Branch: codex/v2-walk-room-trust. Gate: PASS for local simulation. Combined user approval covers proceeding to Phase 5 and publication after checks.

## Changes and completed requirements

- rooms.py adds transaction-scoped owner/team authorization, actual persisted messages, per-author client UUID uniqueness/conflict checks, 300-character messages, four-message cursor pages, 30/minute sender and 500/case quotas. Unicode pages remain below the original 16 KiB frame cap.
- Server/hosted wire ROOM_GET/SEND/FEEDBACK through authenticated verified TLS/TCP commands. Human sessions are rechecked; worker intents cannot act as chat principals. Server_store adds review attention without regressing terminal lifecycle.
- Separate feedback CONFIRM/REOPEN_REQUEST/REVIEW records preserve administrative RESOLVED history. An open request is flagged in responder queue and must be reviewed before confirmation; all actions append generic audit events. Chat bodies are not copied into general audit/export.
- web.py adds CSRF-protected message/feedback endpoints, JSON server receipts, stable form message IDs and authorized room history. room.html and incident.html provide thread, composer, quick replies, pagination and closure feedback.
- app.js sends messages with explicit pending/confirmed/unconfirmed states, retains draft and UUID on fetch failure, and polls other regions while excluding the actively edited composer. No fake human-read, typing or push state.
- mobile.css supports wrapping messages, large quick replies and ordinary-flow composer with keyboard scroll clearance. No attachment or call integration.

## Actual tests

`.venv/Scripts/python.exe -m pytest -q --basetemp=C:/Users/mehak/.codex/visualizations/2026/11/18/01a1eef0-be7d-75d1-b1ed-8f0bbffef830/v2-phase4-verified`

**55 passed in 43.27s**, exit 0. Initial run: 54 passed, one failure exposed incorrect Flask jsonify argument combination; fixed response construction and reran full suite. Existing network/identity/SafeWalk tests preserved.

New tests: concurrent message retries, changed-body conflict, student/desk-team isolation, early/illegal feedback, feedback idempotency, preserved resolution, Unicode frame bounds, cursor history, quota, redacted audit, real TLS roles and token-only denial, web CSRF/XSS and private polling.

## Browser evidence

Synthetic walk-linked case only: student message → desk question, while student draft remained exactly intact and incoming question appeared via polling. Desk acknowledged/started/resolved. Student requested follow-up; pending review visible while original state stayed Resolved; desk reviewed; student confirmed. Screenshots: phase4-room-phone.png, phase4-thread-and-feedback.png; widths recorded in phase4-responsive.json show no page overflow at all seven required widths. Composer checked in 390×480 reduced-height viewport as a keyboard-space approximation, not physical phone keyboard certification.

## Pending / limits / rollback

Real mail and public authenticated user flows remain unavailable until inbox delivery configured. No actual call/notification/read receipt. Messages require connectivity; uncertain sends retain the same key for retry, not an offline queue. Only latest four messages plus paginated history; feedback shows recent five. New local cybersecurity controls remain Phase 5.

Schema version 3 additive; preserve messages/history during rollback. Stop writers, privately back up both SQLite files, restore into separate path and verify before switching code; never reset ownership or enable public shared login. Phase 4 code may be reverted to accepted Phase 3 while retaining access-restricted tables. No production Phase 3/4 migration has run yet; tests/previews use isolated local data.

Decision: PASS. Phase 5 approved by user's combined request. Publish only after final checks; local-only Trust Lab must be denied publicly.
