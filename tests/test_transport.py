import socket
import ssl
import struct
import threading

import pytest

from safesignal import protocol
from safesignal.models import new_alert
from safesignal.server import AlertServer, request
from safesignal.server_store import Store
from safesignal.tls import create_certificate, server_context, client_context


@pytest.fixture
def lab(tmp_path):
    cert = tmp_path / 'certs'
    create_certificate(cert)
    store = Store(tmp_path / 'server.sqlite')
    server = AlertServer(('127.0.0.1', 0), server_context(cert), store, 'test-sender', 'test-responder')
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    def call(kind, payload=None, token='test-sender'):
        return request(server.server_address, client_context(cert), token, kind, payload)
    yield server, store, call, cert
    server.shutdown()
    server.server_close()
    thread.join()


def test_submit_dedup_conflict_and_ack(lab):
    server, store, call, _ = lab
    p = new_alert('HIGH', 'TEST ONLY: synthetic alert')
    assert call('SUBMIT_ALERT', p)['code'] == 'SERVER_RECEIVED'
    assert call('SUBMIT_ALERT', p)['duplicate'] is True
    assert call('SUBMIT_ALERT', dict(p, description='TEST ONLY: changed content'))['code'] == 'ID_CONFLICT'
    for _ in range(2):
        assert call('ACK_ALERT', {'alert_id': p['alert_id']}, 'test-responder')['code'] == 'RESPONDER_ACKNOWLEDGED'
    assert call('GET_STATUS', {'alert_id': p['alert_id']})['code'] == 'RESPONDER_ACKNOWLEDGED'
    with store.connect() as db:
        assert db.execute('SELECT count(*) FROM alerts').fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM audit WHERE event='RESPONDER_ACKNOWLEDGED'").fetchone()[0] == 1


@pytest.mark.parametrize('kind,token', [('SUBMIT_ALERT', 'bad'), ('LIST_ALERTS', 'test-sender'), ('ACK_ALERT', 'bad')])
def test_role_auth(lab, kind, token):
    assert lab[2](kind, token=token)['code'] == 'UNAUTHORIZED'
    assert lab[1].listing() == []


def test_validation_and_listener_survives(lab):
    server, _, call, cert = lab
    assert call('SUBMIT_ALERT', {'description': 'broken'})['code'] == 'INVALID_REQUEST'
    for frame in (struct.pack('!I', 16385), struct.pack('!I', 0), struct.pack('!I', 3) + b'xxx', struct.pack('!I', 10) + b'{}'):
        with socket.create_connection(server.server_address) as raw:
            with client_context(cert).wrap_socket(raw, server_hostname='localhost') as sock:
                sock.sendall(frame)
    assert call('HEALTH')['code'] == 'HEALTHY'


def test_wrong_certificate(lab, tmp_path):
    create_certificate(tmp_path / 'other')
    with pytest.raises(ssl.SSLCertVerificationError):
        request(lab[0].server_address, client_context(tmp_path / 'other'), 'test-sender', 'HEALTH')


def test_fragmented_frame():
    class Fragmented:
        data = bytearray(struct.pack('!I', 8) + b'{"x": 1}')
        def recv(self, n):
            value = self.data[:1]
            del self.data[:1]
            return value
    assert protocol.receive(Fragmented()) == {'x': 1}
