import json
import sqlite3
import threading
from uuid import uuid4

import pytest

from safesignal.identity import Identity, email_address
from safesignal.models import new_alert
from safesignal.server import AlertServer, request
from safesignal.server_store import Store
from safesignal.sender_store import Outbox
from safesignal.sender_worker import Worker
from safesignal.tls import create_certificate, client_context, server_context
from safesignal.web import create_app


@pytest.fixture
def accounts(tmp_path):
    mail=[]
    clock=[100000.0]
    auth=Identity(tmp_path/'server.sqlite','private-test-key',clock=lambda:clock[0],mail=lambda *args:mail.append(args))
    def student(number):
        email=f'{number:010d}@mail.jiit.ac.in'
        auth.register(email,'correct-password-123')
        token=mail[-1][2]
        auth.consume(token,'VERIFY')
        sid=auth.login(email,'correct-password-123','student')
        return email,sid,auth.user(sid)
    return auth,mail,clock,student


@pytest.mark.parametrize('value',['123456789@mail.jiit.ac.in','12345678901@mail.jiit.ac.in','abcdefghij@mail.jiit.ac.in',
    '１２３４５６７８９０@mail.jiit.ac.in','1234567890+alias@mail.jiit.ac.in','1234567890@jiit.ac.in','12345 67890@mail.jiit.ac.in'])
def test_exact_email_rejections(value):
    with pytest.raises(ValueError): email_address(value)


def test_verification_reset_sessions_and_privilege(accounts):
    auth,mail,clock,student=accounts
    email='2408030009@mail.jiit.ac.in'
    assert email_address(' 2408030009@MAIL.JIIT.AC.IN ')==email
    auth.register(email,'correct-password-123')
    challenge=mail[-1][2]
    assert auth.login(email,'correct-password-123','student') is None
    auth.consume(challenge,'VERIFY')
    with pytest.raises(ValueError): auth.consume(challenge,'VERIFY')
    assert auth.login(email,'wrong','student') is None
    assert auth.login(email,'correct-password-123','responder') is None
    sid=auth.login(email,'correct-password-123','student')
    assert auth.user(sid)['role']=='student'
    with auth.connect() as db:
        raw=db.execute('SELECT password_hash FROM users').fetchone()[0]
        assert raw.startswith('$argon2id$') and 'correct-password' not in raw
        assert challenge not in str(list(db.execute('SELECT * FROM challenges')))
    auth.challenge(email,'RESET')
    reset=mail[-1][2]
    auth.consume(reset,'RESET','replacement-password-123')
    assert auth.user(sid) is None
    with pytest.raises(ValueError): auth.consume(reset,'RESET','replacement-password-123')
    sid=auth.login(email,'replacement-password-123','student')
    clock[0]+=1801
    assert auth.user(sid) is None
    sid=auth.login(email,'replacement-password-123','student')
    auth.provision(email,'Medical Team')
    assert auth.user(sid) is None
    assert auth.login(email,'replacement-password-123','student') is None
    sid=auth.login(email,'replacement-password-123','responder')
    auth.change_password(sid,'replacement-password-123','third-password-123')
    assert auth.user(sid) is None


def test_expiry_throttle_and_fail_closed(accounts,tmp_path):
    auth,mail,clock,student=accounts
    auth.register('1234567890@mail.jiit.ac.in','correct-password-123')
    challenge=mail[-1][2]
    clock[0]+=901
    with pytest.raises(ValueError): auth.consume(challenge,'VERIFY')
    for _ in range(8): assert auth.limit('login','synthetic','local')
    assert not auth.limit('login','synthetic','local')
    assert auth.limit('login','other','local')
    off=Identity(tmp_path/'off.sqlite','secret')
    with pytest.raises(ValueError): off.register('1234567890@mail.jiit.ac.in','correct-password-123')
    with off.connect() as db: assert db.execute('SELECT count(*) FROM users').fetchone()[0]==0


