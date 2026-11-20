import base64
import io
import re
import time
from uuid import uuid4

from cryptography.exceptions import InvalidTag
import pyotp
import pytest
from werkzeug.test import Client
from werkzeug.wrappers import Response

from safesignal.cyber_cases import Cases
from safesignal.cyber_evidence import Evidence, validate_file
from safesignal.cyber_monitor import Monitor
from safesignal.hosted import hosted_runtime
from safesignal.identity import Identity
from safesignal.mfa import MFA
from test_combined_app import csrf


def enroll(identity, number, team=None):
    email=f'{number:010}@mail.jiit.ac.in'
    password='Synthetic testing password 3401'
    with identity.connect() as db:
        db.execute('INSERT INTO users(id,email,password_hash,verified,created) VALUES(?,?,?,1,?)',
                   (str(uuid4()),email,identity.hash_password(password),identity.clock()))
    if team:
        identity.provision(email,team)
    return email,password


def login(client, prefix, account):
    route=f'/{prefix}/login'
    token=csrf(client.get(route))
    return client.post(route,data=dict(csrf=token,email=account[0],password=account[1]))


def enroll_mfa(client):
    assert client.get('/responder/').location == '/responder/mfa'
    page=client.get('/responder/mfa')
    seed=re.search(r'<code>([A-Z2-7]{32})</code>',page.text)[1]
    assert client.get('/responder/mfa/qr').mimetype == 'image/png'
    token=csrf(page)
    assert 'invalid' in client.post('/responder/mfa',data=dict(csrf=token,code='invalid')).text
    result=client.post('/responder/mfa',data=dict(csrf=token,code=pyotp.TOTP(seed).now()))
    assert 'Save your recovery codes' in result.text
    return re.findall(r'<code>([a-f0-9]{32})</code>',result.text)


