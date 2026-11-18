# SafeSignal — Phase-by-Phase Codex Build Plan and Git Workflow

## Mission, prioritization, and stop condition
Build a *complete demonstrable course project*, not a feature-rich startup. Repository must remain publicly readable, with synthetic test data and no live secrets. One functional feature per small, real commit; no fake or backdated history. Each phase ends with code running, tests passing and a short update to `docs/findings.md`. Do not proceed if previous-phase acceptance tests fail.

### How to use this plan
The human supplies these five Markdown files plus approved synopsis to Codex, and pastes the instructions from `05_CODEX_MASTER_PROMPT.md`. Codex should inspect the working directory and `git status`, build and test incrementally. Codex may create the GitHub repository using `gh` if authenticated; otherwise initialize locally and provide the exact `gh repo create ... --public` command to run after login. Never claim external publication happened unless GitHub remote confirms it.

## Phase 0 — Repository hygiene and skeleton

**Goal:** public-repo-ready, no logic yet.

1. Check existing files; do not delete user work. Choose public repo `safesignal-cn-lab` unless name taken.
2. `git init -b main` if not already a Git repo. Create `.gitignore` excluding `.env`, `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.sqlite`, `*.sqlite3`, `*.db`, `certs/*.key`, `certs/*.pem`, private tokens, Wireshark captures with sensitive traffic, generated artifacts/temp files. Dev public cert may also be generated locally rather than committed.
3. Add MIT license only if team approves; otherwise choose license explicitly with humans; do not assume copyright assignment. Add README with educational disclaimer, feature checklist, setup placeholders and architecture diagram. Add five docs under `docs/` and source attribution for synopsis.
4. Create minimal package scaffolding and requirements, test workflow. Use deterministic formatting; no excessive dependencies.
5. Create GitHub repo via `gh auth status` and `gh repo create safesignal-cn-lab --public --source=. --remote=origin --push` **only if authenticated and team explicitly authorized publishing the current content**. Public content must be reviewed for private data first.

**Acceptance:** `git status` clean after commit, `README` readable, no secrets, valid `python -m ...` package smoke test. Suggested commit `chore: initialize public SafeSignal lab repository`.

## Phase 1 — Transport and security core

1. Define models and JSON framing (4-byte length; max 16 KiB; exact read; length validation).
2. Create development TLS certificate with SAN localhost; strict client verification.
3. Start TLS TCP server accepting `HEALTH` and `SUBMIT_ALERT`; separate sender/responder scoped tokens.
4. Initialize server SQLite, parse/validate and store one synthetic alert, respond only after commit.
5. Unit/integration tests for successful request, malformed request, bad token, bad cert and frame limits.

**Acceptance:** one command starts server, one script sends alert, SQLite persists it; invalid cert/token rejected. Do not count a successful `sendall()` as durable receipt. Suggested commits: `feat(protocol): add framed TLS socket messages`; `feat(server): persist authenticated alerts`; `test(transport): cover malformed and unauthorized requests`.

## Phase 2 — Sender outbox, retries and dedup

1. Persist UUID/alert locally before any send; bounded queue worker starts independently of browser session.
2. Transitions QUEUED/SENDING/SERVER_RECEIVED and retry with capped exponential backoff plus jitter; per-alert attempt counter and last_error.
3. Recover in-flight sends after sender process restart; cap retry rate; keep retry until acknowledged by server or explicit human cancellation (for demo test runs, use finite observation window without losing queue data).
4. Use server unique alert ID and payload hash to return DUPLICATE for same payload, conflict for mutation.
5. Sender polls `GET_STATUS`; server responder `ACK_ALERT` changes authoritative state.
6. Tests for crash/restart, duplicate suppression and already-acknowledged terminal status.

**Acceptance:** disconnect sender, submit test alert, restart sender, reconnect; server gets exactly one row even if ACK lost and retry occurs. Suggested commits: `feat(sender): persist and recover alert outbox`; `feat(reliability): add backoff and idempotent deduplication`; `feat(status): separate receipt and responder acknowledgment`.

## Phase 3 — Functional UI (do not polish prematurely)

1. Minimal Flask sender form/outbox/status view, local-only port 5001.
2. Minimal Flask responder listing/acknowledgment view, local-only port 5002, separate authenticated session.
3. Add alert timeline and severity ordering. Display proper statuses, real timestamps only.
4. Prevent XSS, CSRF and unauthorized responder actions; no tokens in the webpage.
5. Small CSS design pass for legibility/responsive behavior.

**Acceptance:** two distinct browser tabs demonstrate send -> server received -> responder acknowledged; reload does not erase state. Suggested commits: `feat(ui): add sender portal and status timeline`; `feat(responder): add authenticated acknowledgment console`; `style(ui): improve responsive lab dashboard`.

## Phase 4 — Network Chaos Lab / differentiators

