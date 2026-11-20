"""Versioned cyber records, separate from the immutable delivery envelope."""
import json
from datetime import datetime, timezone
from uuid import UUID

from .identity import canonical
from .models import new_alert
from .rooms import text

CATEGORIES = {
    'PHISHING': ('Phishing or suspicious email', {'sender': 'Claimed sender', 'indicator': 'Suspicious address or link (plain text)', 'excerpt': 'Message excerpt', 'clicked': 'Link clicked?', 'credentials': 'Credentials entered?', 'opened': 'File downloaded or opened?'}),
    'ACCOUNT': ('Compromised account', {'activity': 'Unexpected changes or activity', 'access': 'Still have access?', 'recovery': 'Recovery actions taken'}),
    'MALWARE': ('Suspected malware', {'symptoms': 'Symptoms or warning', 'opened': 'Suspect file opened?'}),
    'EXPOSURE': ('Data exposure', {'data_type': 'Type of data (no private values)', 'audience': 'Who may have seen it?'}),
    'ACCESS': ('Unauthorized access', {'activity': 'Unexpected access or activity', 'indicator': 'Relevant identifier (plain text)'}),
    'IMPERSONATION': ('Online impersonation or harassment', {'platform': 'Platform', 'activity': 'What happened?', 'indicator': 'Relevant identifier (plain text)'}),
}
CHOICES = {'ongoing', 'clicked', 'credentials', 'opened', 'access'}
STATES = ('REPORTED', 'TRIAGED', 'INVESTIGATING', 'CONTAINED', 'RECOVERED', 'CLOSED')
DISPOSITIONS = ('DUPLICATE', 'INVALID')
NOT_APPLICABLE = {'CONTAINMENT_NOT_APPLICABLE':'CONTAINED','RECOVERY_NOT_APPLICABLE':'RECOVERED'}


