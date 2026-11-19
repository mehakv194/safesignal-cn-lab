import json
import sqlite3
import time

from .models import now, validate_alert, INCIDENT_STATES


class Outbox:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS outbox (
                    alert_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'QUEUED',
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at REAL NOT NULL DEFAULT 0,
                    last_error TEXT, server_received_at TEXT,
                    responder_acknowledged_at TEXT);
                CREATE TABLE IF NOT EXISTS journey (
                    id INTEGER PRIMARY KEY, alert_id TEXT, event TEXT, recorded_at TEXT);
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(outbox)')}
            for name,definition in {
                'incident_state':"TEXT NOT NULL DEFAULT 'REPORTED'",'assigned_to':"TEXT NOT NULL DEFAULT ''",
                'assigned_team':"TEXT NOT NULL DEFAULT ''",'last_note':"TEXT NOT NULL DEFAULT ''",'resolved_at':'TEXT',
                'owner_user_id':'TEXT',
            }.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE outbox ADD COLUMN {name} {definition}')
            db.execute("UPDATE outbox SET incident_state='ACKNOWLEDGED' WHERE status='RESPONDER_ACKNOWLEDGED' AND incident_state='REPORTED'")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def enqueue(self, payload):
        validate_alert(payload)
        with self.connect() as db:
            db.execute('INSERT INTO outbox(alert_id,payload) VALUES (?,?)',
                       (payload['alert_id'], json.dumps(payload)))
            db.execute('INSERT INTO journey(alert_id,event,recorded_at) VALUES (?,?,?)',
                       (payload['alert_id'], 'QUEUED', now()))

    def recover(self):
        with self.connect() as db:
            db.execute("UPDATE outbox SET status='QUEUED', next_attempt_at=0 WHERE status='SENDING'")

    def enqueue_owned(self,payload,owner):
        validate_alert(payload)
        with self.connect() as db:
            old=db.execute('SELECT * FROM outbox WHERE alert_id=?',(payload['alert_id'],)).fetchone()
            if old:
                if old['owner_user_id']!=owner or json.loads(old['payload'])!=payload:
                    raise ValueError('Conflicting queue intent')
                return
            db.execute("INSERT INTO outbox(alert_id,payload,owner_user_id) VALUES(?,?,?)",(payload['alert_id'],json.dumps(payload),owner))
            db.execute('INSERT INTO journey(alert_id,event,recorded_at) VALUES(?,?,?)',(payload['alert_id'],'QUEUED',now()))

    def rows(self):
        with self.connect() as db:
            return [dict(r, alert=json.loads(r['payload'])) for r in db.execute('SELECT * FROM outbox ORDER BY rowid DESC')]

    def claim(self, aid):
        with self.connect() as db:
            updated = db.execute("UPDATE outbox SET status='SENDING', attempt_count=attempt_count+1 WHERE alert_id=? AND status='QUEUED' AND next_attempt_at<=?", (aid, time.time()))
            if updated.rowcount:
                db.execute('INSERT INTO journey(alert_id,event,recorded_at) VALUES (?,?,?)', (aid, 'SENDING', now()))
            return bool(updated.rowcount)

    def failed(self, aid, delay, code):
        with self.connect() as db:
            db.execute("UPDATE outbox SET status='QUEUED',next_attempt_at=?,last_error=? WHERE alert_id=? AND status='SENDING'",
                       (time.time() + delay, code, aid))

    def confirmed(self, aid, reply):
        state = 'RESPONDER_ACKNOWLEDGED' if reply['code'] == 'RESPONDER_ACKNOWLEDGED' else 'SERVER_RECEIVED'
        with self.connect() as db:
            row = db.execute('SELECT * FROM outbox WHERE alert_id=?', (aid,)).fetchone()
            if row is None:
                return
            if row['status']=='RESPONDER_ACKNOWLEDGED':
                state = row['status']
            progress = reply.get('incident_state','ACKNOWLEDGED' if state=='RESPONDER_ACKNOWLEDGED' else 'REPORTED')
            if progress not in INCIDENT_STATES or INCIDENT_STATES.index(progress)<INCIDENT_STATES.index(row['incident_state']):
                return
            db.execute('UPDATE outbox SET status=?,server_received_at=?,responder_acknowledged_at=?,last_error=NULL WHERE alert_id=?',
                       (state, reply['server_received_at'], reply.get('responder_acknowledged_at'), aid))
            db.execute('UPDATE outbox SET incident_state=?,assigned_to=?,assigned_team=?,last_note=?,resolved_at=? WHERE alert_id=?',
                       (progress,reply.get('assigned_to',row['assigned_to']),reply.get('assigned_team',row['assigned_team']),reply.get('last_note',row['last_note']),reply.get('resolved_at',row['resolved_at']),aid))
            if row['status'] != state:
                db.execute('INSERT INTO journey(alert_id,event,recorded_at) VALUES (?,?,?)', (aid, state, now()))
                if reply.get('duplicate'):
                    db.execute('INSERT INTO journey(alert_id,event,recorded_at) VALUES (?,?,?)', (aid, 'DUPLICATE_SUPPRESSED', now()))
            if row['incident_state'] != progress and progress in ('IN_PROGRESS','RESOLVED'):
                db.execute('INSERT INTO journey(alert_id,event,recorded_at) VALUES (?,?,?)',(aid,progress,now()))

    def retry_now(self, aid):
        with self.connect() as db:
            db.execute("UPDATE outbox SET next_attempt_at=0 WHERE alert_id=? AND status='QUEUED'", (aid,))

    def timeline(self, aid):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT event,recorded_at FROM journey WHERE alert_id=? ORDER BY id', (aid,))]
