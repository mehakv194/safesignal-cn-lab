import hashlib
import json
import sqlite3

from .models import now, validate_alert


class Store:
    def __init__(self, path):
        self.path = str(path)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    payload_hash TEXT NOT NULL, sender_id TEXT NOT NULL,
                    status TEXT NOT NULL, server_received_at TEXT NOT NULL,
                    responder_acknowledged_at TEXT);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY, alert_id TEXT, event TEXT, recorded_at TEXT);
                CREATE TABLE IF NOT EXISTS submission_attempts (
                    id INTEGER PRIMARY KEY, alert_id TEXT, result TEXT, recorded_at TEXT);
            ''')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def submit(self, payload):
        validate_alert(payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        aid = payload['alert_id']
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM alerts WHERE alert_id=?', (aid,)).fetchone()
            result = 'NEW' if old is None else ('DUPLICATE' if old['payload_hash'] == digest else 'ID_CONFLICT')
            stamp = now()
            if old is None:
                db.execute('INSERT INTO alerts VALUES (?,?,?,?,?,?,NULL)',
                           (aid, canonical, digest, 'synthetic-sender', 'SERVER_RECEIVED', stamp))
                db.execute('INSERT INTO audit(alert_id,event,recorded_at) VALUES (?,?,?)',
                           (aid, 'SERVER_RECEIVED', stamp))
            db.execute('INSERT INTO submission_attempts(alert_id,result,recorded_at) VALUES (?,?,?)',
                       (aid, result, stamp))
        if result == 'ID_CONFLICT':
            return dict(status='ERROR', code=result)
        return dict(status='OK', code='SERVER_RECEIVED', alert_id=aid,
                    server_received_at=old['server_received_at'] if old else stamp,
                    duplicate=old is not None)

    def status(self, aid):
        with self.connect() as db:
            row = db.execute('SELECT * FROM alerts WHERE alert_id=?', (aid,)).fetchone()
        if not row:
            return dict(status='ERROR', code='NOT_FOUND')
        return dict(status='OK', code=row['status'], **json.loads(row['payload']),
                    server_received_at=row['server_received_at'],
                    responder_acknowledged_at=row['responder_acknowledged_at'])

    def listing(self):
        with self.connect() as db:
            ids = db.execute('SELECT alert_id FROM alerts ORDER BY server_received_at DESC LIMIT 100').fetchall()
        return [self.status(row[0]) for row in ids]

    def acknowledge(self, aid):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            updated = db.execute("UPDATE alerts SET status='RESPONDER_ACKNOWLEDGED', responder_acknowledged_at=? WHERE alert_id=? AND responder_acknowledged_at IS NULL", (now(), aid))
            if updated.rowcount:
                db.execute('INSERT INTO audit(alert_id,event,recorded_at) VALUES (?,?,?)',
                           (aid, 'RESPONDER_ACKNOWLEDGED', now()))
        return self.status(aid)

    def audit(self, aid):
        with self.connect() as db:
            return [dict(r) for r in db.execute('SELECT event,recorded_at FROM audit WHERE alert_id=? ORDER BY id', (aid,))]
