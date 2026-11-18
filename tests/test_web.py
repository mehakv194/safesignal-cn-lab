import re

from safesignal.models import new_alert
from safesignal.sender_store import Outbox
from safesignal.web import create_app
from test_transport import lab


def csrf(client):
    with client.session_transaction() as s:
        return s['csrf']


def login(client, token):
    client.get('/login')
    return client.post('/login', data={'csrf': csrf(client), 'token': token})


def test_web_auth_csrf_and_escaping(lab, tmp_path):
    config = dict(session_secret='test-session-secret', sender_token='test-sender', responder_token='test-responder')
    box = Outbox(tmp_path / 'outbox.sqlite')
    sender = create_app('sender', config, lab[2], box).test_client()
    assert sender.get('/').status_code == 302
    assert sender.post('/submit', data={}).status_code == 400
    assert login(sender, 'wrong').status_code == 200
    assert login(sender, 'test-sender').status_code == 302
    assert sender.post('/submit', data={'csrf': csrf(sender), 'severity': 'LOW', 'description': '<script>TEST ONLY</script>'}).status_code == 302
    page = sender.get('/').get_data(as_text=True)
    assert '&lt;script&gt;TEST ONLY&lt;/script&gt;' in page
    assert 'test-sender' not in page
    assert sender.get('/', headers={'Host': 'evil.example'}).status_code == 400
    assert sender.post('/ack/anything', data={'csrf': csrf(sender)}).status_code == 403
    responder_call = lambda kind, payload=None: lab[2](kind, payload, 'test-responder')
    responder = create_app('responder', config, responder_call).test_client()
    assert login(responder, 'test-sender').status_code == 200
    assert responder.get('/').status_code == 302
    assert login(responder, 'test-responder').status_code == 302
    p = new_alert('HIGH', 'TEST ONLY: web acknowledgment')
    lab[2]('SUBMIT_ALERT', p)
    assert p['alert_id'] in responder.get('/').get_data(as_text=True)
    assert responder.post('/ack/' + p['alert_id'], data={'csrf': csrf(responder)}).status_code == 302
    assert lab[2]('GET_STATUS', {'alert_id': p['alert_id']})['code'] == 'RESPONDER_ACKNOWLEDGED'
