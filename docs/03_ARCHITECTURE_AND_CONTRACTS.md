# SafeSignal — Technical Architecture, Data Model and Wire Protocol

## 1. Non-negotiable design
Use **Python 3.11+ standard library first**: `socket`, `ssl`, `sqlite3`, `json`, `threading`, `uuid`, `time`, `logging`, `argparse`, `secrets`, `hashlib`, `unittest` or `pytest`. `Flask` only for local web sender and responder pages. HTML/CSS/vanilla JS; Chart.js is optional but can instead render charts with matplotlib and link resulting PNGs. No React/Next.js, Redis, Docker, paid services, external data APIs, message brokers, or cloud databases. Prioritize easy installation and human-readable code.

### 1.1 Components and data flow

```text
Browser sender (127.0.0.1:5001)
    | HTTP on localhost ONLY, authenticated locally
    v
Sender Flask app + SQLite outbox + persistent worker
    | length-prefixed JSON over TLS/TCP (client verifies server cert)
    v
Python socket server (127.0.0.1:9443)
    | token/role validation; atomic INSERT OR detect UUID conflict
    v
Server SQLite: alerts + audit + acknowledgments
    ^
    | local backend access, never directly from browser
Responder Flask app (127.0.0.1:5002)
    ^
    | browser login with session + CSRF protection
Browser responder (127.0.0.1:5002)

Separate optional experiments:
NS2 TCL wired-topology scripts -> .tr traces -> AWK/Python parsing -> CSV/plots
Wireshark capture of TCP/TLS loopback or authorized lab LAN traffic
```

**Architecture caveat:** both Flask web processes may use same server SQLite file if running on the same laptop. Central server must remain the owner of authoritative alert state. A simpler choice is for responder Flask to call an authenticated server API/socket request, not write directly to SQLite. Implement this simpler separation: browser -> responder Flask -> authenticated TCP request -> server DB; likewise sender status requests. Keep one server DB owner to avoid lock and coupling. Single laptop is the default demo; LAN adaptation is optional.

### 1.2 UI process security choice
Run browser-facing endpoints on `127.0.0.1` only; require responder session login, secure random secret loaded from `.env` or environment, CSRF token on state-changing forms, and `HttpOnly; SameSite=Lax` session cookies. Local HTTP on loopback is a demo-only concession; state clearly that LAN/public deployment needs HTTPS for all browser endpoints. Do not expose ports to the public internet.

## 2. Project tree (target)

```text
safesignal/
  README.md
  LICENSE
  .gitignore
  .env.example
  requirements.txt
  docs/
    01_RESEARCH_AND_SCOPE.md
    02_PRODUCT_AND_DEMO.md
    03_ARCHITECTURE_AND_CONTRACTS.md
    04_PHASED_IMPLEMENTATION.md
    05_CODEX_MASTER_PROMPT.md
    findings.md
    experiment-results.md
  safesignal/
    __init__.py
    protocol.py            # 4-byte big-endian length prefix + bounded JSON
    models.py              # schemas, statuses, validators
    auth.py                # role/token verification, constant-time compare
    tls.py                 # verified SSL context factory
    server.py              # threaded TCP request handler
    server_store.py        # SQLite transactions, idempotency, audit
    sender_store.py        # durable SQLite outbox
    sender_worker.py       # retry scheduler and status polling
    sender_web.py          # Flask sender UI
    responder_web.py       # Flask responder UI
    faults.py              # app-layer test-only fault injection
    metrics.py             # calculate / export metrics
    config.py
    templates/
      sender.html
      responder.html
      alert.html
      evidence.html
    static/
      styles.css
      app.js
  scripts/
    init_demo.py           # create config, synthetic demo users without secrets in git
    create_dev_cert.py     # localhost SAN certificate; private key ignored
    run_demo.py            # orchestration, print URLs and PID/process info
    reset_demo.py
    run_experiments.py
    export_results.py
  ns2/
    baseline.tcl
    impaired.tcl
    analyze.awk
    README.md
  tests/
    test_protocol.py
    test_queue.py
    test_dedup.py
    test_auth.py
    test_status.py
    test_faults.py
    test_integration.py
  artifacts/                  # generated results ignored except approved sample outputs
```

