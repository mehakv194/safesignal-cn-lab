"""Private incident messages and independent resolution-review records."""
from datetime import datetime, timezone

from .walks import uuid

AUTOMATED_REPLY = (
    'Your update was saved in this Incident Room. A demo responder can reply here. '
    'This automatic reply confirms storage only.'
)


def text(value, limit):
    if not isinstance(value,str) or not 1 <= len(value.strip()) <= limit or any(ord(c)<32 and c not in '\n\t\r' for c in value):
        raise ValueError('Invalid message length or characters')
    return value.strip()


class Rooms:
    def __init__(self,identity,store):
        self.identity,self.store=identity,store
        with identity.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS incident_messages(
                    id INTEGER PRIMARY KEY,incident_id TEXT NOT NULL,author_id TEXT NOT NULL,
                    author_role TEXT NOT NULL,client_uuid TEXT NOT NULL,body TEXT NOT NULL,
                    received REAL NOT NULL,UNIQUE(author_id,client_uuid));
                CREATE INDEX IF NOT EXISTS room_messages ON incident_messages(incident_id,id);
                CREATE TABLE IF NOT EXISTS incident_feedback(
                    id INTEGER PRIMARY KEY,incident_id TEXT NOT NULL,author_id TEXT NOT NULL,
                    client_uuid TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,
                    state TEXT NOT NULL,stamp REAL NOT NULL,UNIQUE(author_id,client_uuid));
                CREATE UNIQUE INDEX IF NOT EXISTS one_open_review ON incident_feedback(incident_id)
                    WHERE kind='REOPEN_REQUEST' AND state='OPEN';
                INSERT OR IGNORE INTO schema_migrations VALUES(3);
            ''')

    def access(self,db,user,aid):
        if self.identity.mfa:
            from .cyber_cases import Cases
            scope,args=Cases.scope(user)
            return db.execute(f'''SELECT c.*,a.incident_state FROM cyber_cases c JOIN alerts a
                ON a.alert_id=c.id WHERE c.id=? AND {scope}''',(aid,*args)).fetchone()
        scope,args=self.store.scope(user)
        row=db.execute(f'SELECT * FROM alerts WHERE alert_id=? AND {scope}',(aid,*args)).fetchone()
        if not row:
            db.execute('INSERT INTO security_events(event,result,stamp,actor_id,target_type,reason_code) VALUES(?,?,?,?,?,?)',
                       ('ROOM_DENIED','DENIED',self.identity.clock(),user['id'],'incident','OWNER_OR_TEAM'))
        return row

    def get(self,user,aid,before=0):
        if type(before)!=int or before<0:
            raise ValueError('Invalid page cursor')
        with self.identity.connect() as db:
            if not self.access(db,user,aid):
                return dict(status='ERROR',code='NOT_FOUND')
            rows=db.execute('''SELECT id,author_role,body,received FROM incident_messages
                WHERE incident_id=? AND (?=0 OR id<?) ORDER BY id DESC LIMIT 4''',(aid,before,before)).fetchall()
            feedback=[dict(r) for r in db.execute('SELECT id,kind,body,state,stamp FROM incident_feedback WHERE incident_id=? ORDER BY id DESC LIMIT 5',(aid,))]
            pending=db.execute("SELECT 1 FROM incident_feedback WHERE incident_id=? AND kind='REOPEN_REQUEST' AND state='OPEN'",(aid,)).fetchone() is not None
        return dict(status='OK',code='ROOM',messages=[dict(r) for r in reversed(rows)],
                    older=rows[-1]['id'] if len(rows)==4 else 0,feedback=feedback,review_pending=pending)

    def send(self,user,aid,key,body):
        uuid(key);body=text(body,300);stamp=self.identity.clock()
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not self.access(db,user,aid):
                return dict(status='ERROR',code='NOT_FOUND')
            old=db.execute('SELECT * FROM incident_messages WHERE author_id=? AND client_uuid=?',(user['id'],key)).fetchone()
            if old:
                if old['incident_id']!=aid or old['body']!=body:
                    return dict(status='ERROR',code='ID_CONFLICT')
                return dict(status='OK',code='SERVER_RECEIVED',message_id=old['id'],received=old['received'],duplicate=True)
            count=db.execute('SELECT count(*) FROM incident_messages WHERE author_id=? AND received>?',(user['id'],stamp-60)).fetchone()[0]
            total=db.execute("SELECT count(*) FROM incident_messages WHERE incident_id=? AND author_role!='system'",(aid,)).fetchone()[0]
            if count>=30 or total>=500:
                return dict(status='ERROR',code='RATE_LIMITED')
            cursor=db.execute('INSERT INTO incident_messages(incident_id,author_id,author_role,client_uuid,body,received) VALUES(?,?,?,?,?,?)',
                              (aid,user['id'],user['role'],key,body,stamp))
            mid=cursor.lastrowid
            if user['role'] == 'student' and not self.identity.mfa:
                db.execute(
                    '''INSERT INTO incident_messages
                       (incident_id,author_id,author_role,client_uuid,body,received)
                       VALUES(?,?,?,?,?,?)''',
                    (aid, 'safesignal-system', 'system', str(mid), AUTOMATED_REPLY, stamp),
                )
            db.execute('INSERT INTO audit(alert_id,event,recorded_at,detail) VALUES(?,?,?,?)',
                       (aid,'MESSAGE_STORED',datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'Private message stored; no read receipt inferred'))
        return dict(status='OK',code='SERVER_RECEIVED',message_id=mid,received=stamp,duplicate=False)

    def feedback(self,user,aid,key,kind,body):
        uuid(key);body=text(body,200)
        if kind not in ('CONFIRM','REOPEN_REQUEST','REVIEW'):
            raise ValueError('Invalid feedback')
        if (kind=='REVIEW') != (user['role']=='responder'):
            return dict(status='ERROR',code='UNAUTHORIZED')
        stamp=self.identity.clock()
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            case=self.access(db,user,aid)
            if not case:
                return dict(status='ERROR',code='NOT_FOUND')
            old=db.execute('SELECT * FROM incident_feedback WHERE author_id=? AND client_uuid=?',(user['id'],key)).fetchone()
            if old:
                return dict(status='OK',code='FEEDBACK_SAVED') if (old['incident_id'],old['kind'],old['body'])==(aid,kind,body) else dict(status='ERROR',code='ID_CONFLICT')
            if case['incident_state']!='RESOLVED':
                return dict(status='ERROR',code='INVALID_TRANSITION')
            count=db.execute('SELECT count(*) FROM incident_feedback WHERE author_id=? AND stamp>?',(user['id'],stamp-60)).fetchone()[0]
            if count>=10:
                return dict(status='ERROR',code='RATE_LIMITED')
            opened=db.execute("SELECT id FROM incident_feedback WHERE incident_id=? AND kind='REOPEN_REQUEST' AND state='OPEN'",(aid,)).fetchone()
            if kind=='REVIEW':
                if not opened:
                    return dict(status='ERROR',code='INVALID_TRANSITION')
                db.execute("UPDATE incident_feedback SET state='REVIEWED' WHERE id=?",(opened['id'],))
            elif opened:
                return dict(status='ERROR',code='REVIEW_PENDING')
            db.execute('INSERT INTO incident_feedback(incident_id,author_id,client_uuid,kind,body,state,stamp) VALUES(?,?,?,?,?,?,?)',
                       (aid,user['id'],key,kind,body,'OPEN' if kind=='REOPEN_REQUEST' else 'RECORDED',stamp))
            db.execute('UPDATE alerts SET review_pending=? WHERE alert_id=?',(int(kind=='REOPEN_REQUEST'),aid))
            db.execute('INSERT INTO audit(alert_id,event,recorded_at,detail) VALUES(?,?,?,?)',
                       (aid,kind,datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'Resolution feedback recorded; original lifecycle preserved'))
        return dict(status='OK',code='FEEDBACK_SAVED')
