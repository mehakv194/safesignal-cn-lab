# SafeSignal — Product Experience, Screens, Demo and Evaluation

## 1. The deliverable
A **local-first, multi-process Python prototype**: a sender-facing web page for convenience; a separate authorized responder page; a real Python TLS/TCP alert server; a sender-worker outbox; simulated connectivity controls; recorded evidence for CN evaluation. Desktop browser responsive layout. No external data API needed.

**Information originates from:** (a) user-entered synthetic alert form (severity, description, optional location); (b) client-generated UUID and clock values; (c) local application metrics/attempt log; (d) server database timestamps/status/audit; (e) deterministic simulation settings; (f) NS2 trace files from separate network simulations. No live police, hospital, GPS, social feed or government database.

## 2. Sender screens

### Sender / Home
Header: SafeSignal, `SIMULATION — NOT FOR REAL EMERGENCIES`, current backend connectivity. A single alert form: severity dropdown LOW/MEDIUM/HIGH/CRITICAL; description (10–300 chars); optional user-approved location text (max 120 chars). `Send test SOS` creates UUID and first commits to SQLite local outbox; no dependence on live internet at creation. Show visible confirmation "Saved locally" rather than "Delivered".

### Outbox / Alert Detail
Rows/cards include alert short ID, severity, submitted timestamp, last known state, attempt count, last error and next retry. Detail has step-by-step timeline: created locally, send attempted, server accepted, responder acknowledged; show factual timestamps only. `Retry now` button does not create a new UUID, and cannot bypass user/auth checks. A status poll uses authenticated `GET_STATUS` over TCP to retrieve responder changes.

### Network Chaos Lab (simulation)
Three presets: `Normal` (0 delay, no imposed faults), `High latency` (e.g. 1500 ms app-level delay), `ACK lost` (server commits then suppresses first application receipt for selected alert), `Temporary disconnect` (sender-worker simulation blocks connect attempts). Include a `Reset simulation` control. Make it clear **application fault injection, not packet-loss emulation**. Counters: queued, server received, responder acknowledged, retries, duplicate suppressions. Fault settings apply only to test traffic and are never global OS/network changes.

### Evidence Lab
Compare two reproducible sender policies against identical seeded synthetic batches: `single attempt` and `retry + dedup`. Store the run config and raw result rows. Show total unique alerts, unique received, delivery ratio, median/p95 receipt delay, retries, number of duplicates prevented, number still pending at deadline. If data insufficient, say N/A; never calculate misleading values. Ability to export CSV and PNG graphs. Include links to NS2 results as a **separate experiment**.

## 3. Responder screen
Separate URL and dedicated responder login (local token in environment; do not put shared credentials in frontend source). Header `Responder Console / Test Environment`. Priority ordered alert table: CRITICAL, HIGH, MEDIUM, LOW, then chronological. Filter by status, severity, newest. Alert detail reveals brief description and manually entered location. `Acknowledge` action verifies responder role on the server and persists exactly one responder acknowledgment event. Must not say "help dispatched". Refresh via short polling; web sockets not required.

## 4. Visual direction
Professional dark navy/neutral base, red accent only for high-severity or SOS actions; restrained dashboard. Clear status chips and metric numbers. No intimidating sirens, fake dispatch maps, or overproduced marketing animations. Layout should work on a 1366x768 laptop; keyboard accessible focus and readable contrast. Use semantic headings and a compact legend explaining the difference between `server received` and `responder acknowledged`.

## 5. Golden 5-minute live demonstration

1. **0:00–0:35:** open sender and responder views; explain sockets/TCP and separate acknowledgment layers.
2. **0:35–1:15:** send a LOW synthetic SOS in Normal mode; see `SERVER_RECEIVED`; acknowledge from responder; sender status transitions.
3. **1:15–2:10:** enable Temporary disconnect; submit HIGH alert; demonstrate persisted `QUEUED` state; reset; worker retries same UUID; alert arrives.
4. **2:10–3:05:** enable ACK lost for one message; send; server stores it, sender retries; database still has *one* alert record; duplicate counter increments.
5. **3:05–4:10:** show TLS packet capture and explain ciphertext versus readable application content; show exported measurements and comparative graph. Do not show or expose private keys.
6. **4:10–5:00:** show separate NS2 trace/plot: baseline vs imposed delay/loss; state distinction from running application's simulated faults; conclude limitations.

## 6. Test acceptance table

| ID | Trigger | Expected observable result |
|---|---|---|
| T01 | Normal submission | Exactly one server row, SERVER_RECEIVED; responder sees it |
| T02 | Responder acknowledges | Exactly one acknowledgment; sender can poll updated state |
| T03 | Sender offline | Same UUID remains on disk and QUEUED until reconnection |
| T04 | Lost application ACK after commit | Client retries same UUID; server record count=1; dedup count increases |
| T05 | Sender process restarted | Pending queue survives and can be sent after restart |
| T06 | Unauthorized sender token | No alert created; error logged without sensitive detail |
| T07 | Unauthorized responder token | Cannot read or acknowledge alerts |
| T08 | Invalid fields / oversize frame | Clean rejection, no crash or stored bad row |
| T09 | Nonmatching TLS certificate | Connection rejected; do not downgrade security |
| T10 | High app-level latency | Measured application-level timings reflect delay |
| T11 | Same ID different content | Explicit conflict / reject, not silent mutation |
| T12 | Normal vs fault-injected batch | Export real raw records and derived ratios, no fabricated metrics |

## 7. Report and metrics definitions

`Unique delivery ratio = unique alert IDs durably received before observation deadline / unique alert IDs submitted * 100`.

`Server receipt latency = server_received_at - created_at`, using clock synchronization caveat (same-host demo recommended). For comparison runs prefer client-monotonic elapsed from submit to confirmed receipt; document that acknowledgment delay may inflate measured *confirmed* latency if the server already stored an alert. Report separate `time-to-confirmation` and `time-to-responder-ack` when available.

`Retry count = total send attempts - first attempts` summed per alert, never TCP retransmission count.

`Duplicate suppression = duplicate alert submissions rejected/recognized by UNIQUE alert ID`, not TCP duplicate segments.

`p95`: state percentile method and sample size; if no successful receipts, N/A. `Pending at deadline` must remain visible rather than quietly counting as success.

## 8. Teacher presentation / viva

**Title:** SafeSignal: Reliable SOS Messaging over Unstable Networks

**Slides (6):** problem & limitations; architecture; alert wire format & state machine; security/queuing/dedup; experiments & results (only actual outcomes); conclusion & future scope.

**Likely questions:**
- Why TCP if you also retry? TCP protects transport, not application server commit/confirmation or responder action.
- Why UUID? Stable idempotency key for ambiguous retries.
- Why SQLite? Lightweight durable local and server state for prototype.
- Why TLS? Confidentiality, integrity and server authentication in transit; no homegrown crypto.
- What is ACK? Distinguish TCP ACK, app server receipt and human responder ACK.
- Why exponential backoff? Avoid hammering a temporarily unavailable endpoint.
- What if the internet is fully down? Only local queuing; no transmission until path returns.
- Does "received" mean emergency services responded? No.
- How is packet loss measured? In NS2 or Wireshark-derived captured trace; app-layer injected dropped receipts are a separate test.

## 9. Boundaries
All names and alerts synthetic. Avoid real contact details and live geographic tracking. Clear the demo database between runs; documented test-data retention and reset.
