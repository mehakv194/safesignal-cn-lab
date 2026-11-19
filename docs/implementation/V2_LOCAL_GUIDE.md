# Phase 1–2 review guide

Phase 1–2 source was published and deployed at f7aec68 after owner approval. Phases 3–5 source is on codex/v2-walk-room-trust until final checks and deployment. No paid services were added. Later phase reports record actual deployed revisions.

## Normal local run

Install requirements with the existing venv, initialize local config only if absent, then run `python scripts/run_app.py`. This enables individual identity in the combined app. Stop other local writers first. Existing local SQLite is backed up under local/pre-v2-backup before additive changes. Keep an additional private copy off the host before any real migration; local backups on ephemeral hosting do not survive loss of that storage.

Registration requires genuine inbox verification. Set SAFESIGNAL_SMTP_HOST, SAFESIGNAL_MAIL_FROM, optional SMTP_PORT (default 587), SMTP_USER and SMTP_PASSWORD through the process environment. SMTP uses STARTTLS; do not paste credentials into source or chat. No provider, account, charge or outbound real email was configured during implementation. If no mail transport exists, signup is unavailable. Tests inject a captured transport; production main has no mock-mail or verification-bypass setting.

Signup uses exactly ten ASCII enrollment digits and @mail.jiit.ac.in. Outer whitespace is trimmed and domain case normalized. Accounts start as students; verification/reset challenges expire in 15 minutes and are single-use. Passwords require 12–128 characters. Sessions expire after 30 minutes idle or eight hours absolute and are revoked on logout, reset, password or role change. Hosted main also requires SAFESIGNAL_REGISTRATION_ENABLED=1; it is explicitly 0 by current owner choice. Do not enable until separately authorized and genuine inbox delivery verified.

## Provision a synthetic response account

After the account's inbox is verified, an authorized local maintainer sets SAFESIGNAL_DATA_DIR and SAFESIGNAL_SESSION_SECRET for the same data store, then runs:

```powershell
python scripts/provision_responder.py <verified-demo-email> --team "Medical Team"
```

Team options: Campus Safety, Medical Team, Facilities Team. Explicit `--legacy-demo` additionally permits legacy NULL-owner demo cases under that team's queue policy. There is no public provisioning route or responder role picker. Unassigned new cases are visible to authorized response desks; after assignment, only the matching team can access them. Students only see their own cases. Demo staff eligibility does not represent real institutional authorization.

## What to review

In a configured local environment, open Sender, register, complete the delivered inbox challenge, and sign in. Home shows SafeWalk, reporting and private cases before analytics. Use Incidents to search/filter, Profile for account details/change password/logout, and Network Lab for delivery concepts. Start SafeWalk, save check-ins, request simulated help and complete/end the walk. A missed check-in after two-minute grace creates one follow-up; it does not prove danger. Incident Room provides private 300-character messages, four-message pages, quick replies and separate student resolution feedback. Responder login requires a provisioned account and retains assignment/start/notes/resolve and Evidence Lab.

For controlled local cybersecurity fixtures only, use `python scripts/run_app.py --enable-trust-lab` and sign in as a provisioned synthetic responder. The five local fixtures use isolated temporary test data, real HMAC verification, actual access guards and a bounded application login detector. The public service ignores lab enabling and forces fault injection off. No new public attack controls are deployed.

An isolated synthetic preview may run at http://127.0.0.1:5056/ while this development session is active. It uses local/v2-preview, captured test mail and synthetic accounts only; it is not a permanent host or real mailbox proof. The normal local launcher uses your own local data, not this preview.

## Rollback

Keep runtime changes on the feature branch. Legacy shell is retained for isolated legacy network fixtures, not as a public auth fallback. Stop every writer before migration/restore. Restore the matched server/outbox backups into a new directory, verify integrity/counts and baseline behavior there, and only then switch operational paths with approval. Never assign legacy shared cases to a new student. Do not deploy these phases until separate explicit approval and release checks; hosted registration remains disabled if email is not verified operationally.
