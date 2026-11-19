import re
import time

from argon2 import PasswordHasher
from werkzeug.test import Client
from werkzeug.wrappers import Response

from safesignal.hosted import hosted_runtime


def csrf(response):
    return re.search(r'name="csrf" value="([^"]+)"',response.get_data(as_text=True)).group(1)


def test_one_origin_dashboards_and_persistence(tmp_path):
    config=dict(sender_token='s'*32,responder_token='r'*32,session_secret='k'*32,
                allowed_hosts=('campus.example',))
    with hosted_runtime(config,tmp_path,True) as app:
        client=Client(app,Response)
        assert client.get('/',base_url='https://campus.example').status_code==200
        assert client.get('/healthz',base_url='https://campus.example').json['ready'] is True
        assert client.get('/sender/login',base_url='https://evil.example').status_code==400
        assert client.get('/sender/login',base_url='http://campus.example').status_code==400
        page=client.get('/sender/login',base_url='https://campus.example')
        assert 'Secure' in page.headers['Set-Cookie'] and 'Path=/sender' in page.headers['Set-Cookie']
        login=client.post('/sender/login',base_url='https://campus.example',data={'csrf':csrf(page),'token':'s'*32})
        assert login.location=='/sender/'
        home=client.get('/sender/',base_url='https://campus.example')
        assert '/sender/submit' in home.get_data(as_text=True)
        assert '/responder/' in home.get_data(as_text=True)
        assert client.post('/sender/examples',base_url='https://campus.example',data={}).status_code==400
        assert client.post('/sender/examples',base_url='https://campus.example',data={'csrf':csrf(home)}).status_code==302
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            page=client.get('/sender/',base_url='https://campus.example')
            if 'Queued ·' not in page.get_data(as_text=True) and 'TEST ONLY: first-aid' in page.get_data(as_text=True):
                break
            time.sleep(.1)
        assert 'TEST ONLY: first-aid' in page.get_data(as_text=True)

        responder_login=client.get('/responder/login',base_url='https://campus.example')
        assert client.post('/responder/login',base_url='https://campus.example',data={'csrf':csrf(responder_login),'token':'r'*32}).status_code==302
        assert client.get('/responder/',base_url='https://campus.example').status_code==200
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            network=client.get('/sender/?view=network',base_url='https://campus.example')
            if 'Server receipt confirmed' in network.text:
                break
            time.sleep(.1)
        assert network.status_code==200 and 'Live Network Lab' in network.text
        assert 'Send test report' not in network.text and 'Temporary sender disconnect' not in network.text
        assert 'Server receipt confirmed' in network.text
        tracked = re.search(r'<code>([a-f0-9-]{36})</code>', network.text)[1]
        desk = client.get('/responder/?view=network',base_url='https://campus.example')
        assert desk.status_code==200 and 'Latest server receipts' in desk.text
        assert f'<code>{tracked}</code>' in desk.text
        assert client.post('/sender/network-demo/report',base_url='https://campus.example',
                           data={'csrf':csrf(home)}).status_code==404
        assert client.post('/sender/simulation',base_url='https://campus.example',
                           data={'csrf':csrf(home),'preset':'disconnect'}).status_code==403
        assert client.get('/sender/evidence',base_url='https://campus.example').status_code==200
    # A full runtime restart keeps both persistent SQLite databases.
    with hosted_runtime(config,tmp_path) as app:
        client=Client(app,Response)
        page=client.get('/sender/login',base_url='https://campus.example')
        client.post('/sender/login',base_url='https://campus.example',data={'csrf':csrf(page),'token':'s'*32})
        page=client.get('/sender/',base_url='https://campus.example')
        assert 'TEST ONLY: first-aid' in page.get_data(as_text=True)


def test_free_plan_configuration_and_retention_notice(tmp_path):
    from pathlib import Path
    from safesignal.sender_store import Outbox
    from safesignal.web import create_app
    from test_web import login
    blueprint=(Path(__file__).resolve().parents[1]/'render.yaml').read_text()
    settings=[line.strip() for line in blueprint.splitlines() if line.strip() and not line.lstrip().startswith('#')]
    assert [line for line in settings if line.startswith('plan:')]==['plan: free']
    assert 'disk:' not in settings
    config=dict(sender_token='sender',responder_token='responder',session_secret='test-only',ephemeral_storage=True)
    client=create_app('sender',config,lambda *args:dict(status='OK'),Outbox(tmp_path/'box.sqlite')).test_client()
    login(client,'sender')
    assert 'reports can reset when the host restarts' in client.get('/').get_data(as_text=True)


def test_local_transfer_lab_shows_retry_then_same_responder_receipt(tmp_path):
    password = 'synthetic-password-123'
    hashed = PasswordHasher().hash(password)
    config = dict(identity=True, hosted=False, session_secret='fixture-key', sender_token='fixture-sender',
                  responder_token='fixture-responder', mail=None,
                  demo_accounts={'student': hashed, 'responder': hashed})
    with hosted_runtime(config, tmp_path, enable_faults=True) as app:
        client = Client(app, Response)
        for index, prefix in enumerate(('sender', 'responder'), start=1):
            path = f'/{prefix}/login'
            form = dict(email=f'{index:010}@mail.jiit.ac.in', password=password, csrf=csrf(client.get(path)))
            assert client.post(path, data=form).location == f'/{prefix}/'

        sender_lab = '/sender/?view=network'
        responder_lab = '/responder/?view=network'
        assert 'Live Network Lab' in client.get(sender_lab).text
        desk_csrf = csrf(client.get('/responder/profile'))
        assert client.post('/responder/network-demo/report', data={'csrf': desk_csrf}).status_code == 404
        assert client.post('/responder/simulation', data={'csrf': desk_csrf, 'preset': 'disconnect'}).status_code == 403
        token = csrf(client.get(sender_lab))

        def set_link(preset):
            assert client.post('/sender/simulation', data={'csrf': token, 'preset': preset}).location == sender_lab

        def submit():
            assert client.post('/sender/network-demo/report', data={'csrf': token}).location == sender_lab
            return re.search(r'<code>([a-f0-9-]{36})</code>', client.get(sender_lab).text)[1]

        def wait_for(path, content):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                page = client.get(path).text
                if content in page:
                    return page
                time.sleep(.1)
            raise AssertionError(f'{content!r} did not appear on {path}')

        set_link('disconnect')
        incident = submit()
        page = wait_for(sender_lab, 'No successful receipt · retry scheduled')
        assert incident in page and 'Awaiting server receipt' in page
        assert incident not in client.get(responder_lab).text
        set_link('normal')
        assert incident in wait_for(sender_lab, 'Server receipt confirmed')
        assert client.get(responder_lab).text.count(f'<code>{incident}</code>') == 1
        update = dict(csrf=desk_csrf, action='CLAIM', team='Medical Team')
        assert client.post(f'/responder/incident/{incident}/update?view=network', data=update).location == responder_lab
        wait_for(sender_lab, 'Responder acknowledged the incident')

        set_link('ack_lost')
        receipt_lost = submit()
        page = wait_for(sender_lab, 'Repeated incident ID · original receipt reused')
        assert receipt_lost in page and 'No successful receipt · retry scheduled' in page
        assert client.get(responder_lab).text.count(f'<code>{receipt_lost}</code>') == 1
