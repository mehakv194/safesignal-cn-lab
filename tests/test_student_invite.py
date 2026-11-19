import re

import pytest
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.test import Client
from werkzeug.wrappers import Response

from safesignal.identity import Identity, digest
from safesignal.sender_store import Outbox
from safesignal.web import create_app


def test_hosted_invite_requires_inbox_code_and_cannot_reset_account(tmp_path):
    auth = Identity(tmp_path / 'server.sqlite', 'fixture-secret', clock=lambda: 1000)
    email = '0000000001@mail.jiit.ac.in'
    code = 'a' * 43
    password = 'fresh-synthetic-password'
    invite = {'expires_at': 1001, 'commitment': digest(f'safesignal-invite-v1:{email}:{code}')}
    config = dict(session_secret='fixture-secret', hosted=True, student_invite=invite)
    app = create_app('sender', config, None, Outbox(tmp_path / 'queue.sqlite'), identity=auth)
    client = Client(DispatcherMiddleware(Response(status=404), {'/sender': app}))
    path = '/sender/activate-demo'
    https = {'base_url': 'https://localhost'}
    page = client.get(path, **https)
    assert page.status_code == 200
    csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
    form = dict(email=email, code=code, password=password, confirm_password=password, csrf=csrf, role='responder')
    assert client.post(path, data=dict(form, csrf='incorrect'), **https).status_code == 400
    assert 'Invalid or expired' in client.post(path, data=dict(form, email='0000000002@mail.jiit.ac.in'), **https).text
    assert 'Invalid or expired' in client.post(path, data=dict(form, code='b'*43), **https).text
    with pytest.raises(ValueError, match='expired'):
        auth.redeem_invite(email, code, password, dict(invite, expires_at=1000))
    assert client.post(path, data=form, **https).location == '/sender/login'
    assert 'already been used' in client.post(path, data=form, **https).text
    assert auth.login(email, password, 'student')
    assert not auth.login(email, password, 'responder')
    assert 'Registration unavailable' in client.get('/sender/register', **https).text
