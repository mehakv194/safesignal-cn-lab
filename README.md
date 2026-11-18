# SafeSignal

SIMULATION — NOT FOR REAL EMERGENCIES

Local educational TLS/TCP alert delivery with a durable sender queue and separate
responder acknowledgment. This does not dispatch assistance or guarantee delivery.

Python 3.11+ required. Setup in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts/init_demo.py
.\.venv\Scripts\python scripts/run_demo.py
```

macOS/Linux: use `.venv/bin/python` in place of `.\.venv\Scripts\python`.
Sender: http://127.0.0.1:5001; responder: http://127.0.0.1:5002.
Generated local credentials are stored in ignored `local/config.json`.
Run tests with `python -m pytest -q` using the virtual environment.

Browser HTTP is loopback-only; socket transport verifies TLS. Public/LAN
deployment is unsupported. Server sees plaintext after TLS termination and SQLite
is not encrypted at rest. Use synthetic data only. See `docs/findings.md` for
verified progress and limitations; setup commands apply as phases are implemented.
