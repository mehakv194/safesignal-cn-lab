import json

import pytest

from safesignal.trust_lab import TrustLab
from safesignal.web import create_app
from test_identity import accounts


@pytest.mark.parametrize('scenario,result',[('genuine','VERIFIED'),('modified','REJECTED'),('cross_user','DENIED'),('role','DENIED'),('burst','DETECTED')])
def test_five_actual_local_outcomes(accounts,scenario,result):
    auth,mail,clock,student=accounts
    lab=TrustLab(auth)
    outcome=lab.run(scenario,'synthetic-maintainer')
    assert outcome['result']==result
    public=json.dumps(outcome)+json.dumps(lab.events())
    assert lab.key.hex() not in public and 'password_hash' not in public
    assert '@mail.jiit.ac.in' not in public and 'token' not in public
    assert lab.events()[0]['event']=='TRUST_'+scenario.upper()


def test_real_login_failure_detector_ignores_normal_use(accounts):
    auth,mail,clock,student=accounts
    email,sid,user=student(1)
    assert auth.login(email,'correct-password-123','student','test-ip')
    for _ in range(4): assert auth.login(email,'wrong','student','test-ip') is None
    with auth.connect() as db: assert not db.execute("SELECT 1 FROM security_events WHERE event='LOGIN_BURST'").fetchone()
    assert auth.login(email,'wrong','student','test-ip') is None
    for _ in range(3): auth.login(email,'wrong','student','test-ip')
    with auth.connect() as db:
        assert db.execute("SELECT count(*) FROM security_events WHERE event='LOGIN_BURST'").fetchone()[0]==1
        assert db.execute('SELECT count(*) FROM login_failures').fetchone()[0]<=6
    clock[0]+=61
    auth.login(email,'wrong','student','test-ip')
    with auth.connect() as db: assert db.execute('SELECT count(*) FROM login_failures').fetchone()[0]==1


def test_local_lab_role_csrf_and_remote_denial(accounts):
    auth,mail,clock,student=accounts
    email,sid,user=student(1);auth.provision(email,'Campus Safety')
    sid=auth.login(email,'correct-password-123','responder')
    app=create_app('responder',dict(session_secret='test',trust_lab=True),lambda *args:None,identity=auth)
    c=app.test_client()
    assert c.get('/trust-lab').status_code==302
    with c.session_transaction() as s:s.update(sid=sid,role='responder',csrf='csrf')
    assert c.get('/trust-lab').status_code==200
    assert c.post('/trust-lab/run',data={'scenario':'genuine'}).status_code==400
    assert c.get('/trust-lab',environ_overrides={'REMOTE_ADDR':'203.0.113.20'}).status_code==404
    assert c.post('/trust-lab/run',data=dict(csrf='csrf',scenario='modified')).status_code==302
    assert 'REJECTED' in c.get('/trust-lab').text
    assert c.post('/trust-lab/run',data=dict(csrf='csrf',scenario='unknown')).status_code==400


def test_public_mode_denies_direct_lab_and_fault_override(accounts,tmp_path):
    import re
    from safesignal.hosted import hosted_runtime
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    auth,mail,clock,student=accounts
    # Use real-time session for actual runtime, not this fixture's injectable clock.
    from safesignal.identity import Identity
    directory=tmp_path/'public';directory.mkdir()
    realtime=Identity(directory/'server.sqlite','key',mail=lambda *args:mail.append(args))
    email='0000000001@mail.jiit.ac.in'
    realtime.register(email,'synthetic-password-123');realtime.consume(mail[-1][2],'VERIFY')
    config=dict(identity=True,trust_lab=True,hosted=True,session_secret='key',sender_token='sender',responder_token='responder',allowed_hosts=('campus.example',))
    with hosted_runtime(config,directory,True) as app:
        c=Client(app,Response)
        for path in ('/sender/trust-lab','/responder/trust-lab','/responder/trust-lab?enable=1'):
            assert c.get(path,base_url='https://campus.example').status_code==404
        assert c.post('/responder/trust-lab/run',base_url='https://campus.example',data={'scenario':'genuine'}).status_code==404
        page=c.get('/sender/login',base_url='https://campus.example')
        csrf=re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
        c.post('/sender/login',base_url='https://campus.example',data=dict(csrf=csrf,email=email,password='synthetic-password-123'))
        network=c.get('/sender/?view=network',base_url='https://campus.example')
        assert 'Fault injection is disabled' in network.text
        assert 'Local Trust Lab' not in network.text
        csrf=re.search(r'name="csrf" value="([^"]+)"',network.text).group(1)
        assert c.post('/sender/simulation',base_url='https://campus.example',data=dict(csrf=csrf,preset='disconnect')).status_code==403


def test_fixture_allowlist_and_fake_signature(accounts):
    auth,*_=accounts
    lab=TrustLab(auth)
    assert not lab.verify(dict(message='public edit'), '0'*64)
    with pytest.raises(ValueError): lab.run('external-attack','synthetic')


def test_owner_can_keep_registration_disabled_even_with_mail(monkeypatch,tmp_path):
    from contextlib import contextmanager
    import safesignal.hosted as hosted
    import waitress
    for key,value in dict(SAFESIGNAL_SENDER_TOKEN='s'*32,SAFESIGNAL_RESPONDER_TOKEN='r'*32,
                          SAFESIGNAL_SESSION_SECRET='k'*32,SAFESIGNAL_ALLOWED_HOSTS='campus.example',
                          SAFESIGNAL_DATA_DIR=str(tmp_path),SAFESIGNAL_REGISTRATION_ENABLED='0').items():
        monkeypatch.setenv(key,value)
    def mail_must_stay_off(): raise AssertionError('Owner disabled registration')
    monkeypatch.setattr(hosted,'configured_mail',mail_must_stay_off)
    @contextmanager
    def capture(config,*args):
        assert config['mail'] is None
        yield lambda *args:None
    monkeypatch.setattr(hosted,'hosted_runtime',capture)
    monkeypatch.setattr(waitress,'serve',lambda *args,**kwargs:None)
    hosted.main()
