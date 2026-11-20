# SecureSignal implementation and operator guide

## Baseline and migration

This branch began at 523db41 in the complete Flask repository. The pre-change
suite passed 73 tests. Flask owns user sessions, the server and identity share
private SQLite, the outbox uses a separate SQLite database, and a background
worker retries length-prefixed, verified TLS/TCP operations. This release keeps
the existing transport frame, UUID, intent reconciliation, commit-before-receipt
and duplicate semantics. New cyber reports send a neutral transport envelope.
Their substantive data resides in version 1 cyber case records, and the case
plus immutable outbox intent are committed in one transaction.

Migrations 5–8 create cyber, MFA, encrypted evidence and monitoring tables.
Historical physical reports, messages, audits, users and immutable outbox rows
are preserved and are excluded from the new queues. No case data is
reclassified. Legacy responder teams are ineligible for cyber work until a
maintainer explicitly provisions a new assignment. Legacy responder sessions
cannot pass the MFA check. The historical classroom entry point stays
separate. Cyber mode rejects its HTTP routes and non-room user TLS commands.

## Configuration

For a regular local run, prepare an existing local/config.json with distinct
random sender_token, responder_token, and session_secret values (or start from
the existing repository's local configuration). Run
python scripts/run_app.py. The module entry point python -m safesignal.hosted
uses hosting variables in .env.example; it does not automatically load .env.
Set the variables in the shell or host's secret manager. Use separate
random 32-byte base64 keys for MFA and evidence, generated independently with
python -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())".
Do not commit, email, or log them. Missing MFA key prevents responder sign-in;
missing active evidence key disables upload. Incorrect old evidence keys
cannot decrypt objects. To rotate evidence keys, add a unique key ID, retain
old keys, and change SECURESIGNAL_EVIDENCE_ACTIVE. MFA key replacement is an
operator migration and must not be done as an ordinary config change.

Human accounts require verified JIIT-format addresses. SMTP stays off unless
explicitly configured; use a capture adapter in isolated tests. To promote a
verified, eligible account, set SAFESIGNAL_DATA_DIR to the database directory
and SAFESIGNAL_SESSION_SECRET to the matching session secret, then run:

    python scripts/provision_responder.py 0000000003@mail.jiit.ac.in --team "Cyber Response"
    python scripts/provision_responder.py 0000000004@mail.jiit.ac.in --team "Security Review"

This is a local operator command, not an HTTP endpoint. Never use fixture
credentials or the classroom process in hosted operation. Hosted upload
requires explicitly configured durable SQLite storage and
SECURESIGNAL_DURABLE_EVIDENCE=1; the service refuses uploads when ephemeral
storage is marked. Do not enable this on the existing free ephemeral host.

## Permission matrix

| Actor | Cases, room and evidence | Investigation | Alerts |
|---|---|---|---|
| Student | Own cases; room after server receipt | Read own progress/outcome | None |
| MFA-pending responder | None | None | None |
| MFA Cyber Response | Unassigned cases with server receipt and own assigned cases | First transition claims; only assignee can continue | None |
| MFA Security Review | None | None | Redacted alerts and reviews |
| Maintainer | Local database administration only | Assigns role/team from CLI | Maintains configuration |

Names and untrusted indicators render as escaped text; they are not fetched or
turned into links. Case routes, polling, the TLS room, uploads, downloads and
exports independently check case scope. Server receipt is confirmation of
storage, not of attention, response or investigation state.

## Evidence and recovery

Accepted originals are written as authenticated ciphertext BLOBs to private
SQLite, atomically with metadata and the upload audit. The multipart stream is
bounded and memory-only. PNG/JPEG are verified and decoded within a pixel
budget; EML validates bounded headers and remains inert. TXT/LOG/EML use UTF-8.
No file is rendered inline, executed, or sent to a third party. Upload defaults
are 5 MiB per file, 10 files per case, 50 MiB per uploading account, and 20
requests per account per minute per evidence action; evidence_limits in local
config overrides max_size, max_files and account_bytes. There is no malware
scanner. Filenames are labels only. SHA-256 plus authenticated decryption checks
consistency with the recorded original, not accuracy or legal admissibility.

Before migration or restore, stop the web process and worker. Take consistent
SQLite backups of server.sqlite and outbox.sqlite (SQLite backup API or CLI
.backup), protect them with OS access controls, and store separate protected
copies of both key sets and IDs. Restore both files into an isolated directory
and run PRAGMA integrity_check; verify sign-in, a stored evidence download
against its manifest, and a queued receipt with the worker. Do not restore over
a running process. SQLite ciphertext and metadata are included in server.sqlite.
Case text and audit metadata require access-controlled backups too. Losing
evidence keys means losing access to encrypted evidence. Roll back the code
with the previous checkout using a pre-change copy, not by dropping tables
from a live database; retain the migrated database to preserve new records.

