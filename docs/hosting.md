# Single Python app deployment — prepared, not provisioned

User approved one permanent web address with separate dashboards and explicitly
requires approval before paid services. Netlify preparation was deferred in favor
of one Python hosting service. No Netlify project, paid service or disk created.

## What runs

`python -m safesignal.hosted` starts one process: Waitress serves `/`, `/sender/`,
`/responder/` and `/healthz`. One worker handles one SQLite outbox; a private
loopback TLS socket server owns authoritative incident state. No raw TCP port is
publicly exposed. Browser ingress uses the hosting provider's HTTPS termination.
The local equivalent is `python scripts/run_app.py --enable-demo-faults` at :5000.

## Concrete Render configuration

`render.yaml`: one Python Starter web service, one instance, 1GB persistent disk
at `/var/data`, build `pip install -r requirements-hosted.txt`, start
`python -m safesignal.hosted`, health check `/healthz`. This is a PAID configuration;
review the current provider quote and obtain approval before applying it.
Free ephemeral storage would lose SQLite state and does not meet persistence goals.

Three independent random secrets (at least 32 characters) are required:
SAFESIGNAL_SENDER_TOKEN, SAFESIGNAL_RESPONDER_TOKEN, SAFESIGNAL_SESSION_SECRET.
The owner enters these in the hosting dashboard; never put them in Git or chat.
RENDER_EXTERNAL_HOSTNAME is allowed automatically; other domains require an exact
SAFESIGNAL_ALLOWED_HOSTS comma-separated allowlist. No wildcard host allowance.
Secure, HttpOnly, SameSite=Lax cookies have separate role names and paths.
HTTPS scheme is trusted from one ingress proxy; forwarded Host is not trusted.

ENABLE_DEMO_FAULTS defaults to 0. If enabled for a protected synthetic presentation,
settings reset to Normal on startup. A persistent disk stores both databases,
fault configuration and evidence. Do not scale replicas: SQLite and one shared
outbox require one service instance. Back up the disk through provider facilities.

## Review before public release

1. Approve the actual hosting/disk quote; connect the owner's hosting account.
2. Owner supplies infrastructure secrets in the provider dashboard.
3. Deploy reviewed commit and verify `/healthz`, HTTPS/host restrictions and login.
4. Submit → acknowledge/assign → in progress/note → resolve through the public URL.
5. Restart the service and verify the same incident IDs and state survive.

Public release is not claimed until these steps actually succeed. The prepared
runtime has local integration coverage for mounted routes, HTTPS/secure cookies,
CSRF, real private TLS submission, role checks and full runtime restart persistence.

## Truthful limits

The shared sender queue is on the Python host. A browser without access to the
website cannot submit or save offline; IndexedDB/service-worker queuing is not
implemented. Internal TLS/TCP traffic is within one host, not a measured WAN path.
Reviewed local experiment results are explicitly labeled when copied to hosted
Evidence; they are not hosted-network measurements. There is one shared demo
sender and one authenticated response-desk principal with synthetic teams.
No real emergency dispatch, production security proof or uptime guarantee.
