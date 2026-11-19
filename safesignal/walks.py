"""Server-authoritative synthetic walks; scheduling never depends on an open tab."""
import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from .models import new_alert
from .identity import canonical


def uuid(value):
    if str(UUID(value)) != value:
        raise ValueError('Canonical action UUID required')
    return value


def label(value):
    if not isinstance(value,str) or not 1 <= len(value.strip()) <= 80 or any(ord(c)<32 for c in value):
        raise ValueError('Use a place label of 1–80 characters')
    return value.strip()


class Walks:
    GRACE=120

    def __init__(self, identity, store):
        self.identity,self.store,self.clock=identity,store,identity.clock
        with identity.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS walks(
                    id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,from_label TEXT NOT NULL,to_label TEXT NOT NULL,
                    started REAL NOT NULL,expected_end REAL NOT NULL,interval_s INTEGER NOT NULL,
                    status TEXT NOT NULL,ended REAL,request TEXT NOT NULL);
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_walk ON walks(owner_id)
                    WHERE status IN ('ACTIVE','NEEDS_FOLLOW_UP');
                CREATE TABLE IF NOT EXISTS walk_slots(
                    walk_id TEXT NOT NULL,due REAL NOT NULL,status TEXT NOT NULL,response_at REAL,
                    PRIMARY KEY(walk_id,due));
                CREATE TABLE IF NOT EXISTS walk_actions(
                    owner_id TEXT NOT NULL,action_id TEXT NOT NULL,walk_id TEXT NOT NULL,action TEXT NOT NULL,
                    PRIMARY KEY(owner_id,action_id));
                CREATE TABLE IF NOT EXISTS walk_events(
                    id INTEGER PRIMARY KEY,walk_id TEXT NOT NULL,event TEXT NOT NULL,stamp REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS walk_due ON walk_slots(status,due);
                INSERT OR IGNORE INTO schema_migrations VALUES(2);
            ''')

    def start(self, user, fields):
        wid=uuid(fields['action_id'])
        origin,destination=label(fields['origin']),label(fields['destination'])
        duration,interval=fields['duration'],fields['interval']
        if type(duration)!=int or type(interval)!=int or duration not in (5,10,15,30,60) or interval not in (5,10,15) or interval>duration:
            raise ValueError('Choose supported duration and interval')
        requested=canonical(dict(origin=origin,destination=destination,duration=duration,interval=interval))
        stamp=self.clock()
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT * FROM walks WHERE id=?',(wid,)).fetchone()
            if old:
                if old['owner_id']!=user['id'] or old['request']!=requested:
                    raise ValueError('Conflicting walk identifier')
            else:
                if db.execute("SELECT 1 FROM walks WHERE owner_id=? AND status IN ('ACTIVE','NEEDS_FOLLOW_UP')",(user['id'],)).fetchone():
                    raise ValueError('End your current walk before starting another')
                db.execute('INSERT INTO walks VALUES(?,?,?,?,?,?,?,?,?,?)',
                           (wid,user['id'],origin,destination,stamp,stamp+duration*60,interval*60,'ACTIVE',None,requested))
                db.executemany('INSERT INTO walk_slots(walk_id,due,status) VALUES(?,?,?)',
                               [(wid,stamp+seconds,'SCHEDULED') for seconds in range(interval*60,duration*60+1,interval*60)])
                db.execute('INSERT INTO walk_events(walk_id,event,stamp) VALUES(?,?,?)',(wid,'STARTED',stamp))
        return self.get(user,wid)

    def get(self,user,wid):
        with self.identity.connect() as db:
            row=db.execute('SELECT * FROM walks WHERE id=? AND owner_id=?',(wid,user['id'])).fetchone()
            if not row:
                return dict(status='ERROR',code='NOT_FOUND')
            slots=[dict(r) for r in db.execute('SELECT due,status,response_at FROM walk_slots WHERE walk_id=? ORDER BY due',(wid,))]
            links=[dict(r) for r in db.execute('SELECT kind,alert_id,disposition FROM walk_links WHERE walk_id=?',(wid,))]
            events=[dict(r) for r in db.execute('SELECT event,stamp FROM walk_events WHERE walk_id=? ORDER BY id DESC LIMIT 10',(wid,))]
        result={k:row[k] for k in ('id','from_label','to_label','started','expected_end','status','ended')}
        result['walk_state']=result.pop('status')
        result.update(status='OK',code='WALK_SAVED',slots=slots,links=links,events=list(reversed(events)),server_time=self.clock(),grace_s=self.GRACE)
        return result

    def listing(self,user):
        with self.identity.connect() as db:
            rows=db.execute('SELECT id,from_label,to_label,status,started FROM walks WHERE owner_id=? ORDER BY started DESC LIMIT 5',(user['id'],)).fetchall()
        return dict(status='OK',code='WALKS',walks=[dict(r) for r in rows])

    def link(self,db,walk,kind):
        old=db.execute('SELECT alert_id,disposition FROM walk_links WHERE walk_id=? AND kind=?',(walk['id'],kind)).fetchone()
        if old:
            if kind=='FOLLOW_UP' and old['disposition']=='WITHDRAWN':
                db.execute("UPDATE walk_links SET disposition='REVIEW_REQUIRED' WHERE walk_id=? AND kind=?",(walk['id'],kind))
                db.execute("UPDATE alerts SET followup_disposition='REVIEW_REQUIRED' WHERE alert_id=?",(old['alert_id'],))
            return old['alert_id']
        aid=str(uuid4())
        text='TEST ONLY: simulated help requested during SafeWalk' if kind=='HELP' else 'TEST ONLY: missed SafeWalk check-in; status unknown, needs follow-up'
        payload=new_alert('HIGH',text,walk['to_label'],'SAFETY')
        payload['alert_id']=aid
        payload['created_at']=datetime.fromtimestamp(self.clock(),timezone.utc).isoformat()
        db.execute('INSERT INTO submission_intents(alert_id,owner_id,payload) VALUES(?,?,?)',(aid,walk['owner_id'],canonical(payload)))
        db.execute('INSERT INTO walk_links VALUES(?,?,?,?)',(walk['id'],kind,aid,'OPEN'))
        return aid

    def action(self,user,wid,action,action_id):
        uuid(action_id)
        if action not in ('SAFE','HELP','ARRIVE','END'):
            raise ValueError('Invalid walk action')
        stamp=self.clock()
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            walk=db.execute('SELECT * FROM walks WHERE id=? AND owner_id=?',(wid,user['id'])).fetchone()
            if not walk:
                return dict(status='ERROR',code='NOT_FOUND')
            prior=db.execute('SELECT * FROM walk_actions WHERE owner_id=? AND action_id=?',(user['id'],action_id)).fetchone()
            if prior:
                if prior['walk_id']!=wid or prior['action']!=action:
                    raise ValueError('Conflicting action identifier')
            else:
                if walk['status'] not in ('ACTIVE','NEEDS_FOLLOW_UP'):
                    raise ValueError('This walk has ended')
                db.execute('INSERT INTO walk_actions VALUES(?,?,?,?)',(user['id'],action_id,wid,action))
                if action in ('ARRIVE','END'):
                    db.execute('UPDATE walks SET status=?,ended=? WHERE id=?',('COMPLETED' if action=='ARRIVE' else 'CANCELLED',stamp,wid))
                    db.execute("UPDATE walk_slots SET status='CANCELLED' WHERE walk_id=? AND status IN ('SCHEDULED','DUE')",(wid,))
                else:
                    slot=db.execute("SELECT * FROM walk_slots WHERE walk_id=? AND status IN ('DUE','MISSED') ORDER BY due LIMIT 1",(wid,)).fetchone()
                    if not slot:
                        slot=db.execute("SELECT * FROM walk_slots WHERE walk_id=? AND status='SCHEDULED' ORDER BY due LIMIT 1",(wid,)).fetchone()
                    if slot:
                        db.execute('UPDATE walk_slots SET status=?,response_at=? WHERE walk_id=? AND due=?',
                                   ('CONFIRMED_SAFE' if action=='SAFE' else 'HELP_REQUESTED',stamp,wid,slot['due']))
                    if action=='HELP':
                        self.link(db,walk,'HELP')
                    else:
                        link=db.execute("SELECT * FROM walk_links WHERE walk_id=? AND kind='FOLLOW_UP'",(wid,)).fetchone()
                        if link:
                            incident=db.execute('SELECT incident_state FROM alerts WHERE alert_id=?',(link['alert_id'],)).fetchone()
                            disposition='WITHDRAWN' if not incident or incident['incident_state']=='REPORTED' else 'REVIEW_REQUIRED'
                            db.execute("UPDATE walk_links SET disposition=? WHERE walk_id=? AND kind='FOLLOW_UP'",(disposition,wid))
                            db.execute('UPDATE alerts SET followup_disposition=? WHERE alert_id=?',(disposition,link['alert_id']))
                            if incident:
                                db.execute('INSERT INTO audit(alert_id,event,recorded_at,detail) VALUES(?,?,?,?)',
                                           (link['alert_id'],'LATE_SAFE_CHECKIN',datetime.fromtimestamp(stamp,timezone.utc).isoformat(),'Self-reported safe; follow-up '+disposition.lower()))
                        db.execute("UPDATE walks SET status='ACTIVE' WHERE id=?",(wid,))
                db.execute('INSERT INTO walk_events(walk_id,event,stamp) VALUES(?,?,?)',(wid,action,stamp))
        return self.get(user,wid)

    def reconcile(self):
        stamp=self.clock()
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            rows=db.execute("SELECT * FROM walks WHERE status IN ('ACTIVE','NEEDS_FOLLOW_UP')").fetchall()
            for walk in rows:
                db.execute("UPDATE walk_slots SET status='DUE' WHERE walk_id=? AND status='SCHEDULED' AND due<=?",(walk['id'],stamp))
                missed=db.execute("UPDATE walk_slots SET status='MISSED' WHERE walk_id=? AND status='DUE' AND due+?<=?",(walk['id'],self.GRACE,stamp)).rowcount
                if missed:
                    self.link(db,walk,'FOLLOW_UP')
                    db.execute("UPDATE walks SET status='NEEDS_FOLLOW_UP' WHERE id=?",(walk['id'],))
                    db.execute('INSERT INTO walk_events(walk_id,event,stamp) VALUES(?,?,?)',(walk['id'],'MISSED_STATUS_UNKNOWN',stamp))
