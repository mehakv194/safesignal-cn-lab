# SafeSignal — Project Idea, Features and Complete User Workflow

Current implementation guide · Prepared 19 November 2026

**SIMULATION — NOT FOR REAL EMERGENCIES**

This document describes what the current code actually implements. Planned possibilities are identified separately. It is a product and workflow explanation, not a claim that a university or emergency service operates this system.

## 1. What is SafeSignal?

SafeSignal is a campus incident reporting and response coordination web app. A sender reports a concern, a response desk takes ownership, records progress, and closes the incident with a resolution summary. The sender can follow that journey from the same website.

It also serves as a Computer Networks project: beneath the dashboard, reports travel through a SQLite-backed queue and a verified TLS/TCP connection. The system demonstrates application receipts, retries, duplicate prevention and recovery when the underlying storage survives.

In one sentence: **SafeSignal turns a synthetic campus concern into a trackable incident with delivery confirmation, response ownership, progress updates and a recorded outcome.**

The useful result is more than a submitted form. It is a shared incident record answering:

- What was reported, where, and at what priority?
- Did the server actually store it?
- Has the response desk acknowledged it?
- Which response team is assigned?
- Is response work underway?
- What was the final recorded resolution?

## 2. The problem and the idea

Imagine a concern reported through an informal message: the reporter may not know whether anyone received it, who is handling it, or whether it was resolved. Meanwhile, the person coordinating responses may have no structured queue or consistent history.

SafeSignal demonstrates a structured alternative. Each report gets an identifier, category, priority and timestamps. The response desk sees a queue, moves the report through controlled stages, and records notes. The sender sees the resulting updates.

The project addresses two different questions:

| Question | Implemented response |
|---|---|
| Can a report be delivered reliably when an application connection fails temporarily? | Save before sending; retry the same identifier; suppress repeat submissions. |
| Can people follow what happens after delivery? | Assign a team; acknowledge; start response; add notes; resolve; expose the timeline. |

A network receipt alone cannot answer the second question. That is why delivery state and incident progress are separate.

## 3. What kind of application is it?

It is **one hosted web app with two role dashboards**, rather than two websites that users must run separately.

| Entry point | Purpose |
|---|---|
| https://safesignal-campus.onrender.com/ | Public landing page and role selection. |
| https://safesignal-campus.onrender.com/sender/ | Sender login and reporting dashboard. |
| https://safesignal-campus.onrender.com/responder/ | Response-desk login and coordination dashboard. |
| `/healthz` | Operational readiness check; not a user dashboard. |

These are the deployed addresses recorded on 18 November 2026. This document does not represent a fresh uptime check on 19 November.

Users only need a browser and the appropriate access token. They do not need to run Python, open a terminal, or connect directly to the socket server to use the hosted version.

Internally, the app still has browser-facing code, a worker and a socket server. Those are implementation components inside one Python hosting service. They are not separate hosting subscriptions or separate public websites.

## 4. Roles and access

### Sender

The sender can create synthetic reports, inspect the shared sender queue, search and filter incidents, open incident details, and follow response updates. The sender cannot acknowledge, assign or resolve incidents.

### Responder / campus response desk

The responder can inspect the server's incident queue, choose an authorized response team, acknowledge ownership, start work, add progress notes and resolve incidents.

The assigned desk identity is **Campus Response Desk**. The available team labels are **Campus Safety**, **Medical Team** and **Facilities Team**. These are synthetic assignments recorded in the app; selecting one does not contact an actual team.

### Project owner

The owner manages the hosting configuration and distributes role access tokens. There is no separate in-app administrator dashboard.

### Current account model

There is one shared sender token and one shared responder token. This is not individual student registration or individual staff authentication. People sharing a role share its view and authority; the system does not provide a private incident history per student or identify which individual staff member made an update.

The owner retrieves the hosted tokens from the service's Render Environment page:

- `SAFESIGNAL_SENDER_TOKEN` for the sender dashboard.
- `SAFESIGNAL_RESPONDER_TOKEN` for the responder dashboard.

