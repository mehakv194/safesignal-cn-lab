# Actual experiment results

Run 20261118T140908885117 on 18 November 2026, Windows, Python 3.13.9,
single host, verified loopback TLS, temporary isolated SQLite databases.
Command: `.venv/Scripts/python scripts/run_experiments.py`.

Seed 7; 6 synthetic alerts per policy; 2-second per-alert observation window.
Schedule repeats: first attempt disconnected, first application receipt lost after
commit, normal. These are application faults, not physical packet loss.

| Observation | Single attempt | Retry + dedup |
|---|---:|---:|
| Unique alerts stored | 4/6 | 6/6 |
| Unique delivery ratio | 66.67% | 100% |
| Confirmed receipts | 2 | 6 |
| Pending confirmation | 4 | 0 |
| Submission retries | 0 | 4 |
| Duplicate suppressions | 0 | 2 |
| Median confirmation seconds | 0.0253 | 0.2577 |
| p95 confirmation seconds | 0.0326 | 0.2845 |

Confirmation sample sizes: 2 and 6; nearest-rank p95. Confirmation delays use
client monotonic clocks; server receipt delays in CSV use same-host UTC clocks.
Lost receipts can leave stored alerts unconfirmed. Retry confirmation latency is
larger here because it includes recovered attempts; do not infer slower transport
or universal improvement. Small deterministic sample, no statistical significance
claim. Observation window defines success; no delivery promise after a deadline.

Reviewed raw outputs: [CSV](results/results.csv), [config/metrics](results/summary.json),
[SVG chart](results/comparison.svg). Generated full runs under ignored `artifacts/`.

Integration suite at Phase 4: **14 passed in 11.96s**. Includes normal submit,
responder ACK/idempotency, unauthorized roles, broken/oversized frames, wrong TLS
certificate, persisted outbox/restart, lost application receipt/dedup/conflict,
web CSRF/XSS protections, guarded latency and actual experiment export.

NS2 and Wireshark: **NOT RUN**; executables unavailable on PATH. No trace,
packet-loss or NS2 throughput results are claimed. Independent instructions in
`ns2/README.md` and `docs/wireshark.md`.

Final QA: fresh virtual environment, **19 passed in 13.33s**. Includes actual
abrupt sender-process exit and recovery, maximum Unicode frame pagination,
validated filters, login throttle and non-destructive database archiving.
PNG chart export verified through browser: docs/results/comparison.png.

Public GitHub Actions run 44324181360 passed on both Ubuntu and Windows after
publication. See https://github.com/mehakv194/safesignal-cn-lab/actions/runs/44324181360 .
