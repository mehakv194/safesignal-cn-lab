"""Bounded, encrypted evidence, committed atomically with metadata in private SQLite."""
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import os
from pathlib import PurePath
import re
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from PIL import Image
from .identity import canonical


MEDIA = {'.png':'image/png','.jpeg':'image/jpeg','.jpg':'image/jpeg',
         '.txt':'text/plain','.log':'text/plain','.eml':'message/rfc822'}


def validate_file(filename, raw):
    name = filename.replace('\\','/').rsplit('/',1)[-1]
    name = ''.join(c for c in name if c.isprintable())[:180]
    ext = PurePath(name).suffix.lower()
    mime = MEDIA.get(ext)
    if not mime or not raw:
        raise ValueError('Choose a nonempty PNG, JPEG, TXT, LOG or EML file.')
    if mime.startswith('image/'):
        try:
            with Image.open(BytesIO(raw), formats=['PNG','JPEG']) as image:
                if Image.MIME[image.format]!=mime or image.width*image.height>12_000_000 or getattr(image,'is_animated',False):
                    raise ValueError()
                image.verify()
            with Image.open(BytesIO(raw), formats=['PNG','JPEG']) as image:
                image.load()
        except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
            raise ValueError('Invalid or oversized screenshot.') from None
    else:
        try:
            body=raw.decode('utf-8-sig')
            if any(not c.isprintable() and c not in '\t\r\n' for c in body):
                raise ValueError()
            if mime=='message/rfc822':
                header, sep, _ = body.replace('\r\n','\n').partition('\n\n')
                if not sep or len(header)>32768 or not re.search(r'(?im)^(from|to|subject|date|message-id):',header):
                    raise ValueError()
                if any(not re.match(r'^[!-9;-~]+:|^[ \t]',line) for line in header.splitlines()):
                    raise ValueError()
        except ValueError:
            raise ValueError('Use UTF-8 text or an EML file with valid message headers.') from None
    return name,mime


class Evidence:
    def __init__(self, cases, keys, active, enabled=True, max_size=5*1024**2, max_files=10, account_bytes=50*1024**2):
        self.cases, self.active = cases, active
        self.keys = {key_id:AESGCM(key) for key_id,key in keys.items()}
        self.enabled = enabled and active in self.keys
        self.max_size, self.max_files, self.account_bytes = max_size, max_files, account_bytes
        with cases.identity.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS cyber_evidence(
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL, previous TEXT, name TEXT NOT NULL,
                    mime TEXT NOT NULL, size INTEGER NOT NULL, hash TEXT NOT NULL, created REAL NOT NULL,
                    actor TEXT NOT NULL, version INTEGER NOT NULL, key_id TEXT NOT NULL,
                    nonce BLOB NOT NULL, ciphertext BLOB NOT NULL, UNIQUE(key_id,nonce));
                CREATE INDEX IF NOT EXISTS cyber_evidence_case ON cyber_evidence(case_id,created);
                CREATE INDEX IF NOT EXISTS cyber_evidence_actor ON cyber_evidence(actor);
                INSERT OR IGNORE INTO schema_migrations VALUES(7);
            """)

    @staticmethod
    def aad(row):
        return canonical([row[k] for k in ('version','id','case_id','previous','name','mime','size','hash','created','actor','key_id')]).encode()

    def upload(self, user, aid, file, previous=None):
        if not self.enabled:
            raise RuntimeError('Evidence upload is unavailable: durable storage and a key are required.')
        raw = file.stream.read(self.max_size+1)
        if len(raw)>self.max_size:
            raise ValueError('The file exceeds the evidence size limit.')
        name,mime = validate_file(file.filename,raw)
        identity=self.cases.identity
        row = dict(id=str(uuid4()), case_id=aid, previous=previous, name=name, mime=mime, size=len(raw),
                   hash=sha256(raw).hexdigest(), created=identity.clock(), actor=user['id'], version=1, key_id=self.active)
        nonce=os.urandom(12)
        cipher=self.keys[self.active].encrypt(nonce,raw,self.aad(row))
        with identity.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not self.cases.get(db,user,aid):
                raise PermissionError()
            if previous and not db.execute('SELECT 1 FROM cyber_evidence WHERE id=? AND case_id=?',(previous,aid)).fetchone():
                raise ValueError('The earlier evidence record does not belong to this case.')
            if (db.execute('SELECT count(*) FROM cyber_evidence WHERE case_id=?',(aid,)).fetchone()[0]>=self.max_files or
                db.execute('SELECT coalesce(sum(size),0) FROM cyber_evidence WHERE actor=?',(user['id'],)).fetchone()[0]+len(raw)>self.account_bytes):
                raise ValueError('Evidence quota reached.')
            db.execute('INSERT INTO cyber_evidence VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(*row.values(),nonce,cipher))
            self.audit(db, user, row['id'], 'EVIDENCE_UPLOAD')
        return row['id']

    def audit(self, db, user, target, event, result='ALLOWED'):
        db.execute("""INSERT INTO security_events(event,result,stamp,actor_id,target_type,target_id)
                    VALUES(?,?,?,?,?,?)""",(event,result,self.cases.identity.clock(),user['id'],'evidence',target))

    def list(self, db, aid):
        return [dict(r) for r in db.execute("""SELECT id,case_id,previous,name,mime,size,hash,created,actor,version
                          FROM cyber_evidence WHERE case_id=? ORDER BY created,id""",(aid,))]

    def manifest(self, user, aid):
        with self.cases.identity.connect() as db:
            if not self.cases.get(db,user,aid):
                raise PermissionError()
            rows = self.list(db,aid)
            self.audit(db,user,aid,'EVIDENCE_EXPORT')
        for row in rows:
            row['uploaded_at'] = datetime.fromtimestamp(row.pop('created'),timezone.utc).isoformat()
            row['sha256'] = row.pop('hash')
        return dict(schema_version=1,case_id=aid,evidence=rows,exported_by=user['id'],
                    exported_at=datetime.fromtimestamp(self.cases.identity.clock(),timezone.utc).isoformat(),
                    integrity_note='A matching hash shows consistency with the recorded original, not truthfulness or legal admissibility.')

    def verify(self, row):
        key = self.keys.get(row['key_id'])
        if not key:
            raise RuntimeError('The recorded evidence key is unavailable.')
        raw = key.decrypt(row['nonce'],row['ciphertext'],self.aad(row))
        if len(raw)!=row['size'] or sha256(raw).hexdigest()!=row['hash']:
            raise InvalidTag()
        return raw

    def download(self, user, aid, eid):
        with self.cases.identity.connect() as db:
            if not self.cases.get(db,user,aid):
                raise PermissionError()
            row=db.execute('SELECT * FROM cyber_evidence WHERE id=? AND case_id=?',(eid,aid)).fetchone()
            if not row:
                raise PermissionError()
            try:
                raw=self.verify(row)
            except (InvalidTag,RuntimeError):
                self.audit(db,user,eid,'EVIDENCE_VERIFY','FAILED')
                return row,None
            self.audit(db,user,eid,'EVIDENCE_DOWNLOAD')
        return row,raw