The session secret is an infrastructure setting, not a user login token. Tokens must not be embedded in reports, screenshots or public project documentation. Local demo tokens are separate from hosted tokens.

## 5. Complete journey at a glance

```text
Open SafeSignal
      |
Choose Sender -> sign in -> Report incident
      |                       |
      |                 Validate the form
      |                       |
      |                 Save in SQLite outbox
      |                       |
      |                 Worker sends over TLS/TCP
      |                       |
      |                 Server commits the incident
      |                       |
      |                 Server receipt confirmed
      |                       |
Choose Responder -> sign in -> Review incident queue
                              |
                        Assign & acknowledge
                              |
                         Start response
                              |
                        Add progress notes
                              |
                    Resolve with a written summary
                              |
                Sender sees the final recorded outcome
```

The two people can work in separate browser sessions. They do not need to take turns on the same device.

## 6. Sender journey in detail

### Step 1 — Enter the app

The sender opens the landing page, chooses the sender dashboard, and signs in with the sender token. A valid login establishes the sender session. An invalid token does not grant access.

### Step 2 — Understand the dashboard

The sender sees total reports, active incidents, open critical incidents, resolved incidents, recent activity and incident charts. A new deployment may legitimately show zero records. The charts are derived from saved records rather than decorative sample numbers.

### Step 3 — Create a report

The sender clicks **Report incident** and completes the form.

| Field | Current choices or rules | Purpose |
|---|---|---|
| Category | MEDICAL, FIRE, SAFETY, INFRASTRUCTURE | Describes the type of concern. |
| Priority | CRITICAL, HIGH, MEDIUM, LOW | Records urgency selected by the sender. |
| Description | 10–300 characters after trimming for validation | Explains the synthetic concern. |
| Location | Up to 120 characters; may be blank | Describes the place in text. |
| Incident identifier | Canonical UUID generated by the app | Tracks the report and prevents duplicate records on retry. |
| Creation timestamp | Generated in UTC | Records when the report was created. |

Category and urgency are independent. A facilities report is not automatically low priority, and the app does not infer urgency using AI. It also does not automatically select a response team.

The form has no photo upload, GPS capture, map picker or reporter contact profile. The original report content is not editable through the current UI after submission.

### Step 4 — Save before transmission

Once validation succeeds, the report is inserted into the outbox before network transmission. Its initial delivery status is `QUEUED` and its incident progress is `REPORTED`.

In the hosted app, this outbox is on the hosting server, not inside the sender's phone or browser. A browser with no internet cannot submit a new report to that hosted outbox. This is not an offline-first mobile app.

### Step 5 — Observe delivery

A background worker attempts delivery. During an attempt the delivery status becomes `SENDING`. A confirmed server commit advances it to `SERVER_RECEIVED`.

If a connection fails, the saved report returns to the queue and retries later with the same UUID. This behavior depends on the process running again, the backend becoming reachable, and the SQLite data surviving.

The sender should read `SERVER_RECEIVED` as **the system stored the report**, not as a promise that somebody has started responding.

### Step 6 — Follow the response

The sender opens the incident detail page to see its progress steps, assigned team, latest note, timestamps and recent timeline events. Updates from the response desk become visible through polling.

The browser refreshes designated live regions roughly every five seconds when the tab is visible and it is safe to do so. It avoids overwriting an actively edited form. This is periodic polling, not a WebSocket stream or push notification service.

### Step 7 — View closure

After the response desk resolves the incident, the sender sees `RESOLVED`, the assigned team, a resolution summary and a resolution timestamp. There is no sender approval step, rating, dispute process or reopen button in the current implementation.

## 7. Responder journey in detail

### Step 1 — Sign in

The responder uses the responder token. Sender credentials cannot perform responder actions.

### Step 2 — Review and prioritize

The response overview shows aggregate workload and recent events. The incident workspace supports category, priority, progress and text filtering. Text search matches descriptions and locations.

