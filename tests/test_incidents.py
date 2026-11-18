import sqlite3
import hashlib
import json

import pytest

from safesignal.models import new_alert
from safesignal.sender_store import Outbox
from safesignal.sender_worker import Worker
from safesignal.server_store import Store
from test_transport import lab


def test_full_workflow_and_sender_sync(lab,tmp_path):
    box=Outbox(tmp_path/'outbox.sqlite')
    payload=new_alert('HIGH','TEST ONLY: simulated medical incident','Synthetic Sports Hall','MEDICAL')
    box.enqueue(payload)
    worker=Worker(box,lab[2]);worker.tick()
    aid=payload['alert_id']
    def update(action,**fields):
        return lab[2]('UPDATE_INCIDENT',dict(alert_id=aid,action=action,**fields),'test-responder')
    assert update('RESOLVE',note='Too early to resolve')['code']=='INVALID_TRANSITION'
    assert lab[2]('UPDATE_INCIDENT',dict(alert_id=aid,action='CLAIM',team='Medical Team'))['code']=='UNAUTHORIZED'
    assert update('CLAIM',team='Unknown team')['code']=='INVALID_REQUEST'
    assert update('CLAIM',team='Medical Team',note='Synthetic first-aid team assigned')['incident_state']=='ACKNOWLEDGED'
    worker.tick()
    assert box.rows()[0]['assigned_team']=='Medical Team'
    assert update('START',note='Practice response is underway')['incident_state']=='IN_PROGRESS'
    assert update('NOTE',note='<script>TEST ONLY note</script>')['status']=='OK'
    worker.tick()
    assert box.rows()[0]['incident_state']=='IN_PROGRESS'
    assert update('RESOLVE',note='x')['code']=='INVALID_REQUEST'
    assert update('RESOLVE',note='Practice completed; synthetic incident resolved')['incident_state']=='RESOLVED'
    worker.tick()
    row=box.rows()[0]
    assert row['incident_state']=='RESOLVED' and row['resolved_at']
    assert row['status']=='RESPONDER_ACKNOWLEDGED' and row['attempt_count']==1
    assert update('START')['code']=='INVALID_TRANSITION'
    assert lab[2]('ACK_ALERT',{'alert_id':aid},'test-responder')['incident_state']=='RESOLVED'
    assert lab[2]('GET_AUDIT',{'alert_id':aid})['events'][-1]['event']=='RESOLVED'
    summary=lab[2]('DASHBOARD',token='test-responder')
    assert summary['total']==1 and summary['resolved']==1 and summary['categories']['MEDICAL']==1


def test_dashboard_counts_before_pagination(lab):
    for i in range(6):
        lab[2]('SUBMIT_ALERT',new_alert('LOW',f'TEST ONLY: category incident {i}',category='INFRASTRUCTURE'))
    assert len(lab[2]('LIST_ALERTS',token='test-responder')['alerts'])==4
    assert lab[2]('DASHBOARD',token='test-responder')['total']==6
    assert len(lab[2]('LIST_ALERTS',{'search':'incident 4'},'test-responder')['alerts'])==1
    assert lab[2]('DASHBOARD')['code']=='UNAUTHORIZED'


def test_schema_upgrade_preserves_legacy_alert(tmp_path):
    path=tmp_path/'legacy.sqlite'
    p=new_alert('LOW','TEST ONLY: legacy immutable alert')
    del p['category']
    canonical=json.dumps(p,sort_keys=True,separators=(',',':'))
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE alerts(alert_id TEXT PRIMARY KEY,payload TEXT NOT NULL,payload_hash TEXT NOT NULL,sender_id TEXT NOT NULL,status TEXT NOT NULL,server_received_at TEXT NOT NULL,responder_acknowledged_at TEXT)')
        db.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,?)',(p['alert_id'],canonical,hashlib.sha256(canonical.encode()).hexdigest(),'synthetic-sender','RESPONDER_ACKNOWLEDGED',p['created_at'],p['created_at']))
    store=Store(path)
    assert store.submit(p)['duplicate'] is True
    Store(path)
    assert store.submit(p)['duplicate'] is True
    assert store.status(p['alert_id'])['incident_state']=='ACKNOWLEDGED'
    assert store.status(p['alert_id'])['description']==p['description']
    assert store.status(p['alert_id'])['server_received_at']==p['created_at']


def test_legacy_outbox_payload_survives_upgrade(lab,tmp_path):
    path=tmp_path/'outbox.sqlite'
    p=new_alert('LOW','TEST ONLY: legacy sender queue')
    del p['category']
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE outbox(alert_id TEXT PRIMARY KEY,payload TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'QUEUED',attempt_count INTEGER NOT NULL DEFAULT 0,next_attempt_at REAL NOT NULL DEFAULT 0,last_error TEXT,server_received_at TEXT,responder_acknowledged_at TEXT)''')
        db.execute("INSERT INTO outbox(alert_id,payload,status) VALUES (?,?,'SENDING')",(p['alert_id'],json.dumps(p)))
    box=Outbox(path)
    Worker(box,lab[2]).tick()
    assert box.rows()[0]['status']=='SERVER_RECEIVED'
    assert box.rows()[0]['alert']==p


def test_bounded_unicode_notes_and_audit(lab):
    payload=new_alert('HIGH','🚦'*300,'🚦'*120)
    lab[2]('SUBMIT_ALERT',payload)
    aid=payload['alert_id']
    lab[2]('UPDATE_INCIDENT',dict(alert_id=aid,action='CLAIM',team='Campus Safety'),'test-responder')
    for _ in range(10):
        assert lab[2]('UPDATE_INCIDENT',dict(alert_id=aid,action='NOTE',note='🚦'*200),'test-responder')['status']=='OK'
    assert len(lab[2]('GET_AUDIT',{'alert_id':aid})['events'])==8
    assert lab[2]('UPDATE_INCIDENT',dict(alert_id=aid,action='NOTE',note='\0'*20),'test-responder')['code']=='INVALID_REQUEST'
