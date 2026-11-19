# Single Python app — free-only deployment

Current release: SafeSignal v2 through Phases 1–5 is deployed at source 9b130a7 on
19 November 2026. See [release evidence](implementation/PRODUCTION_RELEASE_2026-11-19.md).
Human access uses verified individual enrollment-email/password accounts; shared
role tokens are internal service credentials only. Registration is explicitly
disabled by owner choice. Trust Lab controls and application faults are local-only.
The older deployment/token notes below are historical v1 records, not current login instructions.

The user explicitly requires FREE plans only and declined Supabase or any separate
cloud database. No Supabase project/database was created. No billing upgrade,
paid instance, persistent disk, external database or trial subscription is allowed.

## What runs

Live URL: https://safesignal-campus.onrender.com/
Sender: https://safesignal-campus.onrender.com/sender/
Responder: https://safesignal-campus.onrender.com/responder/

Deployed on 18 November 2026 at source commit 95082a6. Render reported the
deployment succeeded. Public landing, health endpoint and both role login pages
were verified. CI passed all 28 tests on Windows and Linux. Authenticated hosted
incident actions were not tested because private deployment tokens were not read.

Service: https://dashboard.render.com/web/srv-dbusv3vf3r2c739lkrp0
Owner-only tokens: https://dashboard.render.com/web/srv-dbusv3vf3r2c739lkrp0/env
Use SAFESIGNAL_SENDER_TOKEN and SAFESIGNAL_RESPONDER_TOKEN respectively.
The service shows Free; the workspace showed Hobby, no card and zero charges.

One Render Free Python web service, one instance. Waitress serves the landing
page, /sender/, /responder/ and /healthz. The existing private verified TLS/TCP
server and sender worker run inside the same process. SQLite is stored under
/tmp/safesignal. No public raw-TCP port or extra hosted service is needed.

render.yaml specifies plan: free and contains NO disk stanza. The provider
creates three random environment secrets through generateValue; actual secret
values are never committed or included in browser source. The owner can obtain
their dashboard access tokens from the service's Environment page.

Build: pip install -r requirements-hosted.txt
Start: python -m safesignal.hosted
Health check: /healthz
SAFESIGNAL_DATA_DIR=/tmp/safesignal
SAFESIGNAL_EPHEMERAL_STORAGE=1
ENABLE_DEMO_FAULTS=0

## Important free-plan behavior

Render Free can sleep after inactivity and restart with an empty filesystem.
The provider URL remains stable while the service exists; this is not an always-on
or lifetime availability guarantee. Incident reports, outbox and audit data may
reset on a host restart/redeploy. The UI explicitly discloses this. Export evidence
before a restart if needed. Local SQLite lab data is unaffected by cloud resets.

This is the deliberate free-only compromise after the user declined a separate
free cloud database. It does not meet the earlier cross-restart hosted-persistence
goal, and must not be presented as meeting it. Browser offline storage is also
not implemented. No real emergency dispatch.

Official limits: https://render.com/docs/free . Never switch to Starter or add a
paid disk to bypass these limits. If free quotas are exhausted, accept suspension
or wait for renewal; do not enable billing, paid add-ons or paid overages.

## Deploy and verify

1. Owner signs into Render (interactive credentials remain with owner).
2. Create a Free web service from this repository/configuration. No billing setup.
3. Confirm Free/$0 before final deployment. Use only the free provider subdomain.
4. Verify public HTTPS root, /healthz, sender/responder login and incident workflow.
5. Record the actual URL and deployment result. Do not invent a live URL.

Host allowlist uses RENDER_EXTERNAL_HOSTNAME automatically. Additional domains
require SAFESIGNAL_ALLOWED_HOSTS; no wildcard host acceptance. Role cookies are
Secure, HttpOnly and SameSite=Lax with separate names/paths. Trust one ingress
proxy's forwarded scheme, not forwarded Host. Keep one service instance only.

The local equivalent remains python scripts/run_app.py --enable-demo-faults at
http://127.0.0.1:5000 with durable local SQLite. Stop the existing app before starting
another worker against the same local outbox.
