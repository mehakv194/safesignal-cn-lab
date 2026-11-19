import json
import re
import struct

from argon2 import PasswordHasher
from werkzeug.test import Client
from werkzeug.wrappers import Response

from safesignal.hosted import hosted_runtime
from safesignal.identity import Identity


def test_public_install_assets_and_private_pages(tmp_path):
    config = dict(identity=True, hosted=True, session_secret='fixture-key',
                  sender_token='fixture-sender', responder_token='fixture-responder',
                  allowed_hosts=('campus.example',), mail=None)
    with hosted_runtime(config, tmp_path) as app:
        client = Client(app, Response)
        origin = 'https://campus.example'
        manifest_path = '/static/safesignal.webmanifest'
        for page in ('/', '/sender/login', '/responder/login'):
            response = client.get(page, base_url=origin)
            assert f'rel="manifest" href="{manifest_path}"' in response.text
            assert 'no-store' in response.headers['Cache-Control']
            if page != '/':
                assert '<a class="button secondary" href="/">Main page</a>' in response.text
        response = client.get(manifest_path, base_url=origin)
        assert response.mimetype == 'application/manifest+json'
        manifest = json.loads(response.data)
        assert manifest['start_url'] == manifest['scope'] == '/'
        assert manifest['display'] == 'standalone'
        assert {icon['sizes'] for icon in manifest['icons']} == {'192x192', '512x512'}
        for icon in manifest['icons']:
            asset = client.get('/static/' + icon['src'], base_url=origin)
            assert asset.mimetype == 'image/png'
            assert asset.data.startswith(b'\x89PNG\r\n\x1a\n')
            assert struct.unpack('!II', asset.data[16:24]) == tuple(map(int, icon['sizes'].split('x')))
        assert client.get('/sender/walks', base_url=origin).status_code == 302


def test_hosted_demo_passwords_are_role_bound_without_verification(tmp_path):
    prior_db = tmp_path / 'server.sqlite'
    previous = Identity(prior_db, 'fixture-key')
    student = '0000000001@mail.jiit.ac.in'
    responder = '0000000002@mail.jiit.ac.in'
    passwords = ('synthetic-student-pass', 'synthetic-responder-pass')
    hasher = PasswordHasher()
    hashes = dict(zip(('student', 'responder'), map(hasher.hash, passwords)))
    previous.seed_demo_accounts(dict(student=hashes['responder'], responder=hashes['student']))
    config = dict(identity=True, session_secret='fixture-key', sender_token='fixture-sender',
                  responder_token='fixture-responder', allowed_hosts=('campus.example',),
                  demo_accounts=hashes)
    origin = dict(base_url='https://campus.example')
    with hosted_runtime(config, tmp_path) as app:
        client = Client(app, Response)
        assert 'assigned student or responder demo' in client.get('/', **origin).text
        for role, email, password, other_email, other_password in (
            ('sender', student, passwords[0], responder, passwords[1]),
            ('responder', responder, passwords[1], student, passwords[0]),
        ):
            path = f'/{role}/login'
            page = client.get(path, **origin)
            assert 'Demo email' in page.text
            assert 'Verify inbox' not in page.text
            csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
            for action in ('register', 'verify', 'activate-demo', 'recovery', 'reset-password'):
                assert client.get(f'/{role}/{action}', **origin).status_code == 404
                assert client.post(f'/{role}/{action}', data={'csrf': csrf}, **origin).status_code == 404
            assert client.post(path, data=dict(email=other_email, password=other_password, csrf=csrf), **origin).status_code == 200
            assert client.get(f'/{role}/', **origin).location == path
            assert client.post(path, data=dict(email=email, password=password, csrf=csrf), **origin).location == f'/{role}/'
            dashboard = client.get(f'/{role}/', **origin)
            assert dashboard.status_code == 200
            assert '<a class="button secondary" href="/">Main page</a>' in dashboard.text
            assert 'Change password' not in client.get(f'/{role}/profile', **origin).text
    assert previous.login(student, passwords[1], 'student')