The backend's default queue ordering puts CRITICAL before HIGH, MEDIUM and LOW, then uses server receipt time. The responder queue is paginated in groups of four to keep network responses bounded. Dashboard totals are calculated over the records, not just the four visible entries. Filtering the incident table does not turn the global overview cards into filtered totals.

### Step 3 — Inspect an incident

The detail page exposes the description, location, urgency, category, transport receipt and response history. A newly reported incident has no team assigned.

### Step 4 — Assign and acknowledge

The responder chooses Campus Safety, Medical Team or Facilities Team, optionally writes an initial note, and clicks **Assign & acknowledge**.

The server saves the selected team, Campus Response Desk identity and acknowledgment timestamp. Progress changes from `REPORTED` to `ACKNOWLEDGED`. The corresponding delivery/receipt field becomes `RESPONDER_ACKNOWLEDGED`.

Acknowledgment means the authenticated demo desk recorded ownership. It does not prove that a real responder was notified, dispatched, arrived or accepted the assignment outside this website.

### Step 5 — Start response

The responder clicks **Start response**. Progress advances from `ACKNOWLEDGED` to `IN_PROGRESS`. An optional note can describe the simulated action being taken.

### Step 6 — Record progress

While acknowledged or in progress, the responder can add a progress note of 5–200 characters. A note adds an audit event and changes the latest displayed note without advancing the lifecycle stage.

There is no chat conversation: senders cannot reply with messages in this workflow. There are no actual team inboxes or outbound messages.

### Step 7 — Resolve

From `IN_PROGRESS`, the responder provides a resolution summary of 5–200 characters and clicks **Resolve incident**. The server records the terminal state and resolution timestamp. The sender's synchronized copy eventually reflects the same result.

The app rejects resolving a newly reported incident or going backward from resolved to in progress. There is no reassignment or reopening workflow after the initial claim in the current UI.

## 8. Two state systems: the essential distinction

### Delivery and receipt states

| State | Meaning | Does it mean the concern is resolved? |
|---|---|---|
| QUEUED | Saved in the sender outbox, awaiting an eligible attempt. | No. |
| SENDING | A delivery attempt is underway. | No. |
| SERVER_RECEIVED | Server committed the report and the sender received confirmation. | No. |
| RESPONDER_ACKNOWLEDGED | Response desk explicitly acknowledged ownership. | No. |

### Incident lifecycle states

| State | Meaning | Next normal action |
|---|---|---|
| REPORTED | Incident exists but no response ownership is recorded. | Assign & acknowledge. |
| ACKNOWLEDGED | A response team and desk ownership have been recorded. | Start response; optionally add notes. |
| IN_PROGRESS | Response work is recorded as underway. | Add notes or resolve. |
| RESOLVED | Desk has recorded a final summary and closure timestamp. | View history; no further update in the current workflow. |

An incident can be `RESOLVED` while its delivery field remains `RESPONDER_ACKNOWLEDGED`. That is expected: one field describes receipt, and the other describes the outcome of the response workflow.

## 9. A complete example

This example is fictional and intended only for demonstration.

| Stage | Action | Result visible in the app |
|---|---|---|
| Report | Sender submits “TEST ONLY: first-aid assistance requested during a sports drill,” MEDICAL, HIGH, “Synthetic Sports Centre.” | New UUID; REPORTED lifecycle; queued delivery. |
| Deliver | Worker sends the saved payload to the private TLS server. | SERVER_RECEIVED after server commit and receipt confirmation. |
| Own | Desk selects Medical Team and acknowledges. | Team displayed; ACKNOWLEDGED; acknowledgment timestamp and audit event. |
| Work | Desk clicks Start response and records a drill-related note. | IN_PROGRESS and updated timeline. |
| Update | Desk adds “TEST ONLY: practice first-aid check completed.” | New note event; lifecycle remains IN_PROGRESS. |
| Close | Desk writes “TEST ONLY: drill completed; synthetic participant cleared.” and resolves. | RESOLVED, final summary and closure timestamp. |
| Observe | Sender checks the detail page. | Same assignment and final outcome, with recent history. |