Do not mechanically create empty files. Only create files as functionality is implemented. Code layout may vary slightly; update this document if design changes and explain why.

## 3. Transport protocol (precise)

Transport: TLS-protected TCP sockets; NOT browser raw TCP; browser talks to local Flask frontend.

Framing: `4-byte unsigned big-endian length N` followed by exactly N bytes of UTF-8 JSON, max **16 KiB**; reject zero or larger frames before allocation. `recv_exact` loops until required bytes, handles timeouts/disconnect; `sendall` writes framed data. One request and one response per connection is sufficient. Each message includes `version: 1`, `type`, `request_id`, `token`. Do not log tokens or alert description to debug logs.

Example request:
```json
{
  "version": 1,
  "type": "SUBMIT_ALERT",
  "request_id": "0ce62e45-a347-43d9-a3aa-95fe0c2c6a29",
  "token": "<configured-sender-token>",
  "payload": {
    "alert_id": "d891149d-1f8b-4d8b-aad0-c58fb86cff6d",
    "severity": "HIGH",
    "description": "TEST ONLY: simulated campus alert",
    "location": "Synthetic Block A",
    "created_at": "2026-11-18T10:00:00Z"
  }
}
```

Responses: `status: OK|ERROR`, `code`, `request_id`, and minimal payload. After successfully committed new record or same-ID/same-content retransmission, return code `SERVER_RECEIVED`, `alert_id`, `server_received_at`, `duplicate: bool`. Same UUID with altered content returns `ID_CONFLICT`. Invalid tokens return generic `UNAUTHORIZED`; avoid echoing sensitive fields. Document how clock timestamps are generated as ISO8601 UTC.

Allowed types:
- `SUBMIT_ALERT`: sender token only
- `GET_STATUS`: sender token (only sender-owned alert IDs; for MVP sender identity from token)
- `LIST_ALERTS`: responder token only; max 100 per page, ordered priority then time
- `ACK_ALERT`: responder token only; repeated ACK returns existing state without duplicate event
- `GET_AUDIT`: responder token for a given alert (or sender owner if limited to own alert)
- `HEALTH`: no sensitive content; network test optional

Tokens loaded from environment; for simple demo use separate static sender and responder tokens generated by `secrets.token_urlsafe(32)`. Map token -> role and sender principal. Compare tokens in constant time. Never accept role declarations from client itself. For multi-sender demonstrations, make separately scoped tokens if feasible; do not claim multi-tenancy otherwise. Avoid tokens in URL query string; use server-side Flask configuration/session.

## 4. State machine

**Outbox (sender local):** `QUEUED -> SENDING -> SERVER_RECEIVED -> RESPONDER_ACKNOWLEDGED`.

On network error, `SENDING -> QUEUED` with attempt_count increment, last_error and next_attempt_at stored; a restart must recover stuck `SENDING` records to queued. Once server received, stop *submission retries* and poll status (no need to re-submit) until responder acknowledged. Never regress terminal state. If first app ACK lost, sender stays pending and retries same ID (server detects duplicate).

Server authoritative states: `SERVER_RECEIVED`, `RESPONDER_ACKNOWLEDGED`. No claim of "READ" or "DISPATCHED". Store acknowledgment at most once.

## 5. Storage schema (reference)

Sender SQLite `outbox`:
- `alert_id TEXT PRIMARY KEY`, `severity TEXT NOT NULL`, `description TEXT NOT NULL`, `location TEXT`, `created_at TEXT NOT NULL`
- `status TEXT NOT NULL`, `attempt_count INTEGER NOT NULL DEFAULT 0`, `next_attempt_at TEXT`, `last_error TEXT`, `server_received_at TEXT`, `responder_acknowledged_at TEXT`, `updated_at TEXT NOT NULL`
- `payload_hash TEXT NOT NULL`, `last_attempt_at TEXT`; ensure validation and migration setup.

