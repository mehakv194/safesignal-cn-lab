# Implementation findings

## Inventory — 18 November 2026

Windows / PowerShell; Python 3.13.9. Existing Git repository on unborn `master`,
no code or commits. All five source Markdown files and original DOCX read.
Original synopsis retained under ignored `starter/` because it includes enrollment
numbers. No existing user code changed. pytest present; Flask/cryptography absent
initially. NS2, OpenSSL and Wireshark not on PATH. GitHub CLI installed but saved
authentication invalid: publication blocked until owner runs `gh auth login`.

User approved MIT licensing and publication after checks pass. No publication yet.
Virtual environment ensurepip failed on this Unicode workspace path; installing
through host pip's `--python .venv/Scripts/python.exe` works around bootstrap.

## Scope and decisions

Use standard library TLS/TCP + SQLite, Flask and plain templates. Shared modules
own validation/framing and store transactions; callers are socket handler, worker,
web adapters and integration tests. Never put tokens in browser source. Local
generated secrets/certificates/databases ignored. Only server owns authoritative
alert state. One synthetic sender principal; no multi-tenant claim. TLS selected
from synopsis alternatives; no custom cryptography. Timestamp freshness must not
reject legitimately queued alerts after an outage; validate UTC timestamps and
future skew, use stable UUID/payload hashes for replay safety.

## Ordered checklist

- Phase 0: source preservation, ignores, package, license, documentation.
- Phase 1: bounded protocol, certificate setup, authenticated persistence, TLS tests.
- Phase 2: durable outbox, recovery/backoff, dedup, separate responder ACK.
- Phase 3: authenticated local web interfaces, CSRF, real timeline.
- Phase 4: guarded faults and measured CSV/chart experiment.
- Phase 5: independent NS2/Wireshark instructions, no invented results.
- Phase 6: complete checks and demo documentation, publish only with working auth.