The app records the desk's statements. It does not independently verify that the described physical action happened.

## 10. Feature inventory

| Feature | What currently works |
|---|---|
| One website | Landing page and both role dashboards under one origin. |
| Role login | Separate shared tokens and sessions for sender and responder. |
| Report form | Category, urgency, bounded description, optional text location. |
| Persistent outbox | SQLite queue saved before sending; durability depends on storage. |
| Reliable submission | Application retries with exponential backoff and jitter. |
| Duplicate prevention | Same UUID and payload returns the existing receipt instead of inserting another incident. |
| Conflict detection | Same UUID with changed payload is rejected as an identifier conflict. |
| Secure transport | Public HTTPS and a private certificate-verified TLS/TCP connection. |
| Response coordination | Team assignment, acknowledgment, start, notes and resolution. |
| Live updates | Periodic dashboard refresh and worker status synchronization. |
| Incident discovery | Text search, category, severity and lifecycle filters. |
| Analytics | Actual totals, active count, open critical count, resolved percentage, seven-day activity and category distribution. |
| Timeline | Recent timestamped server audit events; local history fallback for sender where available. |
| Synthetic walkthrough | Sender button creates four clearly labeled examples through the real queue. |
| Network lab | Explains delivery, backend reachability, retries and duplicate suppression; optional local faults. |
| Evidence Lab | Displays experiment evidence and allows available CSV, JSON and SVG downloads plus browser PNG chart export. |
| Local lab | One-origin local launcher; original separate-process networking launcher remains available. |

The visual design uses a white dashboard, dark green and turquoise accents, rounded panels, chart cards, a sidebar and incident detail views. These present real saved state; they are not a claim of activity when no reports exist.

## 11. What happens behind the screen?

```text
Browser
  | HTTPS
Render ingress -> Waitress -> Flask sender/responder routes
                              |
                    Sender SQLite outbox
                              |
                       Background worker
                              | private verified TLS over TCP
                       Socket request server
                              |
                     Server SQLite + audit
                              |
                       Receipt/status reply
                              |
                Worker sync + browser periodic refresh
```

The sender browser submits to Flask. Flask validates and queues the payload. A worker runs independently of the browser's lifetime. The socket server validates a role-authorized request, commits storage changes, and returns a bounded response. The responder dashboard queries and updates the same server through role-authorized socket requests.

Transport uses a four-byte big-endian message length followed by UTF-8 JSON, bounded to 16 KiB per frame. TCP is a byte stream, so explicit framing tells the receiver where a complete message ends. Requests use timeouts and bounded inputs rather than assuming every connection completes normally.

Retries wait roughly 0.4–0.5 seconds initially, grow exponentially and are capped at 30 seconds before jitter; the worker's approximately one-second scheduling loop also affects observed timings. This reduces tight repeated requests during a failure.

Server storage uses UUID uniqueness and a canonical payload hash. A database transaction completes before the server sends its receipt. This provides duplicate-safe record insertion under retransmission, not a blanket promise of exactly-once execution across every future feature or external system.

## 12. Data and history

There is no separate cloud database product. The app uses two SQLite files: one for sender outbox state and one for server incidents and audit data.

| Record group | Examples of stored fields |
|---|---|
| Original report | UUID, category, severity, description, location, creation timestamp. |
| Delivery tracking | Attempt count, next attempt time, last error, receipt timestamps. |
| Incident progress | Lifecycle stage, assigned team, assigned desk, latest note, resolution timestamp. |
| History | Queue/transmission journey and server event timestamps/details. |
| Submission observations | New, duplicate or identifier-conflict submission outcomes. |

The detail page exposes the latest eight server audit events. This is a recent-history view, not an unlimited visible event browser. The underlying audit table may contain earlier events while its database survives.

Event times are shown in UTC. The UI may shorten identifiers for readability, while storage retains the full UUID.