1. Add *clearly labeled* app-layer fault presets (normal, delay, first response suppression, sender disconnect); local-only and disabled by default except demo setting.
2. Fault injection must occur **after successful server commit** for lost-ACK demonstration.
3. Surface counters for unique alerts, attempted sends, duplicate suppressions and pending items; telemetry from real logs/data.
4. Add deterministic synthetic batch runner with fixed seed and two policies (`single attempt`, `retry + dedup`). Use controlled identical fault sequences where feasible; disclose that differences depend on scenario and observation window.
5. Persist run IDs/config/results; export CSV and render at least one simple chart (matplotlib or browser chart). Never hardcode flattering percentages.

**Acceptance:** test fault scenarios all pass; baseline vs reliable comparison is reproducible and stored with seed/config; reports say N/A when data unavailable. Suggested commits: `feat(simulation): add labeled app-layer network faults`; `feat(evidence): implement repeatable comparison and metrics export`.

## Phase 5 — Networking-lab evidence

1. Add NS2 TCL wired example (minimum 3-4 nodes, TCP/FTP flow and optionally UDP/CBR comparison) with parameterized baseline and impaired queue/link settings. Configure meaningful `.tr` trace output; optionally `.nam` when available.
2. Provide two reproducible scenarios: baseline and impaired (clearly chosen queue limit/delay/loss characteristics). Distinguish NS2 channel/queue configuration and losses from application-layer faults.
3. Provide AWK parser or Python parser for NS2 trace (document exact trace format). Report throughput, loss from generated trace, and end-to-end delay only when identifiable; do not fabricate trace metrics. Add plots if NS2 is installed.
4. Document how to capture/inspect TLS traffic with Wireshark and what encrypted packets actually prove. Do not auto-capture unrelated system traffic.
5. Add screenshots of running application *only after running*, anonymized, with concise caption. Add generated actual metrics to `docs/experiment-results.md` with machine/OS/config/date, or mark NOT RUN.

**Acceptance:** run scripts work on available environment; when NS2 not installed, no invented results and honest command-based installation guidance. Suggested commits: `test(ns2): add baseline and impaired topology scripts`; `docs(evidence): document captures and measured results`.

## Phase 6 — Polish, QA, release

1. Run complete test suite, secure defaults check, screenshot against 1366x768, clean demo reset, reproduce full demo from README.
2. Validate GitHub README commands on fresh virtual environment and Windows/macOS/Linux where possible; mark unsupported environment rather than pretending tests passed.
3. Add architecture/state machine diagrams (Mermaid supported in GitHub Markdown), limitations, team roles and demonstrable screenshots/results.
4. Generate 6-slide teacher presentation outline in `docs/demo-script.md`, including short viva answers, and final truthful status in `docs/findings.md`.
5. `git status --short`, `git log --oneline --graph --decorate -15`, `git remote -v`; push actual commits and optional `v1.0-lab-demo` annotated tag only after complete verified run.

**Acceptance:** fresh setup -> send normal -> disconnect/recover -> lost app ACK/one server row -> responder acknowledgment -> real export -> documented NS2 results or explicit limitation.

## Git workflow and commit policy

- `main` always runnable. Do each phase on a named branch, e.g. `feature/transport`, `feature/reliability`, `feature/ui`, `feature/chaos-lab`, `feature/ns2-evidence`, `docs/release`.
- Make authentic small commits only after related files exist and tests pass. Do not fabricate commits, history, authors, dates, reviews or PR approvals. Do not create meaningless tiny commits merely to inflate count.
- If GitHub authentication allows, push branch; make PR with `gh pr create --base main ...`, merge after successful tests/review as suitable. If single developer/time-constrained, use `git switch main && git merge --no-ff <branch>` and push; README/PR comments should not claim independent review occurred.
- Never rewrite team history or force-push shared main. Always `git status` before checkout/merge; preserve uncommitted work.
- On each commit: run relevant tests; stage explicit paths (`git add path1 path2`) and then `git commit -m '...'`; log resulting real commit hash in `docs/findings.md` at natural checkpoints, not retroactively imagined.
- `gh` and cloud publication may require interactive authentication or explicit consent; if blocked, leave functioning local Git and supply exact next steps.

## Minimal demo readiness checklist

- [ ] Sender creates synthetic SOS and persists local UUID
- [ ] TLS certificate verified by client
- [ ] Server returns receipt after DB commit
- [ ] Authorized responder can acknowledge separately
- [ ] Disconnect/recovery works after restart
- [ ] Lost application ACK causes retry but does not duplicate server alert
- [ ] Evidence values obtained from real test run
- [ ] NS2 trace test run or explicitly marked unavailable
- [ ] README runs on clean checkout
- [ ] Public repo contains no secrets or real emergency data
- [ ] Git commits are authentic, comprehensible and pushed when authorized

## If time runs short

Prioritize: Phase 1 + Phase 2 + minimal Phase 3 + one Phase 4 fault scenario + tests + honest README. Then add NS2 as separate short scripts. Sacrifice decoration and advanced charts before reliability and authenticity. Never use a fake UI backed by static data as a substitute for working TCP/TLS transmission.
