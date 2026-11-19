import sqlite3

import pytest

from safesignal.database import connection


def test_commit_rollback_and_closed_handle(tmp_path):
    path=tmp_path/'database.sqlite'
    with connection(path) as db:
        db.execute('CREATE TABLE test(value TEXT)')
        db.execute("INSERT INTO test VALUES('committed')")
    with pytest.raises(sqlite3.ProgrammingError): db.execute('SELECT 1')
    with pytest.raises(RuntimeError):
        with connection(path) as failed:
            failed.execute("INSERT INTO test VALUES('rollback')")
            raise RuntimeError('synthetic failure')
    with pytest.raises(sqlite3.ProgrammingError): failed.execute('SELECT 1')
    with connection(path) as read:
        assert read.execute('SELECT count(*) FROM test').fetchone()[0]==1


def test_concurrent_reconciliation_is_one_queue_insert(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from safesignal.identity import Identity
    from safesignal.sender_store import Outbox
    from safesignal.models import new_alert
    auth=Identity(tmp_path/'server.sqlite','synthetic-key')
    payload=new_alert('HIGH','TEST ONLY: concurrent outbox reconciliation')
    auth.accept('synthetic-owner',payload)
    box=Outbox(tmp_path/'outbox.sqlite')
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:auth.reconcile(box),range(4)))
    assert len(box.rows())==1 and box.rows()[0]['alert_id']==payload['alert_id']
