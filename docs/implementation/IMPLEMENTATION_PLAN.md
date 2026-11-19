# SafeSignal v2 — sequential implementation plan

Prepared 19 November 2026. Baseline: 5a445017c2a7181d1ceb466a06be6caf09e15bc8.
Only Phase 0 has executed. Each later row requires approval after the preceding gate; production publication needs separate approval. Preserve Python/Flask/SQLite and existing module names. No framework rewrite, paid service or external database is planned.

## Phase 0 — Audit and protect baseline

- Dependency: supplied specifications and existing repository.
- Delivered: BASELINE_AUDIT.md, this plan, PHASE_STATUS.md and desktop/phone screenshots.
- Tests: existing suite, 28 passed in 27.41s; read-only local database schema/count inventory.
- Acceptance: verified component map, preservation inventory, auth storage/principal design, risk/backup plan and no feature edits. PASS; user review pending.

## Phase 1 — Verified identity and private ownership

- Dependency: Gate 0 reviewed and explicit approval. Resolve design choices using the audit; no live mail secret is needed for local mocked transport development.
- Scope: additive migration/version ledger; users/challenges/sessions/grants; exact ten-ASCII-digit email rule; Argon2id; inbox verification; generic recovery responses; reset/change-password, expiry/revocation, CSRF and bounded account/IP throttle. Restricted CLI grants responder permission to verified eligible demo users. Separate human and service credentials.
- Integration: extend existing alerts/outbox with immutable owner metadata and restricted legacy handling; trusted command-bound principal context at socket dispatch; scoped incident/list/audit/dashboard/evidence reads and writes. No arbitrary browser-supplied user/role assertions. Establish durable worker submission intent so delayed queue delivery is not tied to a live browser session.
- Expected files: focused auth/policy/migration modules, web.py, hosted.py/runtime.py, server.py, both stores, models validation adapters, login templates, dependency files and auth/migration/regression tests. Keep payload/framing/receipt semantics intact.
- Tests: valid format plus 9/11-digit, alias, wrong suffix and Unicode cases; unverified/wrong password denial; challenge expiry/single-use; reset replay; session fixation/logout/expiry; role spoofing; owner A/B denial at HTTP and socket layers; scoped aggregates/export; team denials; tampered context; legacy byte/hash preservation; full preexisting suite.
- Acceptance: new private individual local accounts work; public token bypass denied; responder provisioning restricted; all regressions pass; migration restore rehearsed. Hosted signup explicitly unavailable without real delivery. No claim of shipped SafeWalk/chat.
- Risks: privacy leaks, stale worker assertions, migration corruption, email abuse. Rollback: tested backups and local-only compatibility adapter; public shared login remains disabled.

## Phase 2 — Mobile shell and onboarding

- Dependency: approved identity/privacy gate.
- Scope: mobile Home, My Walks, Incidents, Profile bottom navigation; verified onboarding/recovery; real own-incident list and usable responder queue. Keep labs secondary. Show SafeWalk as unavailable until Phase 3, not a fake working action.
- Expected files: templates, styles.css, app.js, web routing and browser smoke tests.
- Tests: 320/360/390/430/768/1024/1440 widths; overflow, 44px targets, 16px inputs, keyboard/focus, contrast, status announcements, reduced motion and long errors/emails; role/CSRF/security-header and networking regressions.
- Acceptance: working navigation and identity/report flows on phones/desktop, with screenshot evidence (including 360/390/1024) and documented accessibility issues.
- Risks: broken desktop response controls or hidden form actions. Rollback: reversible layout selection with the same secure backend, never old public token authentication.

## Phase 3 — SafeWalk and server timers

- Dependency: approved Phases 1–2; decide bounded duration/interval/grace settings and enforce them server-side.
- Scope: owner-only walks/check-in slots; ACTIVE/NEEDS_FOLLOW_UP/COMPLETED/CANCELLED lifecycle; server UTC reconciliation independent of browser; I'm Fine, I Need Help, Reached Destination and End Walk. Idempotent help/follow-up links using durable enqueue intents and the original queue/TLS path.
- Integration: put authoritative walks/check-ins in server.sqlite and extend socket commands; web controls call scoped service operations. Scheduler records due/grace/missed events; stable slot/action keys make restart/enqueue retry safe. Late safe confirmation updates unacknowledged follow-up attention with a recorded disposition; acknowledged cases need desk review. Completing a walk never closes its incident.
- Expected files: walk service/scheduler, additive migrations, socket handlers, worker/runtime integration, templates and deterministic-clock tests.
- Tests: safe path creates no incident; double/concurrent help creates one; grace creates one follow-up; late safe preserves audit; closed browser; restart with intact DB; crash either side of outbox enqueue; completion cancels future slots; open incident survives completion; expired state/action denial; offline-before-POST truth; all network regressions.
- Acceptance: real server-persisted walk outcomes and receipts, phone evidence, no continuous monitoring/GPS/push claim. Free host sleep/reset remains explicit.
- Risks: duplicate incidents, timer storms, races and missed enqueue. Rollback: stop scheduler/disable new walk actions without dropping history; ordinary incidents remain usable.

