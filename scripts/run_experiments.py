"""Seeded policies over real loopback TLS, isolated databases and app faults."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import threading
import time
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safesignal.faults import Faults
from safesignal.metrics import export
from safesignal.models import new_alert
from safesignal.server import AlertServer, request
from safesignal.server_store import Store
from safesignal.tls import client_context, server_context


def run(output, seed=7, count=6, window=2.0):
    if not 1 <= count <= 100 or not 1 <= window <= 30:
        raise ValueError('Count 1–100, observation seconds 1–30')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if any(output.glob('*.sqlite')):
        raise ValueError('Choose a fresh experiment directory to avoid mixing runs')
    rows = []
    for policy in ('single_attempt', 'retry_dedup'):
        rng = random.Random(seed)
        store = Store(output / (policy + '.sqlite'))
        faults = Faults(output / 'faults.json', True)
        server = AlertServer(('127.0.0.1', 0), server_context('certs'), store, 'synthetic-sender', 'synthetic-responder', faults)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for i in range(count):
                p = new_alert('LOW', f'TEST ONLY: seeded synthetic batch {i}')
                p['alert_id'] = str(UUID(int=rng.getrandbits(128), version=4))
                preset = ('disconnect', 'ack_lost', 'normal')[i % 3]
                faults.set('ack_lost' if preset == 'ack_lost' else 'normal')
                started = time.monotonic()
                attempts, confirmed = 0, None
                while True:
                    attempts += 1
                    try:
                        if preset == 'disconnect' and attempts == 1:
                            raise ConnectionError('First attempt simulated offline')
                        reply = request(server.server_address, client_context('certs'), 'synthetic-sender', 'SUBMIT_ALERT', p)
                        if reply['status'] != 'OK':
                            raise ValueError('Unexpected server rejection')
                        confirmed = time.monotonic() - started
                        break
                    except (OSError, EOFError):
                        delay = min(.25 * 2 ** min(attempts-1, 4), 2) * rng.uniform(.8, 1)
                        if policy == 'single_attempt' or time.monotonic() + delay - started >= window:
                            break
                        time.sleep(delay)
                state = store.status(p['alert_id'])
                receipt_seconds = (datetime.fromisoformat(state['server_received_at']) - datetime.fromisoformat(p['created_at'])).total_seconds() if state['status'] == 'OK' else None
                received = receipt_seconds is not None and receipt_seconds <= window
                if confirmed is not None and confirmed > window:
                    confirmed = None
                with store.connect() as db:
                    duplicates = db.execute("SELECT count(*) FROM submission_attempts WHERE alert_id=? AND result='DUPLICATE'", (p['alert_id'],)).fetchone()[0]
                rows.append(dict(policy=policy, index=i, alert_id=p['alert_id'], fault=preset,
                                 attempts=attempts, received=received, duplicates=duplicates,
                                 confirmation_seconds=confirmed,
                                 server_receipt_seconds=receipt_seconds))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()
    stamp = datetime.now(timezone.utc).isoformat()
    config = dict(run_id=output.name, seed=seed, count=count, observation_seconds=window,
                  date_utc=stamp, percentile='nearest rank', scenario='Repeated disconnect, lost first app receipt, normal; per-alert observation window')
    result = export(output, rows, config)
    output.parent.joinpath('latest.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=7)
    parser.add_argument('--count', type=int, default=6)
    parser.add_argument('--window', type=float, default=2)
    args = parser.parse_args()
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
    print(json.dumps(run(Path('artifacts') / run_id, args.seed, args.count, args.window), indent=2))