Determine case, evidence, review and backup retention in the institution's
operator policy before real use. There is no automatic evidence/case deletion.
Detection signals purge after the longest configured rule window or 20,000
signals, but alert snapshots and review records persist. Schedule archival
after the chosen policy period, accounting for institutional holds, then apply
the same policy to snapshots and backups.

## Threat model and course mapping

- Confidentiality: session-bound ownership/team checks, separate reviewer
  privileges, verified TLS, and evidence AES-GCM under a protected key.
- Integrity: immutable UUID and payload checking, authenticated evidence
  metadata, original hashes, idempotent progress actions, and audit timestamps.
- Availability: persisted outbox, retry and restart reconciliation, bounded
  forms, evidence quotas, and time-window throttles. A single worker and host
  remain availability limits. This is not a production availability guarantee.
- Authentication: Argon2id password hashes, authenticator TOTP (one step of clock
  tolerance), atomic replay prevention, five-minute pending challenges and
  one-time recovery codes. Lost password plus lost factor needs operator recovery.
- Detection: login account (5 failures/60s), login source (4 distinct
  accounts/120s), case access (4/60s), unauthorized responder actions (4/60s)
  and evidence requests (15/60s). Default cooldown is 300s. Override
  security_rules in local config with [threshold,window_seconds,cooldown_seconds].
  Rule inputs use keyed pseudonyms. The app uses the socket peer address, not
  arbitrary forwarded addresses; on hosted proxies many clients can share this
  identity. This is application monitoring, not a network IDS.
- Out of scope: compromised endpoint, malicious operator with database and key
  access, network-wide intrusion visibility, malware detection, legal chain of
  custody certification and externally verified alert delivery.

## Repeatable demo (synthetic only)

1. Use a student profile to submit a phishing report with a text file and a
   fictitious indicator. Watch queued delivery turn into a server receipt.
2. Enroll the cyber responder in an authenticator, claim by triaging, record
   investigation notes, and send a private reply. Record containment and
   recovery or explain why either does not apply; then close with a summary.
3. In another isolated browser profile, the second student cannot open the
   first student's case or evidence. The authenticated journey test uses
   bounded synthetic denied events to demonstrate alert review.
4. Use the reviewer profile (also MFA) to open a redacted alert and acknowledge
   it. A reviewer cannot read the case body.
5. Run python -m pytest -q tests/test_cyber.py. The test changes a copy of a
   synthetic encrypted record in memory, verifies rejection, then checks that a
   metadata substitution also fails. It never modifies a real evidence object.

## Verification record

- Baseline: python -m pytest -q --tb=short — 73 passed before implementation.
- Focused: python -m pytest -q tests/test_cyber.py --tb=short — initial integration checkpoint, 6 passed.
- Integrated: python -m pytest -q --tb=short — 81 passed, including the later
  concurrency, quota, backup and CSRF checks. The separate compatibility
  test added after collection also passed:
  python -m pytest -q tests/test_cyber.py::test_cyber_migration_preserves_legacy_case_and_queued_payload --tb=short.
  Windows runs supplied a writable --basetemp directory.
- Python compilation, node --check safesignal/static/cyber.js, and git
  diff --check succeeded. The local browser smoke verified the homepage,
  student sign-in at 390 px and responder sign-in at 1280 px; authenticated
  paths at those widths were exercised by HTTP tests, not visually.
- Production was not touched. This is a local implementation and validation,
  not a public deployment or an independent production security review.

## Free hosted classroom release

Only use this mode after the operator verifies the addresses and approves the
release as a synthetic-data classroom demo. Render Free loses SQLite on
restart, including MFA enrollments. Registration stays disabled and evidence
uploads stay disabled. Local startup keys and accounts are never reused.

Run the following in your own terminal and enter unique passwords at the
hidden prompts (replace the example addresses with verified emails):

    python scripts/prepare_release_demo.py 0000000011@mail.jiit.ac.in 0000000012@mail.jiit.ac.in

Transfer the two environment settings from local/release-secrets.env to
Render Environment. Save without deploying until the new build is ready.
Never commit this file or share it in chat. The configuration recreates the
approved accounts after a clean start. Each address has separate Student, Cyber Response, and Security Review profiles.\nSelect the workspace at sign-in and enroll an authenticator separately for\neach privileged profile. Repeated startup
does not change existing account passwords or factor enrollment.
