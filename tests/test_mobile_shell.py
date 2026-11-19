from safesignal.identity import Identity
from safesignal.sender_store import Outbox
from safesignal.web import create_app


def test_mobile_navigation_and_real_private_home(tmp_path):
    mail=[]
    auth=Identity(tmp_path/'server.sqlite','private-key',mail=lambda *args:mail.append(args))
    email='0000000001@mail.jiit.ac.in'
    auth.register(email,'synthetic-password-123');auth.consume(mail[-1][2],'VERIFY')
    sid=auth.login(email,'synthetic-password-123','student')
    config=dict(session_secret='test',allowed_hosts=('localhost',))
    def offline(*args): raise ConnectionError()
    client=create_app('sender',config,offline,Outbox(tmp_path/'box.sqlite'),identity=auth).test_client()
    with client.session_transaction() as s: s.update(sid=sid,role='sender',csrf='test-csrf')
    page=client.get('/')
    assert page.status_code==200
    assert 'Mobile navigation' in page.text and 'My Walks' in page.text
    assert 'Report an incident' in page.text and 'My incidents' in page.text
    assert 'Total reports' not in page.text
    assert 'Backend unavailable' in page.text
    assert "frame-ancestors 'none'" in page.headers['Content-Security-Policy']
    assert page.headers['Cache-Control']=='no-store'
    assert 'not available' in client.get('/walks').text
    assert email in client.get('/profile').text
    assert 'Sign out' in client.get('/profile').text
    assert client.post('/profile',data={}).status_code==400
    assert client.get('/?view=incidents').status_code==200
    assert client.get('/?view=network').status_code==200
    assert client.get('/evidence').status_code==403


def test_public_account_forms_and_signup_confirmation(tmp_path):
    auth=Identity(tmp_path/'server.sqlite','secret',mail=lambda *args:None)
    config=dict(session_secret='test',allowed_hosts=('localhost',))
    client=create_app('sender',config,lambda *args:None,Outbox(tmp_path/'outbox.sqlite'),identity=auth).test_client()
    for path in ('login','register','verify','recovery','reset-password'):
        reply=client.get('/'+path)
        assert reply.status_code==200
        assert 'viewport-fit=cover' in reply.text and 'mobile.css' in reply.text
    with client.session_transaction() as s: csrf=s['csrf']
    reply=client.post('/register',data=dict(csrf=csrf,email='0000000001@mail.jiit.ac.in',password='synthetic-password-123',confirm_password='different-password'))
    assert 'Passwords must match' in reply.text
    with auth.connect() as db: assert db.execute('SELECT count(*) FROM users').fetchone()[0]==0