## 13. Failures and recovery

| Situation | Current behavior and boundary |
|---|---|
| Invalid report | Validation rejects it; no valid incident should be claimed as submitted. |
| Wrong login token | Access remains denied; login attempts are throttled. |
| Internal backend temporarily unavailable | Saved queued reports retry; responder pages can report unavailability. |
| Server stores report but receipt is lost | Same UUID is retried; duplicate insertion is prevented and existing receipt returned. |
| Browser is closed after successful queue submission | Worker can continue while the hosting process remains running. |
| Browser has no internet before submission | No new hosted report is saved; there is no browser offline outbox. |
| Process restarts with intact SQLite | Interrupted SENDING entries recover to QUEUED. |
| Free host discards SQLite | Reports/history can disappear; retry cannot recover a lost outbox. |
| Page polling fails | Browser retains the last rendered state; it must not be assumed current. |
| Update confirmation is uncertain | Refresh the incident before retrying; the response may have been committed. |
| Permanent outage | No guaranteed delivery or response; eventual recovery needs working infrastructure and retained data. |

## 14. Networking experiments and Evidence Lab

The lab compares a single-attempt submission policy with retry plus duplicate prevention using synthetic alerts and controlled application faults.

Optional local presets include normal connection, approximately 1,500 ms application delay, first application receipt lost, and temporary sender disconnect. **Fault injection is disabled in the hosted deployment configuration.** The hosted Network Lab can therefore explain the mechanism without exposing those controls as active.

Experiment outputs include raw per-alert CSV, JSON summaries and an SVG comparison chart. Metrics include unique server receipt ratio, pending delivery, confirmed receipts, median and nearest-rank p95 confirmation latency, retries and duplicate suppressions. Confirmation timing is not the same as human acknowledgment or resolution time.

A previously recorded small chosen scenario stored 4 of 6 alerts under single attempt and 6 of 6 under retry, with two duplicate suppressions. This demonstrates that scenario only; it is not a universal reliability percentage, a benchmark of the public host or proof of handling real emergencies.

The hosted Evidence Lab can load reviewed local-run artifacts and labels them as recorded local evidence. It is not continuously benchmarking the live service. Wireshark and NS2 have separate instructions; they were not executed on the implementation host, and there is no claimed NS2-to-Python integration. Application faults are not measured IP packet loss.

## 15. Hosting, access and cost boundaries

The deployment uses one Render Free Python service with one instance, SQLite under `/tmp/safesignal`, no paid persistent disk, and no Supabase or other external database. No card was added during deployment.

The URL is stable while the service exists; “permanent link” does not mean guaranteed lifetime service or uninterrupted availability. Free instances can sleep after inactivity and need time to start again. Restart, redeployment or free-host lifecycle events can reset the SQLite filesystem. The interface discloses that limitation.

This means the current cloud version is suitable as a hosted demonstration, but it does **not** satisfy guaranteed incident retention across hosting restarts. Local SQLite survives normal application restarts while the local files remain intact. The free-only/no-external-database decision is an explicit project constraint, not something the queue can solve by itself.

## 16. Security measures and their limits

Implemented safeguards include role checks, token comparison, session cookies, CSRF validation for form writes, escaped HTML, explicit Host validation, HTTPS enforcement for hosted role pages, bounded request/frame sizes and field validation. Hosted role cookies are Secure, HttpOnly and SameSite=Lax. The internal TLS client verifies the socket server certificate.

These controls do not create individual accountability, multi-tenant isolation, at-rest database encryption, mutual TLS, end-to-end encryption from reporter to real responder, or production emergency-service certification. Shared tokens grant shared authority. There is no password recovery, institutional SSO or MFA in the app.

The single-instance architecture is intentional. Running several replicas would require revisiting SQLite, worker ownership and shared state rather than just increasing the instance count.

## 17. What is the end result?

### For the sender

A submitted concern becomes a named, trackable incident. The sender can distinguish queueing from server receipt, see response ownership and progress, and read the final recorded resolution.

