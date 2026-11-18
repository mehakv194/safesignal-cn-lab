# Five-minute synthetic demonstration

Before class: run init_demo, tests, run_experiments, then
`python scripts/run_demo.py --enable-demo-faults`. Open sender :5001 and responder
:5002. Log in with the corresponding tokens in ignored local/config.json;
do not project the token file. Use only the supplied synthetic descriptions.

1. **0:00–0:35** Explain sender → verified TLS/TCP socket server → SQLite;
   browser HTTP stays on loopback. Distinguish server receipt and human ACK.
2. **0:35–1:15** Normal preset. Submit LOW “TEST ONLY: synthetic campus alert”.
   Observe local outbox then SERVER_RECEIVED. Responder acknowledges; observe
   RESPONDER_ACKNOWLEDGED on sender. Open factual timeline.
3. **1:15–2:10** Set disconnect. Submit HIGH synthetic alert; it remains queued.
   Stop/restart sender if demonstrating crash recovery; leave the same SQLite
   files in place. Reset normal; observe retry of the same UUID.
4. **2:10–3:05** Set first application receipt lost, submit. Server shows record
   while sender initially cannot confirm it. Retry resolves; sender duplicate
   counter increments. No second alert row is created.
5. **3:05–4:10** Evidence Lab: show config/seed/window, CSV and chart. Baseline
   stored 4/6 vs retry 6/6 in the recorded scenario. Explain pending confirmation
   separately. If a genuine authorized capture exists, show TLS records; otherwise
   state Wireshark capture not run and show the instructions, not a fake capture.
6. **4:10–5:00** Show separate NS2 scripts. State NS2 not run on this host;
   replace this with actual traces only after a real Linux/WSL run. Explain limits.

## Six-slide outline

1. **Problem & boundaries:** intermittent path; synthetic local prototype;
   no direct emergency dispatch, no guarantee through permanent outages.
2. **Architecture:** browser adapters, worker/outbox, TLS sockets, central SQLite,
   responder. Server can read plaintext; encryption at rest not implemented.
3. **Wire/state:** 4-byte length + bounded JSON; stable UUID;
   QUEUED → SENDING → SERVER_RECEIVED → RESPONDER_ACKNOWLEDGED.
4. **Reliability & security:** commit before receipt, payload hash conflict,
   dedup PRIMARY KEY, capped jittered backoff, role tokens, verified certificate,
   CSRF sessions, localhost default.
5. **Actual evidence:** reviewed CSV/chart, seed 7, six samples/policy,
   chosen app fault schedule and 2s window. Separate NS2/Wireshark NOT RUN.
6. **Conclusions & limits:** recoverable local queue, independent ACK, no
   availability promise; future evaluation with more samples and authorized LAN.

## Viva quick answers

- **Why retry with TCP?** TCP receipt is not durable DB commit or application
  confirmation. A failed connection can leave acceptance ambiguous.
- **Why UUID plus hash?** UUID identifies retries; hash rejects changed content
  for the same ID. Database constraint is final dedup authority.
- **Exactly once?** Repeated attempts, one alert record per immutable UUID.
  No exactly-once network-delivery claim.
- **TLS vs mutual TLS?** Server-authenticated TLS plus role tokens. No mTLS.
- **Outage?** Queue persists while disk is intact; delivery needs worker and
  restored communication path. Disk failure is outside this prototype's promise.
- **ACK layers?** TCP segment ACK, server durable application receipt,
  separate responder ACK. None implies assistance dispatched.
- **NS2 relation?** Independent wired topology simulation, not Python app execution.
- **Latency?** Same-host UTC server receipt time and monotonic confirmation time
  are different; missing responses can delay confirmation after persistence.
- **Security limits?** Local demo token model, no at-rest encryption or formal
  security proof; Flask development server is not a production host.

Team contribution assignments in the synopsis are proposals; no claim of actual
individual implementation contributions is made by this generated repository.
