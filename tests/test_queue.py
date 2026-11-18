import subprocess
import sys

from safesignal.models import new_alert
from safesignal.sender_store import Outbox
from safesignal.sender_worker import Worker, backoff
from test_transport import lab


def test_offline_restart_recovery_and_poll(lab, tmp_path):
    path = tmp_path / 'outbox.sqlite'
    box = Outbox(path)
    alert = new_alert('HIGH', 'TEST ONLY: outage and restart')
    box.enqueue(alert)
    def offline(*args):
        raise ConnectionError()
    Worker(box, offline).tick()
    assert box.rows()[0]['status'] == 'QUEUED'
    box.retry_now(alert['alert_id'])
    assert box.claim(alert['alert_id'])
    # A fresh process sees the committed in-flight record and recovers it.
    code = 'from safesignal.sender_store import Outbox; import sys; b=Outbox(sys.argv[1]); b.recover(); assert b.rows()[0]["status"] == "QUEUED"'
    subprocess.run([sys.executable, '-c', code, str(path)], check=True)
    restarted = Worker(Outbox(path), lab[2])
    restarted.tick()
    assert restarted.outbox.rows()[0]['status'] == 'SERVER_RECEIVED'
    lab[2]('ACK_ALERT', {'alert_id': alert['alert_id']}, 'test-responder')
    restarted.tick()
    assert restarted.outbox.rows()[0]['status'] == 'RESPONDER_ACKNOWLEDGED'
    assert restarted.outbox.rows()[0]['attempt_count'] == 3
    assert len(lab[1].listing()) == 1


def test_backoff_bounds():
    for attempt in (0, 1, 2, 20, 100000):
        assert 0.4 <= backoff(attempt) <= 30


def test_lost_application_receipt_after_commit(lab, tmp_path):
    server, store, call, _ = lab
    original = server.dispatch
    dropped = False
    def suppress_once(req):
        nonlocal dropped
        reply = original(req)
        if req['type'] == 'SUBMIT_ALERT' and not dropped:
            dropped = True
            assert len(store.listing()) == 1
            raise EOFError('Test-only suppressed application receipt after commit')
        return reply
    server.dispatch = suppress_once
    box = Outbox(tmp_path / 'outbox.sqlite')
    p = new_alert('HIGH', 'TEST ONLY: lost application receipt')
    box.enqueue(p)
    worker = Worker(box, call)
    worker.tick()
    assert box.rows()[0]['status'] == 'QUEUED'
    box.retry_now(p['alert_id'])
    worker.tick()
    assert box.rows()[0]['status'] == 'SERVER_RECEIVED'
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM alerts').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM submission_attempts WHERE result='DUPLICATE'").fetchone()[0] == 1


def test_no_terminal_regression(tmp_path):
    box = Outbox(tmp_path / 'box.sqlite')
    p = new_alert('LOW', 'TEST ONLY: terminal state')
    box.enqueue(p)
    reply = dict(code='RESPONDER_ACKNOWLEDGED', server_received_at=p['created_at'], responder_acknowledged_at=p['created_at'])
    box.confirmed(p['alert_id'], reply)
    box.confirmed(p['alert_id'], dict(reply, code='SERVER_RECEIVED'))
    assert box.rows()[0]['status'] == 'RESPONDER_ACKNOWLEDGED'


def test_abrupt_sender_process_exit_preserves_inflight(lab, tmp_path):
    path = tmp_path / 'crashed.sqlite'
    code = '''
import os, sys
from safesignal.sender_store import Outbox
from safesignal.models import new_alert
b = Outbox(sys.argv[1])
p = new_alert('HIGH', 'TEST ONLY: abrupt sender process exit')
b.enqueue(p)
assert b.claim(p['alert_id'])
os._exit(23)
'''
    crashed = subprocess.run([sys.executable, '-c', code, str(path)])
    assert crashed.returncode == 23
    box = Outbox(path)
    assert box.rows()[0]['status'] == 'SENDING'
    Worker(box, lab[2]).tick()
    assert box.rows()[0]['status'] == 'SERVER_RECEIVED'