Server SQLite `alerts`:
- `alert_id TEXT PRIMARY KEY`, `sender_id TEXT NOT NULL`, `payload_hash TEXT NOT NULL`, `severity TEXT NOT NULL`, `description TEXT NOT NULL`, `location TEXT`, `created_at TEXT NOT NULL`, `server_received_at TEXT NOT NULL`, `status TEXT NOT NULL`, `responder_acknowledged_at TEXT`, `acknowledged_by TEXT`

Server SQLite `audit`:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`, `alert_id TEXT`, `event TEXT`, `recorded_at TEXT`, `metadata_json TEXT` (no secrets)

Server SQLite `submission_attempts` or metrics counters:
- `id INTEGER PRIMARY KEY AUTOINCREMENT`, `alert_id TEXT`, `received_at TEXT`, `result TEXT` (`NEW|DUPLICATE|ID_CONFLICT`)

Use transactions and `PRIMARY KEY`/UNIQUE as final authority for dedup; use canonical payload hash built from immutable alert fields. A duplicate same-ID/same-data must not create a second alert row or second responder event. Log duplicate attempt separately. If server returns ACK, do so **after** transaction commits. SQLite timeout and short transactions; WAL optional for same-host concurrent readers.

## 6. Failure injection: explicit boundaries

`faults.py` is guarded by `ENABLE_DEMO_FAULTS=1` and local-only admin configuration. Never use for real emergency services. For lost-ACK test: server commits `SUBMIT_ALERT`, then suppresses the *application response* on the first attempt of selected alert ID, closes connection, next attempt gets duplicate response. Delay preset sleeps **before reply** (label app-layer delay, not IP propagation). Disconnect preset makes sender worker voluntarily refuse to connect while active; queued rows still persist. Track active fault preset and seed alongside experiment metadata. Fault settings must reset easily and not contaminate normal runs.

## 7. Security details

Use `ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)` with generated localhost certificate on server, and `ssl.create_default_context(cafile=...)` client with hostname verification on (`server_hostname='localhost'`). Generate a development certificate with DNS SAN `localhost` and IP SAN `127.0.0.1`, ideally via `cryptography` (listed in requirements) or clear OpenSSL command; make certificate generation cross-platform where possible. Never use `CERT_NONE`, `check_hostname=False`, or insecure fallback. TLS server-bound, role-authenticated client request; *not mutual TLS* unless actually implemented. Avoid bespoke AES-GCM to keep scope manageable; transport TLS satisfies synopsis alternative.

Other protections: request framing caps, per-socket timeout, input limits, only accepted severities, max description/location sizes, simple token-scoped rate limit, generic auth failures, no debug mode publicly, no permissive CORS, no raw HTML injected from user strings, audit role actions, no secret or DB files in Git. Encryption at rest is not claimed.

## 8. Testing and observability

Unit tests for partial TCP recv, excessive length, validation, queue recovery, backoff boundaries, duplicate insert, ID conflict, role checks, ACK idempotency. Integration test actually starts temporary TLS server (ephemeral port), sender worker and responder request against temp SQLite with synthetic data. Restore clean state after tests.

Wireshark: capture traffic on local loopback with appropriate adapter/support or on authorized LAN; `tcp.port == 9443` is a display filter. Explain TLS hides application text, but IP/ports and timing remain visible. Record environment/OS/adapter/capture filter. NS2 scripts operate independently; explicitly separate their traces from Python app logs. Run under Linux/WSL if NS2 not available natively; if installation fails, record that as an uncompleted optional lab dependency and keep main app functional.

## 9. Operating instructions Codex must supply

`python -m venv .venv`, activate on Windows PowerShell / macOS/Linux, `pip install -r requirements.txt`, copy `.env.example` to `.env`, generate dev cert/token, `python scripts/run_demo.py`, browser URLs, tests `python -m pytest -q`, simulation and export commands, graceful shutdown and reset. No hidden prerequisite; scripts must work from repo root and be well-commented.