## Phase 4 — Incident Room and resolution feedback

- Dependency: approved ownership, mobile shell and linked-help flow.
- Scope: actual persisted owner/responder thread, bounded text/quick replies, stable client UUID, server sequence/cursor pagination, send receipts and preserved drafts. Separate feedback CONFIRM/REOPEN_REQUEST from original terminal lifecycle; responder review/disposition is explicit and audited.
- Integration decision: use authenticated bounded socket commands for message persistence/history to share the authoritative resource policy; retry same client UUID after uncertain result. Do not change incident SUBMIT receipts or claim human read from a storage receipt. Student follow-up leaves the old RESOLVED history intact; use a separate review record/linked follow-up rather than silently moving backward.
- Expected files: message/feedback service and migrations, server dispatch/store guards, incident templates, polling/composer JS and tests.
- Tests: two-session exchange, cross-user/message-ID/poll denial, team restriction, duplicate/reordered retries and changed-body conflict, pagination, quotas, CSRF/XSS, typing during refresh, phone keyboard/safe-area/scroll, resolve→feedback→review. Existing actions/regressions must pass.
- Acceptance: real two-way private messages and closure disagreement workflow with synthetic transcript and mobile evidence.
- Risks: leaked content, lost drafts or illegal lifecycle regression. Rollback: disable messaging/feedback endpoints while retaining access-restricted rows and audit.

## Phase 5 — Local Trust & Security Lab

- Dependency: approved real authz and messaging boundary; no production testing.
- Scope: genuine vs modified authenticated fixture using vetted stdlib HMAC, private key outside client/source, actual cross-owner/role denial, bounded failed-login detector, redacted append-only logical security events and explanatory outcomes.
- Expected files: small local lab/security service, synthetic fixtures, templates, configuration gate and negative tests. Normal user functions must not depend on lab mode.
- Tests: verified accepts, alteration rejects, public fields cannot forge MAC, invalid actor/scope denied and audited, bounded burst detected, reasonable non-burst not flagged, no secrets/content in exports, direct public-mode routes denied even with query toggles. Full regression suite.
- Acceptance: all five demonstrable local outcomes, redacted audit evidence and server-side public denial. Detector described as a limited application rule, not a network IDS.
- Risks: public attack surface/key disclosure. Rollback: disable lab gate independently; retain normal reporting/walk/chat.

## Phase 6 — Integrated reliability, mobile and privacy hardening

- Dependency: all core feature gates approved.
- Scope: local normal/delay/lost-receipt/disconnect experiments; full user journey and privacy review; deterministic recovery; bounded performance sampling and mobile network conditions; export/log review.
- Tests: original TLS/framing tests, same UUID/same and changed payload, linked help/check-in/message duplicate races, scheduler restart, receipts distinguished from reads, hosted lab/fault denial, all J1–J10 scenarios, full suite and supported CI platforms. Visual matrix and actual mobile keyboard where available; label unavailable device evidence honestly.
- Acceptance: recorded before/after regressions, real p50/p95 only where sampled, anonymized evidence, no critical privacy failures, complete journey tests, remaining limits documented.
- Risks: hidden regressions, unrealistic timing claims. Rollback: prior accepted code plus rehearsed compatible data restore; no destructive cleanup for passing tests.

## Phase 7 — Release readiness (deployment separately approved)

- Dependency: approved integrated release candidate and staging access/configuration; staging hosting itself requires explicit authorization.
- Scope: final user guide/demo, secret/config inventory, free-host warnings, private backups/recovery, mail-delivery acceptance and signup disable behavior. No service spending or deployment by implication.
- Tests: clean isolated staging anonymous/student/responder checks; real verification/reset delivery to authorized eligible test inboxes; invalid/expired challenge, privacy, local lab off, restore rehearsal and smoke/rollback plan.
- Acceptance: no critical auth/privacy issue; real email proved or public registration disabled; user approves exact target/version/configuration and costs (free only unless separately approved). Only then deploy and record actual post-deploy checks.
- Risks: free email unavailable, account/history loss on ephemeral host, cold starts and missed scheduling while asleep. Never advertise continuous safety monitoring or durable cloud records.
- Rollback: known prior candidate plus verified backup/config restoration. Do not restore v1 shared public login as an auth fallback.

## Optional Phase 8 — Separate scope decision

Evidence Locker or PWA extras only after core acceptance and explicit opt-in. Own privacy/storage/quotas/tests gate; no uploads, offline queue or notification promises added implicitly.

## Approval and reporting discipline

After every phase: list actual changed files and behavior, exact test commands/results, mobile/security evidence, preserved baselines, migration/rollback evidence, limitations, completed/pending requirements and PASS/FAIL/BLOCKED. Update PHASE_STATUS.md and stop for user approval. A plan, mocked email or screenshot alone is not a completed feature. Gate 0 permits planning only; this document is not approval for Phase 1.