def test_private_socket_queue_legacy_and_scope(accounts,tmp_path):
    auth,mail,clock,student=accounts
    a,sa,ua=student(1)
    b,sb,ub=student(2)
    r,sr,ur=student(3)
    auth.provision(r,'Medical Team')
    sr=auth.login(r,'correct-password-123','responder')
    cert=tmp_path/'certs';create_certificate(cert)
    store=Store(auth.path)
    old=new_alert('LOW','TEST ONLY: legacy preserved')
    store.submit(old)
    with store.connect() as db: before=db.execute('SELECT payload,payload_hash FROM alerts').fetchone()
    Store(auth.path)
    with store.connect() as db: assert tuple(before)==tuple(db.execute('SELECT payload,payload_hash FROM alerts').fetchone())
    with AlertServer(('127.0.0.1',0),server_context(cert),store,'sender','responder',identity=auth) as server:
        t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
        def call(kind,payload=None,sid=sa,role='sender',intent=None):
            return request(server.server_address,client_context(cert),role,kind,payload,auth,dict(intent=intent) if intent else dict(sid=sid))
        p=new_alert('HIGH','TEST ONLY: private medical concern',category='MEDICAL')
        auth.accept(ua['id'],p)
        box=Outbox(tmp_path/'outbox.sqlite')
        # Intent survives an interruption before outbox insertion and is reconciled idempotently.
        auth.reconcile(box);auth.reconcile(box)
        assert len(box.rows())==1
        def worker_call(kind,payload): return call(kind,payload,intent=p['alert_id'])
        worker=Worker(box,worker_call,auth);worker.tick()
        assert box.rows()[0]['status']=='SERVER_RECEIVED'
        assert call('SUBMIT_ALERT',p,intent=p['alert_id'])['duplicate']
        assert call('GET_STATUS',{'alert_id':p['alert_id']},sid=sb)['code']=='NOT_FOUND'
        assert call('GET_AUDIT',{'alert_id':p['alert_id']},sid=sb)['code']=='NOT_FOUND'
        assert call('SUBMIT_ALERT',p,sid=sb)['code']=='UNAUTHORIZED'
        assert call('GET_STATUS',{'alert_id':old['alert_id']},sid=sr,role='responder')['code']=='NOT_FOUND'
        assert request(server.server_address,client_context(cert),'sender','GET_STATUS',{'alert_id':p['alert_id']})['status']=='ERROR'
        assert call('UPDATE_INCIDENT',dict(alert_id=p['alert_id'],action='CLAIM',team='Campus Safety'),sid=sr,role='responder')['code']=='UNAUTHORIZED'
        assert call('UPDATE_INCIDENT',dict(alert_id=p['alert_id'],action='CLAIM',team='Medical Team'),sid=sr,role='responder')['status']=='OK'
        assert call('DASHBOARD',sid=sr,role='responder')['total']==1
        # Queued submission ownership is durable after logout; human access is revoked.
        auth.logout(sa)
        assert call('GET_STATUS',{'alert_id':p['alert_id']})['status']=='ERROR'
        assert call('GET_STATUS',{'alert_id':p['alert_id']},intent=p['alert_id'])['status']=='OK'
        server.shutdown();t.join()


def test_command_bound_assertion_tamper_and_expiry(accounts):
    auth,mail,clock,student=accounts
    _,sid,_=student(1)
    req=dict(version=1,type='GET_STATUS',request_id=str(uuid4()),token='sender',payload={'alert_id':str(uuid4())})
    req['principal']=auth.sign(req,dict(sid=sid))
    assert auth.principal(req)['role']=='student'
    changed=dict(req,type='UPDATE_INCIDENT')
    with pytest.raises(ValueError): auth.principal(changed)
    clock[0]+=31
    with pytest.raises(ValueError): auth.principal(req)