def test_cyber_complete_journey(tmp_path):
    identity=Identity(tmp_path/'server.sqlite','fixture-secret')
    student=enroll(identity,1)
    other=enroll(identity,2)
    desk=enroll(identity,3,'Cyber Response')
    reviewer=enroll(identity,4,'Security Review')
    old_sid=identity.login(*desk,'responder')
    config=dict(identity=True, hosted=False, cyber=True, session_secret='fixture-secret',
                sender_token='sender', responder_token='responder',mail=None,
                mfa_key=base64.b64encode(b'm'*32).decode(),
                evidence_keys={'v1':base64.b64encode(b'e'*32).decode()},
                evidence_limits={'max_size':128, 'max_files':1},
                security_rules={'CASE_ACCESS':(2,60,300)})
    raw=b'Original synthetic evidence bytes.\r\n'
    with hosted_runtime(config,tmp_path,enable_faults=True) as app:
        clients=[Client(app,Response) for _ in range(4)]
        sender,stranger,responder,security=clients
        assert 'SecureSignal' in sender.get('/').text
        assert login(sender,'sender',student).status_code==302
        assert login(stranger,'sender',other).status_code==302
        assert login(responder,'responder',desk).location=='/responder/mfa'
        assert login(security,'responder',reviewer).location=='/responder/mfa'
        for path in ('/sender/walks','/sender/?view=network','/sender/trust-lab'):
            text=sender.get(path).text
            assert 'Connection controls' not in text and 'SafeWalk' not in text
        report=sender.get('/sender/report')
        assert 'data-category="PHISHING"' in report.text
        op=str(uuid4())
        form=dict(csrf=csrf(report),operation=op,title='Suspicious <b>subject</b>',description='Unexpected sign in notice')
        invalid=sender.post('/sender/report',data=dict(form,category='FIRE'))
        assert invalid.status_code==422 and 'Suspicious &lt;b&gt;subject' in invalid.text
        form.update(category='PHISHING', **{'PHISHING-indicator':'https://synthetic.invalid/'})
        posted=sender.post('/sender/report',data=dict(form,file=(io.BytesIO(raw),'../../synthetic.txt')))
        assert posted.status_code==303
        path=posted.location
        initial=sender.get(path)
        assert initial.status_code==200 and 'https://synthetic.invalid/' in initial.text
        assert 'href="https://synthetic.invalid/' not in initial.text
        assert responder.get(path.replace('/sender','/responder')).location=='/responder/mfa'
        codes=enroll_mfa(responder)
        enroll_mfa(security)
        for _ in range(60):
            if 'Server storage confirmed' in sender.get(path).text:
                break
            time.sleep(.1)
        else:
            pytest.fail('TLS receipt did not arrive')
        assert sender.post('/sender/report',data=form).location==path
        assert sender.post(path+'/message',data={'body':'Missing CSRF'}).status_code==400
        mine=sender.get(path)
        evidence=re.search(r'href="([^"]+/evidence/[^"]+)"',mine.text)[1]
        assert sender.get(evidence).data==raw
        assert 'attachment' in sender.get(evidence).headers['Content-Disposition']
        manifest=sender.get(path+'/manifest').json
        assert manifest['evidence'][0]['name']=='synthetic.txt'
        assert stranger.get(path).status_code==404
        assert stranger.get(evidence).status_code==404
        assert stranger.get(path+'/manifest').status_code==404
        assert security.get(path.replace('/sender','/responder')).status_code==404
        room_token=re.search(r'name="client_uuid" value="([^"]+)"',mine.text)[1]
        assert sender.post(path+'/message',headers={'Accept':'application/json'},data=dict(csrf=csrf(mine),client_uuid=room_token,body='Synthetic update')).status_code==200
        desk_path=path.replace('/sender','/responder')
        page=responder.get(desk_path)
        assert 'Synthetic update' in page.text
        assert 'automatic reply' not in page.text
        action=dict(csrf=csrf(page),operation=str(uuid4()),reason='Scope and ownership confirmed')
        assert responder.post(desk_path+'/advance',data=dict(action,target='CLOSED')).status_code==422
        for state in ('TRIAGED','INVESTIGATING','CONTAINED','RECOVERED','CLOSED'):
            action=dict(action,operation=str(uuid4()),target=state)
            assert responder.post(desk_path+'/advance',data=action).status_code==303
            assert responder.post(desk_path+'/advance',data=action).status_code==303
        assert 'Closed' in sender.get(path).text
        assert responder.get('/responder/security-alerts').status_code==404
        overview=security.get('/responder/security-alerts')
        assert 'Case Access' in overview.text
        alert=re.search(r'href="([^"]+\?id=\d+)"',overview.text)[1]
        details=security.get(alert)
        action=re.search(r'action="([^"]+/security-alerts/\d+)"',details.text)[1]
        assert security.post(action,data=dict(csrf=csrf(details),target='ACKNOWLEDGED',reason='Reviewed')).status_code==303
        assert 'This session' in responder.get('/responder/sessions').text
        assert responder.post('/responder/mfa/replace',data=dict(csrf=csrf(page),password=desk[1],code=codes[0])).status_code==303
        assert responder.get(desk_path).location=='/responder/login'
        stale=Identity(tmp_path/'server.sqlite','fixture-secret')
        stale.mfa=MFA(stale,b'm'*32)
        assert stale.user(old_sid) is None

    lock=Evidence(Cases(identity),{'v1':b'e'*32},'v1')
    with identity.connect() as db:
        stored=dict(db.execute('SELECT * FROM cyber_evidence').fetchone())
        assert raw not in stored['ciphertext']
    assert lock.verify(stored)==raw
    restored_path=tmp_path/'restored.sqlite'
    from safesignal.database import connection
    with identity.connect() as original, connection(restored_path) as restored:
        original.backup(restored)
    restored_identity=Identity(restored_path,'fixture-secret')
    with restored_identity.connect() as restored:
        assert restored.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    restored_locker=Evidence(Cases(restored_identity),{'v1':b'e'*32},'v1')
    with restored_identity.connect() as restored:
        copied=restored.execute('SELECT * FROM cyber_evidence').fetchone()
        assert restored_locker.verify(copied)==raw
    for changed in (dict(stored,name='other.txt'),dict(stored,ciphertext=bytes([stored['ciphertext'][0]^1])+stored['ciphertext'][1:])):
        with pytest.raises(InvalidTag):
            lock.verify(changed)
    with pytest.raises(RuntimeError):
        Evidence(Cases(identity),{},'v1').verify(stored)


@pytest.mark.parametrize('name,raw', [('fake.png',b'hello'),('bad.exe',b'hello'),('bad.eml',b'hello'),('bad.txt',b'\x00')])
def test_evidence_format_validation(name,raw):
    with pytest.raises(ValueError):
        validate_file(name,raw)