### For the response desk

Reports become a prioritized, searchable workload with structured stages and recent history. The desk can see which incidents are waiting, active or closed rather than treating every report as an unrelated message.

### For the academic project

The result is a working web demonstration connecting application design with network reliability concepts: framing over TCP, verified TLS, persistence before send, application receipts, retries, deduplication, state synchronization and evidence-based evaluation.

### What “successful” means

A successful walkthrough ends with one unique stored report, confirmed server receipt, an assigned synthetic team, acknowledgment, work in progress, a written resolution, and matching sender-visible progress. Aggregate counts and the timeline reflect the saved actions.

It does not prove that assistance was dispatched, that a physical hazard was removed, or that a reporter is safe. The final state is a recorded response-desk outcome in a simulation.

## 18. What is deliberately not implemented?

The current project has no real emergency dispatch integration, phone calls, SMS, email alerts, mobile push, GPS/live maps, attachments, AI triage, automatic escalation, arrival tracking or real team messaging.

It also has no individual accounts, per-student private records, admin management portal, assignment reassignment, incident reopening, sender chat, browser offline submission, guaranteed cloud retention, production backup/restore workflow, service-level agreement or verified large-scale performance capacity.

These are scope boundaries, not hidden capabilities. Possible future work could address individual accounts, notifications, storage durability and operational procedures, but none is necessary to explain the current working demonstration, and none should be presented as completed.

## 19. Suggested demonstration sequence

1. Open the public landing page and explain the two role dashboards.
2. Sign into Sender and create one clearly synthetic report.
3. Show the UUID, lifecycle stage and confirmed server receipt.
4. Open Responder in another session and find the same report.
5. Assign a suitable synthetic team and acknowledge ownership.
6. Start response and add a progress note.
7. Show the sender receiving progress updates.
8. Resolve with a meaningful synthetic summary.
9. Show final sender-visible closure, audit events and changed dashboard counts.
10. Explain queueing, TLS, retries and duplicate prevention. Use a local fault-enabled lab for actual fault injection.
11. Open Evidence Lab and distinguish recorded experiment results from live dashboard data.
12. State the shared-token and free-host retention limits.

The **Create 4 sample incidents** button is an optional shortcut for populating a walkthrough. It inserts actual new synthetic incidents through the queue each time; it does not merely animate cards or replace the need to acknowledge and resolve them.

## 20. Implementation references and verification scope

This description was checked against the current implementation, rather than treating the original starter documents as completed functionality.

| Source | What it establishes |
|---|---|
| `safesignal/models.py` | Categories, severities, teams, lifecycle names and report validation. |
| `safesignal/web.py` | Role routes, login, forms, filtering, incident actions and evidence access. |
| `safesignal/templates/home.html` | Dashboard cards, charts, incident list and local fault controls. |
| `safesignal/templates/incident.html` | Detail journey, ownership, notes and action buttons. |
| `safesignal/static/app.js` | Five-second browser polling and chart export behavior. |
| `safesignal/sender_store.py` | Persistent outbox, attempt state and progress synchronization. |
| `safesignal/sender_worker.py` | Delivery retry loop and polling until resolution. |
| `safesignal/server_store.py` | Commit-before-receipt, deduplication, transitions, audit and aggregates. |
| `safesignal/hosted.py` | One service, internal TLS server, worker and mounted dashboards. |
| `safesignal/metrics.py` | Experiment summary definitions and exports. |
| `tests/test_incidents.py` | Full lifecycle, authorization, transition and aggregation regression checks. |
| `docs/hosting.md` and `docs/findings.md` | Deployment record, constraints and previous verification evidence. |

The recorded deployment checks passed 28 tests on Windows and Linux and verified public landing, health and role login pages. Authenticated public incident actions were not tested because deployment tokens were not inspected. This documentation task reads the implementation; it does not rerun the application test suite, perform a new production audit or validate physical emergency outcomes.