def test_web_owner_separation_csrf_role_and_logout(accounts,tmp_path):
    auth,mail,clock,student=accounts
    _,sa,ua=student(1);_,sb,ub=student(2)
    box=Outbox(tmp_path/'box.sqlite')
    pa=new_alert('LOW','TEST ONLY: owner A private incident')
    pb=new_alert('LOW','TEST ONLY: owner B private incident')
    auth.accept(ua['id'],pa);auth.accept(ub['id'],pb);auth.reconcile(box)
    def offline(*args): raise ConnectionError()
    config=dict(session_secret='test',allowed_hosts=('localhost',),sender_token='sender',responder_token='responder')
    app=create_app('sender',config,offline,box,identity=auth)
    client=app.test_client()
    with client.session_transaction() as s: s.update(sid=sa,role='sender',csrf='csrf')
    page=client.get('/').get_data(as_text=True)
    assert pa['description'] in page and pb['description'] not in page
    assert client.get('/incident/'+pb['alert_id']).status_code==404
    assert client.post('/retry/'+pb['alert_id'],data={'csrf':'csrf'}).status_code==404
    assert client.post('/submit',data={}).status_code==400
    assert client.get('/evidence/results.csv').status_code==403
    assert client.post('/incident/'+pa['alert_id']+'/update',data={'csrf':'csrf','action':'CLAIM'}).status_code==403
    assert client.post('/logout',data={'csrf':'csrf'}).status_code==302
    assert auth.user(sa) is None
    # Replaying the old signed browser cookie cannot restore a revoked session.
    with client.session_transaction() as s: s.update(sid=sa,role='sender',csrf='csrf')
    assert client.get('/').status_code==302


def test_real_runtime_verified_signup_and_restore(tmp_path):
    import re
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    from safesignal.hosted import hosted_runtime
    mail=[]
    config=dict(identity=True,sender_token='s'*32,responder_token='r'*32,session_secret='k'*32,
                allowed_hosts=('campus.example',),mail=lambda *args:mail.append(args))
    # Existing legacy files are backed up before the first identity/schema change.
    original=Store(tmp_path/'server.sqlite')
    legacy=new_alert('LOW','TEST ONLY: old report survives migration')
    original.submit(legacy)
    box=Outbox(tmp_path/'outbox.sqlite');box.enqueue(legacy)
    with hosted_runtime(config,tmp_path) as app:
        c=Client(app,Response)
        def get(path): return c.get('/sender/'+path,base_url='https://campus.example')
        def post(path,fields):
            page=get(path)
            csrf=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
            return c.post('/sender/'+path,base_url='https://campus.example',data=dict(csrf=csrf,**fields))
        assert 'Access token' not in get('login').text
        email='2408030009@mail.jiit.ac.in'
        assert post('register',dict(email=email,password='correct-password-123',role='responder')).status_code==200
        assert post('login',dict(email=email,password='correct-password-123')).status_code==200
        assert 'Email verified' in post('verify',dict(challenge=mail[-1][2])).text
        assert post('login',dict(email=email,password='correct-password-123')).status_code==302
        assert 'old report survives migration' not in get('').text
        assert email in get('profile').text
    restored=tmp_path/'restored.sqlite'
    with sqlite3.connect(tmp_path/'pre-v2-backup/server.sqlite') as src,sqlite3.connect(restored) as dst:
        src.backup(dst)
    assert Store(restored).status(legacy['alert_id'])['description']==legacy['description']
    with sqlite3.connect(tmp_path/'server.sqlite') as db:
        assert db.execute('SELECT role FROM users').fetchone()[0]=='student'


def test_registration_csrf_and_unconfigured_mail(accounts,tmp_path):
    auth,mail,clock,student=accounts
    auth.mail=None
    config=dict(session_secret='key',allowed_hosts=('localhost',))
    c=create_app('sender',config,lambda *args:None,Outbox(tmp_path/'box.sqlite'),identity=auth).test_client()
    page=c.get('/register')
    assert 'Registration unavailable' in page.text
    assert c.post('/register',data={'email':'2408030009@mail.jiit.ac.in','password':'correct-password-123'}).status_code==400
