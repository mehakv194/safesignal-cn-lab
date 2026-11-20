"""Individual accounts and durable submission ownership; no browser role assertions."""
import hashlib
import hmac
import json
import re
import secrets
import time
import threading
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHashError

from .models import validate_alert, RESPONSE_TEAMS
from .database import connection


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
        self.mfa = None
        self.release_profiles = None
        self.release_emails = {}
        self.monitor = None
        self.path, self.clock, self.mail = str(path), clock, mail
        self.key = hmac.digest(secret.encode(), b'safesignal-principal-v2', 'sha256')
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
        self.password_slots=threading.BoundedSemaphore(2)
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
                CREATE TABLE IF NOT EXISTS login_failures(key TEXT NOT NULL,stamp REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS failure_window ON login_failures(key,stamp);
            ''')
            if 'legacy' not in {r[1] for r in db.execute('PRAGMA table_info(users)')}:
                db.execute('ALTER TABLE users ADD COLUMN legacy INTEGER NOT NULL DEFAULT 0')
            for name in ('actor_id','target_type','target_id','reason_code'):
                if name not in {r[1] for r in db.execute('PRAGMA table_info(security_events)')}:
                    db.execute(f"ALTER TABLE security_events ADD COLUMN {name} TEXT NOT NULL DEFAULT ''")
            db.execute('INSERT OR IGNORE INTO schema_migrations VALUES(4)')

    def audit(self,event,result,actor='',target_type='',target_id='',reason=''):
        with self.connect() as db:
            db.execute('INSERT INTO security_events(event,result,stamp,actor_id,target_type,target_id,reason_code) VALUES(?,?,?,?,?,?,?)',
                       (event,result,self.clock(),actor,target_type,str(target_id)[:64],reason))

    def failed_login(self,account,ip):
        if self.monitor:
            self.monitor.login(account,ip)
            return
        key=digest(account+'|'+ip)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM login_failures WHERE stamp<?',(self.clock()-60,))
            count=db.execute('SELECT count(*) FROM login_failures WHERE key=?',(key,)).fetchone()[0]
            # At most six markers per key/window; normal auth throttling caps requests too.
            if count<6:
                db.execute('INSERT INTO login_failures VALUES(?,?)',(key,self.clock()))
            if count==4:
                db.execute('INSERT INTO security_events(event,result,stamp,reason_code) VALUES(?,?,?,?)',
                           ('LOGIN_BURST','DETECTED',self.clock(),'FIVE_FAILED_LOGINS_IN_60S'))

    def connect(self):
        return connection(self.path)

    def seed_demo_accounts(self, password_hashes):
        with self.connect() as db:
            for role, email, team in (
                ('student', '0000000001@mail.jiit.ac.in', ''),
                ('responder', '0000000002@mail.jiit.ac.in', 'Medical Team'),
            ):
                hashed = password_hashes[role]
                if not hashed.startswith('$argon2id$'):
                    raise ValueError('Demo accounts require Argon2id password hashes')
                updated = db.execute('''INSERT INTO users(id,email,password_hash,role,verified,team,created)
                    VALUES(?,?,?,?,1,?,?) ON CONFLICT(email) DO UPDATE SET password_hash=excluded.password_hash
                    WHERE users.password_hash != excluded.password_hash''',
                    (str(uuid4()), email, hashed, role, team, self.clock()))
                if updated.rowcount:
                    db.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)', (email,))

    def hash_password(self,value):
        with self.password_slots:
            return self.hasher.hash(value)

    def verify_password(self,hashed,value):
        with self.password_slots:
            return self.hasher.verify(hashed,value)

    def limit(self, action, account, ip, *, window=900, maxima=(8,40)):
        stamp = self.clock()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM auth_limits WHERE stamp<?', (stamp-900,))
            keys = (digest(action+':account:'+account), digest(action+':ip:'+ip))
            if any(db.execute('SELECT count(*) FROM auth_limits WHERE key=? AND stamp>?', (key,stamp-window)).fetchone()[0] >= maximum
                   for key, maximum in zip(keys, maxima)):
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
        hashed = self.hash_password(password)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO users(id,email,password_hash,created) VALUES(?,?,?,?)',
                       (str(uuid4()), email, hashed, self.clock()))
        self.challenge(email, 'VERIFY')

    def redeem_invite(self, email, code, password, invite, *, role='student'):
        email = email_address(email)
        code = code.strip()
        proof = digest(f'safesignal-invite-v1:{email}:{code}')
        if (len(code) != 43 or self.clock() >= invite['expires_at']
                or not hmac.compare_digest(proof, invite['commitment'])):
            raise ValueError('Invalid or expired invitation.')
        self.password(password)
        team = invite.get('team', '') if role == 'responder' else ''
        if role not in ('student', 'responder') or (role == 'responder' and team not in RESPONSE_TEAMS):
            raise ValueError('This invitation is unavailable.')
        password_hash = self.hash_password(password)
        account_id = str(uuid4())
        with self.connect() as db:
            created = db.execute(
                '''INSERT INTO users(id,email,password_hash,created,role,team,verified)
                   VALUES(?,?,?,?,?,?,1) ON CONFLICT(email) DO NOTHING''',
                (account_id, email, password_hash, self.clock(), role, team),
            ).rowcount
            if not created:
                raise ValueError('This invitation has already been used. Sign in with your chosen password.')
            db.execute(
                '''INSERT INTO security_events(event,result,stamp,actor_id,reason_code)
                   VALUES(?,?,?,?,?)''',
                (f'{role.upper()}_INVITE_REDEEMED', 'ALLOWED', self.clock(), account_id, 'MAILBOX_CODE'),
            )

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
            hashed = self.hash_password(password)
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
            if self.mfa:
                db.execute('DELETE FROM mfa_pending WHERE user_id=?', (row['user_id'],))

    def login(self, email, password, role, ip='', *, pending=False, profile=None):
        try:
            email = email_address(email)
        except ValueError:
            email = ''
        with self.connect() as db:
            if self.release_profiles is not None:
                name = 'student' if role=='student' else profile
                uid = self.release_profiles.get((email,name))
                user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
            else:
                user = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        try:
            valid = self.verify_password(user['password_hash'] if user else self.dummy, password)
        except (VerificationError, InvalidHashError):
            valid = False
        if not valid or not user or not user['verified'] or user['disabled'] or user['role'] != role:
            self.failed_login(email,ip)
            return None
        if role=='responder' and self.mfa:
            return self.mfa.begin(user['id'],user['password_hash']) if pending else None
        with self.connect() as db:
            return self.new_session(db,user['id'],self.clock())

    @staticmethod
    def new_session(db, uid, stamp):
        sid = secrets.token_urlsafe(32)
        db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(digest(sid), uid, stamp, stamp, stamp+8*3600))
        return sid

    def user(self, sid):
        with self.connect() as db:
            row = db.execute('''SELECT u.*,s.created AS login_at FROM users u JOIN sessions s
                ON s.user_id=u.id WHERE s.hash=? AND s.expires>? AND s.last_seen>?
                AND u.verified=1 AND u.disabled=0''', (digest(sid), self.clock(), self.clock()-1800)).fetchone()
            if row and self.mfa and row['role']=='responder' and (not self.mfa.key or not db.execute(
                'SELECT 1 FROM mfa_sessions m JOIN mfa_factors f ON f.user_id=? WHERE m.hash=?',
                (row['id'],digest(sid))).fetchone()):
                return None
            if row:
                db.execute('UPDATE sessions SET last_seen=? WHERE hash=?', (self.clock(), digest(sid)))
        return dict(row, email=self.release_emails.get(row['id'],row['email'])) if row else None

    def logout(self, sid):
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE hash=?', (digest(sid),))

    def change_password(self, sid, current, replacement):
        user = self.user(sid)
        if not user:
            raise ValueError('Sign in again.')
        try:
            self.verify_password(user['password_hash'], current)
        except VerificationError:
            raise ValueError('Current password was not accepted.') from None
        self.password(replacement)
        with self.connect() as db:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',
                       (self.hash_password(replacement), user['id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
            if self.mfa:
                db.execute('DELETE FROM mfa_pending WHERE user_id=?',(user['id'],))

    def provision(self, email, team, legacy=False):
        if team not in (*RESPONSE_TEAMS, 'Cyber Response', 'Security Review'):
            raise ValueError('Choose an authorized demo team.')
        with self.connect() as db:
            changed = db.execute("UPDATE users SET role='responder',team=?,legacy=? WHERE email=? AND verified=1 AND disabled=0",
                                 (team, int(legacy), email_address(email))).rowcount
            if not changed:
                raise ValueError('A verified eligible account is required.')
            db.execute('DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE email=?)', (email_address(email),))
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='mfa_pending'").fetchone():
                db.execute('DELETE FROM mfa_pending WHERE user_id=(SELECT id FROM users WHERE email=?)',(email_address(email),))
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
