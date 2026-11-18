# SafeSignal — Research, Existing Work, Scope and Differentiation

**Project:** SafeSignal: A Secure, Reliable Emergency Alert Delivery System for Unstable Networks  
**Course:** Computer Networks Lab (24B15CS313), JIIT Noida  
**Status:** implementation specification, not a claim that the application has been built  
**Research checked:** 18 November 2026

## 1. Source of truth and preservation of synopsis

The team's six-page synopsis proposes an emergency-alert *prototype* with: sender, central server and authorized responder; socket-based TCP; TLS; SQLite; persistent outgoing queue; exponential-backoff retries; deduplication by unique alert ID; explicit server-received and responder-acknowledged stages; Wireshark; and separate NS2 experiments. It forbids promising delivery through permanent outages or replacing real emergency services. Preserve these requirements. Proposed additions in this pack are enhancements, not historical claims from the synopsis.

Team roles proposed in synopsis: Saumya — server/database/status; Sunidhi Singh — sender/UI/queue; Mehak Verma — security/Wireshark/NS2/testing. All members participate in integration and presentation. Reassign if needed and document actual work honestly.

## 2. What has already been done

| System / reference | Demonstrated capability | Why SafeSignal should differ |
|---|---|---|
| Briar | Encrypted messaging; nearby Bluetooth/Wi-Fi and other offline synchronization | Out of scope to build offline mesh; SafeSignal teaches measurable central-server alert delivery and responder acknowledgment |
| ntfy | Lightweight, open-source HTTP publish/subscribe notifications, mobile/desktop clients, optional self hosting | SafeSignal is not a generic notification fanout; it measures sender-to-server persistence and responder handling in degraded network tests |
| Meshtastic | Off-grid LoRa mesh messaging via dedicated hardware | No radio hardware or mesh routing in this small college prototype |
| TCP (RFC 9293) | Reliable ordered byte transport, TCP retransmissions | TCP success alone is NOT proof an alert was durably stored or seen by a responder |
| TLS 1.3 (RFC 8446) | Authenticated encrypted transport | Use existing Python ssl rather than invent encryption |
| HTTP idempotency guidance (RFC 9110) | Retry safety requires idempotent application semantics | UUID + server UNIQUE constraint makes repeated submissions safe after an ambiguous acknowledgment loss |

### Verified primary URLs
- Briar architecture: https://www.briarproject.org/how-it-works/
- Briar documentation: https://briarproject.org/quick-start/
- ntfy source: https://github.com/binwiederhier/ntfy
- ntfy documentation: https://github.com/binwiederhier/ntfy/blob/main/docs/index.md
- Meshtastic firmware: https://github.com/meshtastic/firmware
- TCP: https://www.rfc-editor.org/rfc/rfc9293
- TLS 1.3: https://www.rfc-editor.org/rfc/rfc8446
- Idempotency: https://www.rfc-editor.org/rfc/rfc9110#section-9.2.2
- Python socket: https://docs.python.org/3/library/socket.html
- Python ssl: https://docs.python.org/3/library/ssl.html
- Python sqlite3: https://docs.python.org/3/library/sqlite3.html
- Wireshark docs: https://www.wireshark.org/docs/
- ns-2 information: https://www.isi.edu/websites/nsnam/

These sources are comparative references and implementation documentation, not evidence that any proposed SafeSignal feature has already been tested. Do not copy source code from third-party repos or claim originality for common patterns.

## 3. Gap / contribution (carefully stated)

Not an assertion that a novel protocol was invented. The educational contribution is an **integrated, observable demonstration** of: (1) local persistence when disconnected; (2) authenticated socket transport; (3) server receipt versus responder acknowledgment; (4) deduplication after a lost acknowledgment; (5) measurable performance under reproducible impairment. These concerns are individually well known; the combination makes a useful CN lab demonstrator.

## 4. Prioritized features

**MUST BUILD / MVP**
1. Form: severity LOW/MEDIUM/HIGH/CRITICAL, short description, optional manually entered location (never geolocate without consent).
2. Stable alert UUID and persisted local SQLite outbox before network transmission.
3. Python TLS-over-TCP sender/server using length-framed JSON; server validates token, role and request size.
4. SQLite alert storage with UUID UNIQUE constraint; sender receipt only after durable commit.
5. Separate authenticated responder UI to list and acknowledge alerts; sender displays both statuses.
6. Retry after network errors using capped exponential backoff with jitter; crash/restart safety.
7. Observable audit timeline and deterministic simulated network failures.
8. Basic evaluation scripts, metrics export and README with exact run steps.

**HIGH-VALUE ADDITIONS (small scope)**
A. Network Chaos Lab: adjustable app-layer delay, drop-server-ACK and sender disconnect. Show a visible banner **Simulation only**. Never pretend app-layer dropped acknowledgments are physical packet loss.
B. Alert Journey Timeline: QUEUED → SENDING → SERVER_RECEIVED → RESPONDER_ACKNOWLEDGED; preserve timestamps and attempts.
C. Evidence Lab: same synthetic alert batch sent through single-attempt baseline vs retry-enabled method; export raw CSV and actual chart(s).

**OPTIONAL ONLY IF EVERYTHING ABOVE PASSES**
- Keyboard accessibility and reduced-motion support.
- Export responder timeline as CSV.
- One UDP heartbeat experiment as a separately isolated bonus (never use UDP for alert delivery).

**CUT / FUTURE WORK**
- Mobile apps, GPS/map providers, SMS/WhatsApp integration, direct emergency dispatch, external emergency APIs, live citizen feeds, Bluetooth/mesh relays, multi-cloud routing, ML urgency prediction, background push, production deployment, paid hosting, voice/video/file attachments and realtime geofencing.

## 5. Truthful presentation of networking

- TCP can retransmit a lost TCP segment. SafeSignal's **application retry** handles situations when the client does not know whether an alert was stored, such as an interrupted connection or lost *application receipt message*.
- Do not claim exactly-once delivery over networks. Claim **at-least-once submission attempts with effectively once-only alert record creation by ID**.
- Local queue is only reliable while local disk remains intact and application worker is running; browser tab alone does not run network workers.
- Sender status SERVER_RECEIVED means durable server acceptance; it does not mean anyone has read or acted on the alert.
- An offline sender cannot transmit; it can queue and attempt again after connectivity returns.
- Do not equate simulator drop percentage with measured IP packet loss.
- NS2 is a separate, controlled wired topology experiment; unless an actual bridge is built, do NOT claim the Python application ran inside NS2.

## 6. Security and ethics

Use only synthetic alerts and controlled devices/networks. Keep test server loopback-bound by default. Real emergency response is explicitly unsupported. Use HTTPS locally for browser services when feasible, and TLS with certificate verification on TCP transport; never disable verification or hardcode real credentials. Never commit `.env`, certificates' private keys, tokens or SQLite data. Acknowledge limitations: no operational availability guarantee, no formally verified security, no end-to-end encryption from user to responder (server can see plaintext after TLS termination).

## 7. Presentation positioning (one paragraph)

"SafeSignal is a secure emergency-alert delivery prototype for intermittent networks. The sender queues alerts locally, a TLS/TCP server stores them once even if retries occur, and an authorized responder separately acknowledges them. In a controlled network impairment demo, we inspect the alert timeline and compare single-attempt delivery with retry-and-deduplication behavior. This is an educational simulator, not a replacement for emergency services."

## 8. Research limitations

This is a selected review of representative repos, official protocols and project documentation, **not** a systematic literature review or proof no other project implements these features. Features and metrics in these documents are **requirements** until the code and experiments actually establish them. Do not invent measured improvements or screenshots.
