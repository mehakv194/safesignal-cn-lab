"""Authenticator enrollment, replay protection, and server-side session management."""
import base64
import hmac
import os
import re
import secrets
from hashlib import sha256

import pyotp
from argon2.exceptions import VerificationError, InvalidHashError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def secret_key(value):
    if not value:
        return None
    try:
        key = base64.b64decode(value, validate=True)
        if len(key)==32:
            return key
    except ValueError:
        pass
    raise ValueError('SecureSignal keys must encode 32 random bytes in base64.')


def digest(value):
    return sha256(value.encode()).hexdigest()


class MFA:
    def __init__(self, identity, key):
        self.identity = identity
        self.key = AESGCM(key) if key else None
        with identity.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS mfa_factors(
                    user_id TEXT PRIMARY KEY, secret BLOB NOT NULL, step INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS mfa_pending(
                    token TEXT PRIMARY KEY, user_id TEXT UNIQUE NOT NULL, expires REAL NOT NULL, secret BLOB);
                CREATE TABLE IF NOT EXISTS mfa_recovery(
                    user_id TEXT NOT NULL, code TEXT NOT NULL, PRIMARY KEY(user_id,code));
                CREATE TABLE IF NOT EXISTS mfa_sessions(hash TEXT PRIMARY KEY);
                INSERT OR IGNORE INTO schema_migrations VALUES(6);
            """)

    def seal(self, uid, seed):
        nonce = os.urandom(12)
        return nonce + self.key.encrypt(nonce,seed.encode(),uid.encode())

    def open(self, uid, box):
        return self.key.decrypt(box[:12],box[12:],uid.encode()).decode()

    def begin(self, uid, password_hash):
        if not self.key:
            raise RuntimeError('Authenticator key is unavailable.')
        token = secrets.token_urlsafe(32)
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            account = db.execute("SELECT 1 FROM users WHERE id=? AND password_hash=? AND role='responder' AND verified=1 AND disabled=0",(uid,password_hash)).fetchone()
            if not account:
                return None
            db.execute('DELETE FROM mfa_pending WHERE expires<=? OR user_id=?',(self.identity.clock(),uid))
            db.execute('DELETE FROM mfa_sessions WHERE hash NOT IN (SELECT hash FROM sessions)')
            active = db.execute('SELECT 1 FROM mfa_factors WHERE user_id=?',(uid,)).fetchone()
            seed = None if active else self.seal(uid,pyotp.random_base32())
            db.execute('INSERT INTO mfa_pending VALUES(?,?,?,?)',(digest(token),uid,self.identity.clock()+300,seed))
        return token

    def pending(self, token):
        with self.identity.connect() as db:
            row = db.execute("""SELECT p.*,u.email FROM mfa_pending p JOIN users u ON u.id=p.user_id
                WHERE token=? AND expires>? AND u.role='responder' AND u.verified=1 AND u.disabled=0""",
                             (digest(token),self.identity.clock())).fetchone()
        return row

    def uri(self, row):
        if not row or row['secret'] is None:
            return None
        return pyotp.TOTP(self.open(row['user_id'],row['secret'])).provisioning_uri(row['email'],issuer_name='SecureSignal')

    def consume(self, db, uid, code, factor):
        if re.fullmatch('[0-9]{6}',code):
            totp = pyotp.TOTP(self.open(uid,factor['secret']))
            step = int(self.identity.clock()//30)
            matched = next((s for s in (step+1,step,step-1) if s>factor['step'] and
                            hmac.compare_digest(totp.generate_otp(s),code)), None)
            if matched is not None:
                db.execute('UPDATE mfa_factors SET step=? WHERE user_id=?',(matched,uid))
                return matched
        elif len(code)==32 and db.execute('DELETE FROM mfa_recovery WHERE user_id=? AND code=?',
                                         (uid,digest(code))).rowcount:
            return factor['step']
        return None

    def finish(self, token, code):
        if not self.key:
            raise RuntimeError('Authenticator key is unavailable.')
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            now = self.identity.clock()
            row = db.execute("""SELECT p.* FROM mfa_pending p JOIN users u ON u.id=p.user_id
                WHERE token=? AND expires>? AND u.role='responder' AND u.verified=1 AND u.disabled=0""",
                             (digest(token),now)).fetchone()
            if not row:
                return None, []
            uid = row['user_id']
            factor = db.execute('SELECT * FROM mfa_factors WHERE user_id=?',(uid,)).fetchone()
            codes = []
            if factor:
                if self.consume(db,uid,code,factor) is None:
                    return None, []
            else:
                if not row['secret'] or not re.fullmatch('[0-9]{6}',code):
                    return None, []
                db.execute('INSERT INTO mfa_factors VALUES(?,?,-1)',(uid,row['secret']))
                if self.consume(db,uid,code,dict(secret=row['secret'],step=-1)) is None:
                    db.execute('DELETE FROM mfa_factors WHERE user_id=?',(uid,))
                    return None, []
                codes = [secrets.token_hex(16) for _ in range(8)]
                db.executemany('INSERT INTO mfa_recovery VALUES(?,?)',((uid,digest(c)) for c in codes))
            db.execute('DELETE FROM mfa_pending WHERE user_id=?',(uid,))
            sid = self.identity.new_session(db,uid,now)
            db.execute('INSERT INTO mfa_sessions VALUES(?)',(digest(sid),))
        return sid, codes

    def cancel(self, token):
        with self.identity.connect() as db:
            db.execute('DELETE FROM mfa_pending WHERE token=?',(digest(token),))

    def replace(self, uid, password, code):
        with self.identity.connect() as db:
            user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
        try:
            if not user or not self.identity.verify_password(user['password_hash'],password):
                return False
        except (VerificationError, InvalidHashError):
            return False
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute("SELECT password_hash FROM users WHERE id=? AND role='responder' AND verified=1 AND disabled=0",(uid,)).fetchone()
            if not current or current[0]!=user['password_hash']:
                return False
            factor = db.execute('SELECT * FROM mfa_factors WHERE user_id=?',(uid,)).fetchone()
            if not factor or self.consume(db,uid,code,factor) is None:
                return False
            for table in ('mfa_factors','mfa_recovery','mfa_pending','sessions'):
                db.execute(f'DELETE FROM {table} WHERE user_id=?',(uid,))
        return True

    def sessions(self, uid, sid):
        now = self.identity.clock()
        with self.identity.connect() as db:
            return [dict(created=r['created'],last_seen=r['last_seen'], current=r['hash']==digest(sid),
                         reference=hmac.new(self.identity.key,r['hash'].encode(),'sha256').hexdigest())
                    for r in db.execute('SELECT * FROM sessions WHERE user_id=? AND expires>? AND last_seen>? ORDER BY created DESC',
                                        (uid,now,now-1800))]

    def revoke(self, uid, reference):
        with self.identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for row in db.execute('SELECT hash FROM sessions WHERE user_id=?',(uid,)).fetchall():
                ref=hmac.new(self.identity.key,row['hash'].encode(),'sha256').hexdigest()
                if hmac.compare_digest(ref,reference):
                    db.execute('DELETE FROM sessions WHERE hash=?',(row['hash'],))
                    db.execute('DELETE FROM mfa_sessions WHERE hash=?',(row['hash'],))