def test_monitor_expiry_and_aggregation(tmp_path):
    clock=[1000]
    identity=Identity(tmp_path/'db','secret',clock=lambda:clock[0])
    monitor=Monitor(identity,{'CASE_ACCESS':(2,10,40)})
    monitor.event('CASE_ACCESS','student1')
    clock[0]+=11
    monitor.event('CASE_ACCESS','student1')
    with identity.connect() as db:
        assert db.execute('SELECT count(*) FROM security_alerts').fetchone()[0]==0
    monitor.event('CASE_ACCESS','student1')
    monitor.event('CASE_ACCESS','student1')
    with identity.connect() as db:
        assert [r[0] for r in db.execute('SELECT observations FROM security_alerts')]==[3]

def test_mfa_only_accepts_each_factor_once_under_concurrency(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    clock=[60_000]
    identity=Identity(tmp_path/'mfa.sqlite','secret',clock=lambda:clock[0])
    account=enroll(identity,1,'Cyber Response')
    mfa=identity.mfa=MFA(identity,b'm'*32)
    token=identity.login(*account,'responder',pending=True)
    row=mfa.pending(token)
    seed=mfa.open(row['user_id'],row['secret'])
    code=lambda:pyotp.TOTP(seed).at(clock[0])
    _,recovery=mfa.finish(token,code())
    assert len(recovery)==8
    assert mfa.finish(token,code())==(None,[])
    stale=identity.login(*account,'responder',pending=True)
    clock[0]+=301
    assert mfa.finish(stale,code())==(None,[])
    token=identity.login(*account,'responder',pending=True)
    def race(value):
        barrier=Barrier(2)
        def attempt(_):
            barrier.wait(timeout=3)
            return bool(mfa.finish(token,value)[0])
        with ThreadPoolExecutor(2) as pool:
            return sorted(pool.map(attempt,range(2)))
    assert race(code())==[False,True]
    token=identity.login(*account,'responder',pending=True)
    assert mfa.finish(token,code())==(None,[])
    assert race(recovery[0])==[False,True]
    token=identity.login(*account,'responder',pending=True)
    assert mfa.finish(token,recovery[0])==(None,[])


def test_upload_limits_and_atomic_failure(tmp_path):
    from werkzeug.datastructures import FileStorage
    from safesignal.server_store import Store
    Store(tmp_path/'db')
    identity=Identity(tmp_path/'db','secret')
    cases=Cases(identity)
    aid=str(uuid4())
    user=dict(id='synthetic-user',role='student')
    cases.create(user['id'],aid,dict(title='Synthetic title',category='PHISHING'))
    locker=Evidence(cases,{'v1':b'e'*32},'v1',max_size=3,max_files=1)
    def put(raw):
        return locker.upload(user,aid,FileStorage(io.BytesIO(raw),filename='demo.log'))
    with pytest.raises(ValueError,match='size'):
        put(b'1234')
    with identity.connect() as db:
        db.execute("CREATE TRIGGER synthetic_write_failure BEFORE INSERT ON cyber_evidence BEGIN SELECT RAISE(ABORT,'fixture'); END")
    import sqlite3
    with pytest.raises(sqlite3.IntegrityError):
        put(b'123')
    with identity.connect() as db:
        assert locker.list(db,aid)==[]
        db.execute('DROP TRIGGER synthetic_write_failure')
    first=put(b'123')
    with pytest.raises(ValueError,match='quota'):
        put(b'123')
    assert locker.download(user,aid,first)[1]==b'123'

def test_cyber_migration_preserves_legacy_case_and_queued_payload(tmp_path):
    from safesignal.models import new_alert
    from safesignal.sender_store import Outbox
    from safesignal.server_store import Store
    path=tmp_path/'server.sqlite'
    identity=Identity(path,'secret')
    store=Store(path)
    box=Outbox(tmp_path/'outbox.sqlite')
    student=enroll(identity,1)
    sid=identity.login(*student,'student')
    user=identity.user(sid)
    legacy=new_alert('MEDIUM','Historical physical report',category='FIRE')
    queued=new_alert('HIGH','Previously queued physical report',category='MEDICAL')
    store.submit(legacy,user['id'])
    identity.accept(user['id'],queued)
    assert len(store.audit(legacy['alert_id']))==1
    cases=Cases(identity)
    identity.mfa=MFA(identity,b'm'*32)
    Evidence(cases,{},'v1')
    Monitor(identity)
    identity.reconcile(box)
    assert box.rows(user['id'])[0]['alert']==queued
    assert store.status(legacy['alert_id'])['category']=='FIRE'
    assert len(store.audit(legacy['alert_id']))==1
    assert cases.list(user,0)==[]
    assert cases.read(user,legacy['alert_id'])==(None,[])
    assert identity.user(sid)['id']==user['id']
