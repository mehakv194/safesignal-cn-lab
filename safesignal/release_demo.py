"""Restore approved, isolated role profiles for an ephemeral classroom demo."""
import json
from uuid import NAMESPACE_URL, uuid5

from argon2 import extract_parameters, Type
from argon2.exceptions import InvalidHashError

from .identity import email_address

PROFILES = {'student': ('student', ''), 'responder': ('responder', 'Cyber Response'),
            'reviewer': ('responder', 'Security Review')}


def provision(identity, raw):
    records = json.loads(raw)
    if not isinstance(records, dict) or len(records) != 2:
        raise ValueError('Supply exactly two distinct, approved JIIT addresses.')
    accounts = []
    try:
        for value, password_hash in records.items():
            email = email_address(value)
            if email in ('0000000001@mail.jiit.ac.in','0000000002@mail.jiit.ac.in'):
                raise ValueError()
            params = extract_parameters(password_hash)
            if (params.type != Type.ID or not 19456 <= params.memory_cost <= 65536
                    or not 2 <= params.time_cost <= 4 or not 1 <= params.parallelism <= 4
                    or params.salt_len < 16 or params.hash_len < 32):
                raise ValueError()
            accounts.append((email,password_hash))
        if len({row[0] for row in accounts}) != len(accounts):
            raise ValueError()
    except (ValueError, TypeError, InvalidHashError):
        raise ValueError('Use distinct, verified demo addresses and valid operator-generated Argon2id hashes.') from None
    profiles = {}
    with identity.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for email,password_hash in accounts:
            for name,(role,team) in PROFILES.items():
                uid = str(uuid5(NAMESPACE_URL, f'securesignal:classroom:{email}:{name}'))
                storage_email = f'{uid}@demo.invalid'
                old = db.execute('SELECT email,role,team,verified,disabled FROM users WHERE id=?',(uid,)).fetchone()
                if old and tuple(old) != (storage_email,role,team,1,0):
                    raise ValueError('A configured demo profile conflicts with an existing profile.')
                if not old:
                    db.execute('INSERT INTO users(id,email,password_hash,role,team,verified,created) VALUES(?,?,?,?,?,1,?)',
                               (uid,storage_email,password_hash,role,team,identity.clock()))
                profiles[(email,name)] = uid
        active = set(profiles.values())
        existing = db.execute("SELECT id FROM users WHERE email LIKE '%@demo.invalid'").fetchall()
        for row in existing:
            if row['id'] not in active:
                db.execute('UPDATE users SET disabled=1 WHERE id=?',(row['id'],))
                db.execute('DELETE FROM sessions WHERE user_id=?',(row['id'],))
    identity.release_profiles = profiles
    identity.release_emails = {uid:email for (email,_),uid in profiles.items()}
