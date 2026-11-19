# Phase 1–2 review guide

Source is on codex/v2-identity-mobile. The public app has NOT been upgraded to v2. Phase 0 documentation alone was published to main at 2202136. No paid services were added.

## Normal local run

Install requirements with the existing venv, initialize local config only if absent, then run `python scripts/run_app.py`. This enables individual identity in the combined app. Stop other local writers first. Existing local SQLite is backed up under local/pre-v2-backup before additive changes. Keep an additional private copy off the host before any real migration; local backups on ephemeral hosting do not survive loss of that storage.

Registration requires genuine inbox verification. Set SAFESIGNAL_SMTP_HOST, SAFESIGNAL_MAIL_FROM, optional SMTP_PORT (default 587), SMTP_USER and SMTP_PASSWORD through the process environment. SMTP uses STARTTLS; do not paste credentials into source or chat. No provider, account, charge or outbound real email was configured during implementation. If no mail transport exists, signup is unavailable. Tests inject a captured transport; production main has no mock-mail or verification-bypass setting.

Signup uses exactly ten ASCII enrollment digits and @mail.jiit.ac.in. Outer whitespace is trimmed and domain case normalized. Accounts start as students; verification/reset challenges expire in 15 minutes and are single-use. Passwords require 12–128 characters. Sessions expire after 30 minutes idle or eight hours absolute and are revoked on logout, reset, password or role change.

## Provision a synthetic response account

After the account's inbox is verified, an authorized local maintainer sets SAFESIGNAL_DATA_DIR and SAFESIGNAL_SESSION_SECRET for the same data store, then runs:

```powershell
python scripts/provision_responder.py <verified-demo-email> --team "Medical Team"
```

Team options: Campus Safety, Medical Team, Facilities Team. Explicit `--legacy-demo` additionally permits legacy NULL-owner demo cases under that team's queue policy. There is no public provisioning route or responder role picker. Unassigned new cases are visible to authorized response desks; after assignment, only the matching team can access them. Students only see their own cases. Demo staff eligibility does not represent real institutional authorization.

## What to review

Open Sender, register, complete the delivered inbox challenge, and sign in. Home shows reporting and private cases before analytics. Use Incidents to search/filter, Profile for account details/change password/logout, and Network Lab for delivery concepts. SafeWalk is marked unavailable until Phase 3. Responder login requires a provisioned account and retains assignment/start/notes/resolve functions and Evidence Lab. Messages, student closure feedback and the new security lab are not implemented until later phases.

An isolated synthetic preview may run at http://127.0.0.1:5056/ while this development session is active. It uses local/v2-preview, captured test mail and synthetic accounts only; it is not a permanent host or real mailbox proof. The normal local launcher uses your own local data, not this preview.

## Rollback

Keep runtime changes on the feature branch. Legacy shell is retained for isolated legacy network fixtures, not as a public auth fallback. Stop every writer before migration/restore. Restore the matched server/outbox backups into a new directory, verify integrity/counts and baseline behavior there, and only then switch operational paths with approval. Never assign legacy shared cases to a new student. Do not deploy these phases until separate explicit approval and release checks; hosted registration remains disabled if email is not verified operationally.