def valid_id(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def validate(form):
    errors, fields = {}, {}
    category = form.get('category', '')
    if category not in CATEGORIES:
        errors['category'] = 'Choose a cyber incident category.'
    for key, limit in {'title':120, 'description':3000, 'noticed':40, 'affected':160, 'ongoing':7,
                       **dict.fromkeys(CATEGORIES.get(category, ('', {}))[1], 400)}.items():
        value = form.get(f'{category}-{key}' if key in CATEGORIES.get(category, ('', {}))[1] else key, '').strip()
        try:
            if value or key in ('title', 'description'):
                text(value, limit)
            if key in CHOICES:
                value = value or 'unknown'
                if value not in ('yes','no','unknown'):
                    raise ValueError()
            if key == 'noticed':
                value = value or 'unknown'
                if value != 'unknown':
                    stamp = datetime.fromisoformat(value)
                    if stamp.utcoffset() is None:
                        raise ValueError()
                    value = stamp.astimezone(timezone.utc).isoformat()
        except (ValueError, OverflowError):
            errors[key] = ('Use an ISO timestamp with timezone, or leave blank for unknown.' if key == 'noticed'
                           else f'Enter a valid value (maximum {limit} characters).')
        fields[key] = value
    return dict(fields, category=category), errors


class Cases:
    def __init__(self, identity):
        self.identity = identity
        with identity.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS cyber_cases(
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, category TEXT NOT NULL, title TEXT NOT NULL,
                    data TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1, created REAL NOT NULL,
                    state TEXT NOT NULL DEFAULT 'REPORTED', assignee TEXT, outcome TEXT NOT NULL DEFAULT '');
                CREATE INDEX IF NOT EXISTS cyber_owner ON cyber_cases(owner,created);
                CREATE INDEX IF NOT EXISTS cyber_assignee ON cyber_cases(assignee,created);
                CREATE TABLE IF NOT EXISTS cyber_actions(
                    case_id TEXT NOT NULL, operation TEXT NOT NULL, actor TEXT NOT NULL,
                    state TEXT NOT NULL, reason TEXT NOT NULL, stamp REAL NOT NULL,
                    PRIMARY KEY(case_id,operation));
                INSERT OR IGNORE INTO schema_migrations VALUES(5);
            ''')

    def create(self, owner, case_id, fields):
        if not valid_id(case_id):
            raise ValueError('Invalid report reference.')
        envelope = new_alert('MEDIUM', 'SecureSignal cyber report (case details stored separately).')
        envelope['alert_id'] = case_id
        envelope.pop('category')  # Existing v1 transport envelope; cyber classification lives only in the case.
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT owner,data FROM cyber_cases WHERE id=?',(case_id,)).fetchone()
            data = canonical(fields)
            if old:
                if (old['owner'],old['data']) != (owner,data):
                    raise ValueError('This report reference has already been used.')
                return False
            db.execute('INSERT INTO cyber_cases(id,owner,category,title,data,created) VALUES(?,?,?,?,?,?)',
                       (case_id,owner,fields['category'],fields['title'],data,self.identity.clock()))
            db.execute('INSERT INTO submission_intents(alert_id,owner_id,payload) VALUES(?,?,?)',
                       (case_id,owner,canonical(envelope)))
        return True

    @staticmethod
    def scope(user):
        if user['role']=='student':
            return 'c.owner=?', (user['id'],)
        if user['role']=='responder' and user['team']=='Cyber Response':
            return ("a.alert_id IS NOT NULL AND (c.assignee=? OR c.assignee IS NULL)", (user['id'],))
        return '0', ()

    def list(self, user, offset, assigned=False):
        scope, params = self.scope(user)
        with self.identity.connect() as db:
            return db.execute(f'''SELECT c.id,c.category,c.title,c.state,a.server_received_at
                FROM cyber_cases c LEFT JOIN alerts a ON a.alert_id=c.id WHERE {scope}
                AND (?=0 OR c.assignee=?) ORDER BY c.created DESC,c.id LIMIT 21 OFFSET ?''',
                (*params,assigned,user['id'],offset)).fetchall()

    def get(self, db, user, aid):
        scope, params = self.scope(user)
        return db.execute(f'''SELECT c.*,a.server_received_at FROM cyber_cases c
            LEFT JOIN alerts a ON a.alert_id=c.id WHERE c.id=? AND {scope}''',(aid,*params)).fetchone()

    def read(self, user, aid):
        with self.identity.connect() as db:
            row = self.get(db,user,aid)
            if row is None:
                return None, []
            return dict(row, details=json.loads(row['data'])), db.execute(
                'SELECT * FROM cyber_actions WHERE case_id=? ORDER BY stamp,rowid LIMIT 50',(aid,)).fetchall()

    def advance(self, user, aid, operation, target, reason):
        if user['role']!='responder' or user['team']!='Cyber Response':
            raise PermissionError()
        if not valid_id(operation):
            raise ValueError('Invalid action reference.')
        reason = text(reason, 1000)
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self.get(db,user,aid)
            if not row:
                raise PermissionError()
            old = db.execute('SELECT * FROM cyber_actions WHERE case_id=? AND operation=?',(aid,operation)).fetchone()
            if old:
                if (old['actor'],old['state'],old['reason']) != (user['id'],target,reason):
                    raise ValueError('Action reference already used.')
                return
            state = row['state']
            allowed = next_states(state)
            if target not in allowed:
                raise ValueError('That action is unavailable in the current state.')
            outcome = reason if target in ('CLOSED', *DISPOSITIONS) else ''
            db.execute('UPDATE cyber_cases SET state=?,assignee=?,outcome=? WHERE id=?',
                       (NOT_APPLICABLE.get(target,target),user['id'],outcome,aid))
            db.execute('INSERT INTO cyber_actions VALUES(?,?,?,?,?,?)',
                       (aid,operation,user['id'],target,reason,self.identity.clock()))


def next_states(state):
    if state not in STATES[:-1]:
        return ()
    index = STATES.index(state)
    target = STATES[index+1]
    alternatives = DISPOSITIONS if index < 2 else tuple(k for k,v in NOT_APPLICABLE.items() if v==target)
    return (target,*alternatives)
