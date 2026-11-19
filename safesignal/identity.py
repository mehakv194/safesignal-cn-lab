"""Individual accounts and durable submission ownership; no browser role assertions."""
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from .models import validate_alert, RESPONSE_TEAMS


def email_address(value):
    parts = value.strip().split('@')
    value = '@'.join((parts[0], parts[1].lower())) if len(parts) == 2 else ''
    if not re.fullmatch(r'[0-9]{10}@mail\.jiit\.ac\.in', value):
        raise ValueError('Use ten enrollment digits followed by @mail.jiit.ac.in.')
    return value


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class Identity:
    def __init__(self, path, secret, clock=time.time, mail=None):
        self.path, self.clock, self.mail = str(path), clock, mail
        self.key = hmac.digest(secret.encode(), b'safesignal-principal-v2', 'sha256')
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
        self.dummy = self.hasher.hash(secrets.token_urlsafe(24))
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'student',verified INTEGER NOT NULL DEFAULT 0,
                    disabled INTEGER NOT NULL DEFAULT 0,team TEXT NOT NULL DEFAULT '',created REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS challenges(
                    hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,purpose TEXT NOT NULL,
                    expires REAL NOT NULL,used REAL);
                CREATE TABLE IF NOT EXISTS sessions(
                    hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,created REAL NOT NULL,
                    last_seen REAL NOT NULL,expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_limits(
                    key TEXT NOT NULL,stamp REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS auth_limit_key ON auth_limits(key,stamp);
                CREATE TABLE IF NOT EXISTS security_events(
                    id INTEGER PRIMARY KEY,event TEXT NOT NULL,result TEXT NOT NULL,stamp REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS submission_intents(
                    alert_id TEXT PRIMARY KEY,owner_id TEXT NOT NULL,payload TEXT NOT NULL,
                    enqueued INTEGER NOT NULL DEFAULT 0);
                INSERT OR IGNORE INTO schema_migrations VALUES(1);
            ''')
            if 'legacy' not in {r[1] for r in db.execute('PRAGMA table_info(users)')}:
                db.execute('ALTER TABLE users ADD COLUMN legacy INTEGER NOT NULL DEFAULT 0')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def limit(self, action, account, ip):
        stamp = self.clock()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_limits WHERE stamp<?', (stamp-900,))
            keys = (digest(action+':account:'+account), digest(action+':ip:'+ip))
            if any(db.execute('SELECT count(*) FROM auth_limits WHERE key=?', (key,)).fetchone()[0] >= maximum
                   for key, maximum in zip(keys, (8, 40))):
                db.execute('INSERT INTO security_events(event,result,stamp) VALUES(?,?,?)',
                           ('AUTH_THROTTLED', 'DENIED', stamp))
                return False
            db.executemany('INSERT INTO auth_limits VALUES(?,?)', [(key, stamp) for key in keys])
        return True

    @staticmethod
    def password(value):
        if not 12 <= len(value) <= 128:
            raise ValueError('Use a password of 12–128 characters.')

    def register(self, email, password):
        email = email_address(email)
        self.password(password)
        if self.mail is None:
            raise ValueError('Registration unavailable: email delivery is not configured.')
        hashed = self.hasher.hash(password)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO users(id,email,password_hash,created) VALUES(?,?,?,?)',
                       (str(uuid4()), email, hashed, self.clock()))
        self.challenge(email, 'VERIFY')

    def challenge(self, email, purpose):
        email = email_address(email)
        with self.connect() as db:
            user = db.execute('SELECT * FROM users WHERE email=? AND disabled=0', (email,)).fetchone()
            if not user or self.mail is None or (purpose == 'RESET' and not user['verified']):
                return
            if purpose == 'VERIFY' and user['verified']:
                return
            token = secrets.token_urlsafe(32)
            db.execute('UPDATE challenges SET used=? WHERE user_id=? AND purpose=? AND used IS NULL',
                       (self.clock(), user['id'], purpose))
            db.execute('INSERT INTO challenges(hash,user_id,purpose,expires) VALUES(?,?,?,?)',
                       (digest(token), user['id'], purpose, self.clock()+900))
        try:
            self.mail(email, purpose, token)
        except Exception:
            # Delivery errors are intentionally redacted; secrets never enter logs.
            with self.connect() as db:
                db.execute('UPDATE challenges SET used=? WHERE hash=?', (self.clock(), digest(token)))
                db.execute('INSERT INTO security_events(event,result,stamp) VALUES(?,?,?)',
                           ('MAIL_DELIVERY', 'FAILED', self.clock()))

    def consume(self, token, purpose, password=None):
        if purpose == 'RESET':
            self.password(password or '')
            hashed = self.hasher.hash(password)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM challenges WHERE hash=? AND purpose=? AND used IS NULL AND expires>?',
                             (digest(token), purpose, self.clock())).fetchone()
            if not row:
                raise ValueError('This challenge is invalid, expired or already used.')
            db.execute('UPDATE challenges SET used=? WHERE hash=?', (self.clock(), digest(token)))
            if purpose == 'VERIFY':
                db.execute('UPDATE users SET verified=1 WHERE id=?', (row['user_id'],))
            else:
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (hashed, row['user_id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))

    def login(self, email, password, role):
        try:
            email = email_address(email)
        except ValueError:
            email = ''
        with self.connect() as db:
            user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        try:
            valid = self.hasher.verify(user['password_hash'] if user else self.dummy, password)
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or not user or not user['verified'] or user['disabled'] or user['role'] != role:
            return None
        sid = secrets.token_urlsafe(32)
        stamp = self.clock()
        with self.connect() as db:
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',
                       (digest(sid), user['id'], stamp, stamp, stamp+8*3600))
        return sid

    def user(self, sid):
        with self.connect() as db:
            row = db.execute('''SELECT u.*,s.created AS login_at FROM users u JOIN sessions s
                ON s.user_id=u.id WHERE s.hash=? AND s.expires>? AND s.last_seen>?
                AND u.verified=1 AND u.disabled=0''', (digest(sid), self.clock(), self.clock()-1800)).fetchone()
            if row:
                db.execute('UPDATE sessions SET last_seen=? WHERE hash=?', (self.clock(), digest(sid)))
        return dict(row) if row else None

    def logout(self, sid):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE hash=?', (digest(sid),))

    def change_password(self, sid, current, replacement):
        user = self.user(sid)
        if not user:
            raise ValueError('Sign in again.')
        try:
            self.hasher.verify(user['password_hash'], current)
        except VerificationError:
            raise ValueError('Current password was not accepted.') from None
        self.password(replacement)
        with self.connect() as db:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',
                       (self.hasher.hash(replacement), user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))

    def provision(self, email, team, legacy=False):
        if team not in RESPONSE_TEAMS:
            raise ValueError('Choose an authorized demo team.')
        with self.connect() as db:
            changed = db.execute("UPDATE users SET role='responder',team=?,legacy=? WHERE email=? AND verified=1 AND disabled=0",
                                 (team, int(legacy), email_address(email))).rowcount
            if not changed:
                raise ValueError('A verified eligible account is required.')
            db.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)', (email_address(email),))
            db.execute('INSERT INTO security_events(event,result,stamp) VALUES(?,?,?)',
                       ('RESPONDER_PROVISIONED', 'ALLOWED', self.clock()))

    def accept(self, owner, payload):
        validate_alert(payload)
        with self.connect() as db:
            db.execute('INSERT INTO submission_intents(alert_id,owner_id,payload) VALUES(?,?,?)',
                       (payload['alert_id'], owner, canonical(payload)))

    def reconcile(self, outbox):
        with self.connect() as db:
            intents = db.execute('SELECT * FROM submission_intents WHERE enqueued=0').fetchall()
        for row in intents:
            outbox.enqueue_owned(json.loads(row['payload']), row['owner_id'])
            with self.connect() as db:
                db.execute('UPDATE submission_intents SET enqueued=1 WHERE alert_id=?', (row['alert_id'],))

    def sign(self, req, principal):
        value = dict(principal, issued=self.clock())
        value['mac'] = hmac.new(self.key, canonical([req, value]).encode(), 'sha256').hexdigest()
        return value

    def principal(self, req):
        context = dict(req.get('principal') or {})
        mac = context.pop('mac', '')
        body = {k:v for k,v in req.items() if k != 'principal'}
        expected = hmac.new(self.key, canonical([body, context]).encode(), 'sha256').hexdigest()
        if not isinstance(mac,str) or not hmac.compare_digest(mac, expected) or abs(self.clock()-context.get('issued',0)) > 30:
            raise ValueError('Invalid principal')
        if 'sid' in context:
            user = self.user(context['sid'])
            if not user:
                raise ValueError('Expired principal')
            return user
        aid = context.get('intent')
        if req['type'] not in ('SUBMIT_ALERT', 'GET_STATUS') or req['payload'].get('alert_id') != aid:
            raise ValueError('Invalid worker operation')
        with self.connect() as db:
            intent = db.execute('SELECT * FROM submission_intents WHERE alert_id=?', (aid,)).fetchone()
        if not intent or (req['type']=='SUBMIT_ALERT' and canonical(req['payload']) != intent['payload']):
            raise ValueError('Invalid submission intent')
        return dict(id=intent['owner_id'], role='student', job=True)


def configured_mail():
    """No fallback verification bypass; SMTP secrets are read only at send time."""
    import os
    import smtplib
    from email.message import EmailMessage
    if not all(os.environ.get(k) for k in ('SAFESIGNAL_SMTP_HOST', 'SAFESIGNAL_MAIL_FROM')):
        return None
    def deliver(email, purpose, token):
        message = EmailMessage()
        message['From'], message['To'] = os.environ['SAFESIGNAL_MAIL_FROM'], email
        message['Subject'] = 'SafeSignal simulation — '+('verify your email' if purpose=='VERIFY' else 'password reset')
        message.set_content('Enter this one-time challenge in SafeSignal within 15 minutes:\n\n'+token+
                            '\n\nSimulation only. Do not share this challenge.')
        with smtplib.SMTP(os.environ['SAFESIGNAL_SMTP_HOST'], int(os.environ.get('SAFESIGNAL_SMTP_PORT','587')), timeout=15) as smtp:
            smtp.starttls()
            if os.environ.get('SAFESIGNAL_SMTP_USER'):
                smtp.login(os.environ['SAFESIGNAL_SMTP_USER'], os.environ['SAFESIGNAL_SMTP_PASSWORD'])
            smtp.send_message(message)
    return deliver
