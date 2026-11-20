"""Local-only synthetic accounts and keys kept outside version control."""
import base64
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from .identity import Identity

ACCOUNTS = ('student','other-student','responder','reviewer')


def config_for_demo(path):
    path = Path(path)
    path.mkdir(parents=True,exist_ok=True)
    credentials = path/'fixture.json'
    if not credentials.exists():
        if (path/'server.sqlite').exists() or (path/'outbox.sqlite').exists():
            raise RuntimeError('Demo keys are missing. Restore fixture.json from a backup before using existing data.')
        value={key:secrets.token_urlsafe(32) for key in ('session_secret','sender_token','responder_token')}
        # Encode as standard base64, like externally provisioned keys.
        value['mfa_key']=base64.b64encode(secrets.token_bytes(32)).decode()
        value['evidence_keys']={'v1':base64.b64encode(secrets.token_bytes(32)).decode()}
        value['passwords']={role:secrets.token_urlsafe(18) for role in ACCOUNTS}
        fd=os.open(credentials,os.O_WRONLY | os.O_CREAT | os.O_EXCL,0o600)
        with os.fdopen(fd,'w',encoding='utf-8') as file:
            json.dump(value,file,indent=2)
    value=json.loads(credentials.read_text(encoding='utf-8'))
    passwords=value.pop('passwords')
    identity=Identity(path/'server.sqlite',value['session_secret'])
    for n,role in enumerate(ACCOUNTS,1):
        email=f'{n:010}@mail.jiit.ac.in'
        with identity.connect() as db:
            if db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():
                continue
        with identity.connect() as db:
            db.execute('INSERT INTO users(id,email,password_hash,verified,created) VALUES(?,?,?,1,?)',
                       (str(uuid4()),email,identity.hash_password(passwords[role]),identity.clock()))
        if role=='responder':
            identity.provision(email,'Cyber Response')
        elif role=='reviewer':
            identity.provision(email,'Security Review')
    return dict(value,mail=None)
