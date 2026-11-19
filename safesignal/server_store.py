import hashlib
import json
import sqlite3

from .models import now, validate_alert, SEVERITIES, CATEGORIES, INCIDENT_STATES, RESPONSE_TEAMS


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
                CREATE TABLE IF NOT EXISTS walk_links(
                    walk_id TEXT NOT NULL,kind TEXT NOT NULL,alert_id TEXT UNIQUE NOT NULL,
                    disposition TEXT NOT NULL,PRIMARY KEY(walk_id,kind));
            ''')
            columns = {r[1] for r in db.execute('PRAGMA table_info(alerts)')}
            for name, definition in {
                'incident_state': "TEXT NOT NULL DEFAULT 'REPORTED'",
                'assigned_to': "TEXT NOT NULL DEFAULT ''", 'assigned_team': "TEXT NOT NULL DEFAULT ''",
                'last_note': "TEXT NOT NULL DEFAULT ''", 'resolved_at': 'TEXT', 'updated_at': 'TEXT',
                'owner_user_id': 'TEXT',
                'followup_disposition': "TEXT NOT NULL DEFAULT ''",
            }.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE alerts ADD COLUMN {name} {definition}')
            if 'detail' not in {r[1] for r in db.execute('PRAGMA table_info(audit)')}:
                db.execute("ALTER TABLE audit ADD COLUMN detail TEXT NOT NULL DEFAULT ''")
            db.execute("UPDATE alerts SET incident_state='ACKNOWLEDGED',assigned_to='Campus Response Desk',assigned_team='Campus Safety' WHERE responder_acknowledged_at IS NOT NULL AND incident_state='REPORTED'")
            db.execute('CREATE INDEX IF NOT EXISTS alerts_owner ON alerts(owner_user_id,server_received_at)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def submit(self, payload, owner=None):
        validate_alert(payload)
        canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        aid = payload['alert_id']
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT * FROM alerts WHERE alert_id=?', (aid,)).fetchone()
            result = 'NEW' if old is None else ('DUPLICATE' if old['payload_hash'] == digest and old['owner_user_id']==owner else 'ID_CONFLICT')
            stamp = now()
            if old is None:
                db.execute('INSERT INTO alerts(alert_id,payload,payload_hash,sender_id,status,server_received_at) VALUES (?,?,?,?,?,?)',
                           (aid, canonical, digest, 'synthetic-sender', 'SERVER_RECEIVED', stamp))
                db.execute('UPDATE alerts SET owner_user_id=? WHERE alert_id=?',(owner,aid))
                db.execute("UPDATE alerts SET followup_disposition=coalesce((SELECT disposition FROM walk_links WHERE alert_id=?),'') WHERE alert_id=?",(aid,aid))
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
                    responder_acknowledged_at=row['responder_acknowledged_at'],
                    **{k: row[k] for k in ('incident_state','assigned_to','assigned_team','last_note','resolved_at','updated_at','followup_disposition')})

    def scope(self, principal):
        if principal is None:
            return '1', ()
        if principal['role']=='student':
            return 'owner_user_id=?', (principal['id'],)
        return "((owner_user_id IS NOT NULL OR ?=1) AND (assigned_team='' OR assigned_team=?))", (principal.get('legacy',0),principal['team'])

    def authorized(self, principal, aid):
        scope,args=self.scope(principal)
        with self.connect() as db:
            return db.execute(f'SELECT 1 FROM alerts WHERE alert_id=? AND {scope}',(aid,*args)).fetchone() is not None

    def listing(self, offset=0, severity='', status='', newest=False, incident_state='', category='', search='', principal=None):
        if severity not in ('', *SEVERITIES) or status not in ('', 'SERVER_RECEIVED', 'RESPONDER_ACKNOWLEDGED'):
            raise ValueError('Invalid filter')
        if incident_state not in ('', *INCIDENT_STATES) or category not in ('', *CATEGORIES) or not isinstance(search,str) or len(search)>100:
            raise ValueError('Invalid incident filter')
        order = 'server_received_at DESC' if newest else "CASE json_extract(payload,'$.severity') WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END, server_received_at"
        scope,args=self.scope(principal)
        with self.connect() as db:
            ids = db.execute(f'''SELECT alert_id FROM alerts WHERE
                (?='' OR json_extract(payload,'$.severity')=?) AND (?='' OR status=?)
                AND (?='' OR incident_state=?)
                AND (?='' OR coalesce(json_extract(payload,'$.category'),'SAFETY')=?)
                AND instr(lower(json_extract(payload,'$.description') || ' ' || coalesce(json_extract(payload,'$.location'),'')),lower(?))>0
                AND {scope} AND followup_disposition!='WITHDRAWN' ORDER BY {order} LIMIT 4 OFFSET ?''', (severity, severity, status, status, incident_state, incident_state, category, category, search,*args,offset)).fetchall()
        return [self.status(row[0]) for row in ids]

    def acknowledge(self, aid, principal=None):
        return self.update_incident(aid, 'CLAIM', 'Campus Safety',principal=principal)

    def update_incident(self, aid, action, team='', note='', principal=None):
        if action not in ('CLAIM','START','RESOLVE','NOTE') or not isinstance(note,str) or len(note)>200:
            raise ValueError('Invalid incident action')
        note = note.strip()
        note.encode('utf-8')
        if any(ord(c)<32 and c not in '\n\r\t' for c in note):
            raise ValueError('Unsupported control character')
        if action == 'CLAIM' and team not in RESPONSE_TEAMS:
            raise ValueError('Choose an authorized response team')
        if action in ('RESOLVE','NOTE') and len(note)<5:
            raise ValueError('A note of 5–200 characters is required')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            scope,args=self.scope(principal)
            row = db.execute(f'SELECT * FROM alerts WHERE alert_id=? AND {scope}',(aid,*args)).fetchone()
            if row is None:
                return dict(status='ERROR',code='NOT_FOUND')
            state = row['incident_state']
            if action == 'CLAIM' and state != 'REPORTED':
                return self.status(aid)
            target = {'CLAIM':'ACKNOWLEDGED','START':'IN_PROGRESS','RESOLVE':'RESOLVED','NOTE':state}[action]
            allowed = {'CLAIM':('REPORTED',),'START':('ACKNOWLEDGED',),'RESOLVE':('IN_PROGRESS',),'NOTE':('ACKNOWLEDGED','IN_PROGRESS')}
            if state not in allowed[action]:
                return dict(status='ERROR',code='INVALID_TRANSITION')
            stamp = now()
            if action == 'CLAIM':
                db.execute("UPDATE alerts SET status='RESPONDER_ACKNOWLEDGED',responder_acknowledged_at=?,assigned_to='Campus Response Desk',assigned_team=? WHERE alert_id=?",(stamp,team,aid))
            db.execute('UPDATE alerts SET incident_state=?,updated_at=?,last_note=CASE WHEN ?<>\'\' THEN ? ELSE last_note END,resolved_at=CASE WHEN ?=\'RESOLVED\' THEN ? ELSE resolved_at END WHERE alert_id=?',
                       (target,stamp,note,note,target,stamp,aid))
            event = 'RESPONDER_ACKNOWLEDGED' if action == 'CLAIM' else ('NOTE_ADDED' if action == 'NOTE' else target)
            detail = note or (f'Assigned to {team}' if action == 'CLAIM' else 'Response work started')
            db.execute('INSERT INTO audit(alert_id,event,recorded_at,detail) VALUES (?,?,?,?)',(aid,event,stamp,detail))
        return self.status(aid)

    def audit(self, aid):
        with self.connect() as db:
            rows = db.execute('SELECT event,recorded_at,detail FROM audit WHERE alert_id=? ORDER BY id DESC LIMIT 8', (aid,)).fetchall()
            return [dict(r) for r in reversed(rows)]

    def dashboard(self, principal=None):
        from .dashboard import summarize
        scope,args=self.scope(principal)
        scope += " AND followup_disposition!='WITHDRAWN'"
        with self.connect() as db:
            rows = [dict(json.loads(r['payload']), **{k:r[k] for k in ('incident_state','assigned_team','responder_acknowledged_at','server_received_at')})
                    for r in db.execute(f'SELECT * FROM alerts WHERE {scope}',args)]
            activity = [dict(r) for r in db.execute(f'SELECT alert_id,event,recorded_at,detail FROM audit WHERE alert_id IN (SELECT alert_id FROM alerts WHERE {scope}) ORDER BY id DESC LIMIT 6',args)]
            duplicates = db.execute(f"SELECT count(*) FROM submission_attempts WHERE result='DUPLICATE' AND alert_id IN (SELECT alert_id FROM alerts WHERE {scope})",args).fetchone()[0]
        return dict(summarize(rows), activity=activity, duplicates=duplicates)
