# SafeSignal v2 — authorized production release

Date: 19 November 2026 (Asia/Calcutta). User explicitly authorized deployment of Phases 1–2 and implementation/publication of Phases 3–5. User separately chose **keep registration disabled for now**.

## Live service and source

- URL: https://safesignal-campus.onrender.com/
- Service: srv-dbusv3vf3r2c739lkrp0; existing Render Free Python service, one instance, SQLite, no external database, disk upgrade, card or paid add-on introduced.
- Phase 1–2 deployment: source f7aec68, deployment dep-dbvipf3l550s73fvbjlg, Live observed.
- Final Phase 3–5 deployment: source **9b130a7**, deployment **dep-dbvj82nf3r2c73cdnehg**. Render reported **Deploy succeeded | Live**, duration 50.2s, 19 November 2026 at 23:08:18 GMT+5:30.
- Final service detail: https://dashboard.render.com/web/srv-dbusv3vf3r2c739lkrp0/deploys/dep-dbvj82nf3r2c73cdnehg
- Later documentation-only commits do not imply another runtime deployment. No runtime modifications after the tested source were included.

## What is deployed

Verified-account identity and mobile shell; owner-only server-scheduled SafeWalk with safe/help/arrival/end actions and late follow-up; queue/TLS-linked help incidents; private Incident Room with retry-safe messages, quick replies, polling and independent resolution feedback/review; public login anomaly/security audit defenses.

Trust Lab fixture code is included for local operation but its controls are **not public**. Hosted mode forces lab routes and application fault injection off. This is an intentional security requirement, not unfinished public attack controls.

Registration is explicitly off in hosted main and render.yaml (SAFESIGNAL_REGISTRATION_ENABLED=0/default off). Even existing SMTP configuration cannot implicitly activate registration. No public test accounts or mailbox-verification bypass were created. Internal role tokens are service credentials only and no longer human login credentials.

## Actual test evidence

- Phase 3: 50 passed in 36.65s, including real HTTP→TLS help delivery and time-controlled/restart/idempotency/owner cases.
- Phase 4: 55 passed in 43.27s; real two-session browser message exchange, draft retained during incoming polling, desk resolution, student review request, desk review and student confirmation.
- Phase 5: 65 passed in 49.38s after correcting Windows SQLite connection cleanup; final integrated 66 passed in 51.36s plus new signup-off focused test 1 passed in 0.83s.
- Final source CI: https://github.com/mehakv194/safesignal-cn-lab/actions/runs/44578793459 — **67 passed on Linux in 41.76s**, **67 passed on Windows in 75.38s**. No tests skipped to obtain acceptance.
- Local browser lab: genuine VERIFIED, modified REJECTED, cross-user DENIED, role DENIED, bounded failed-logins DETECTED. Stored redacted outcomes and screenshot in evidence/.
- Existing TLS verification, framing, receipts, retries, duplicate/conflict protection, recovery and response lifecycle regressions remain exercised.

## Actual public verification after final deployment

Read-only Python urllib HTTPS checks with 40-second request timeout returned:

| Path | Observed result |
|---|---|
| / | 200; current SafeWalk/Incident Room copy present |
| /healthz | 200; ready=true |
| /sender/login | 200 |
| /responder/login | 200 |
| /sender/register | 200; registration unavailable |
| /sender/trust-lab | 404 |
| /responder/trust-lab | 404 |

Browser additionally observed the current landing and disabled Send verification button. Public proof: evidence/production-phases345.png. Public-mode direct POST lab denial and forced fault override rejection were tested in the isolated production-mode runtime, not by running attack fixtures against the public service.

No authenticated public incident/walk/chat flow was executed: registration is off, no real inbox delivery or human account was provisioned, and production secrets were not inspected. Those flows were actually exercised using verified synthetic local accounts and automated production-mode/TLS fixtures. Do not describe these as live human mailbox tests.

## Limits and recovery

Free host sleep means no guaranteed continuous scheduling or phone notifications. Ephemeral SQLite may reset, including accounts, reports, messages and backups. No GPS, real dispatch, physical-safety verification, true read receipts or browser offline queue. Real-device keyboard/screen-reader certification and full Phase 6–7 performance/readiness package remain pending; they are not silently marked complete by this release.

Known prior secure release source: f7aec68. If rollback is needed, stop writers, take private matched server/outbox snapshots, rehearse restoration/compatibility in an isolated path, then deploy the approved revision with retained records. Never enable v1 shared public token login or delete new records as rollback. Earlier v2 rollback disables walk/room features; communicate that interruption. No rollback was performed during this release.
