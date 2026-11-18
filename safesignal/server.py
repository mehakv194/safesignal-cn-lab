import hmac
import socket
import socketserver
import ssl
import threading
import time
from uuid import UUID, uuid4

from . import protocol


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(4)
        try:
            with self.server.context.wrap_socket(self.request, server_side=True) as sock:
                req = protocol.receive(sock)
                response = self.server.dispatch(req)
                if req.get('type') == 'SUBMIT_ALERT' and response.get('status') == 'OK' and self.server.faults:
                    preset = self.server.faults.preset()
                    if preset == 'ack_lost' and not response.get('duplicate'):
                        return  # Receipt suppressed only after the store transaction committed.
                    if preset == 'delay':
                        time.sleep(1.5)
                protocol.send(sock, response)
        except (OSError, EOFError, ValueError, TypeError):
            # Malformed peers must not kill the listener or expose request content.
            return


class AlertServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, address, context, store, sender_token, responder_token, faults=None):
        if not sender_token or not responder_token or sender_token == responder_token:
            raise ValueError('Distinct nonempty role tokens required')
        self.context, self.store = context, store
        self.faults = faults
        self.tokens = {'sender': sender_token, 'responder': responder_token}
        self.rate_lock = threading.Lock()
        self.rates = {}
        super().__init__(address, Handler)

    def dispatch(self, req):
        rid = req.get('request_id')
        try:
            UUID(rid)
            if req.get('version') != 1:
                raise ValueError()
            token = req.get('token')
            if not isinstance(token, str):
                token = ''
            role = next((r for r, t in self.tokens.items() if hmac.compare_digest(token.encode(), t.encode())), None)
            kind = req.get('type')
            required = {'SUBMIT_ALERT': 'sender', 'GET_STATUS': 'sender',
                        'LIST_ALERTS': 'responder', 'ACK_ALERT': 'responder',
                        'GET_AUDIT': 'responder', 'HEALTH': 'sender'}
            if role is None or required.get(kind) != role:
                return dict(status='ERROR', code='UNAUTHORIZED', request_id=rid)
            with self.rate_lock:
                start, count = self.rates.get(role, (time.monotonic(), 0))
                if time.monotonic() - start >= 1:
                    start, count = time.monotonic(), 0
                self.rates[role] = (start, count + 1)
                if count >= 100:
                    return dict(status='ERROR', code='RATE_LIMITED', request_id=rid)
            payload = req.get('payload', {})
            if not isinstance(payload, dict):
                raise ValueError()
            if kind == 'HEALTH':
                result = dict(status='OK', code='HEALTHY')
            elif kind == 'SUBMIT_ALERT':
                result = self.store.submit(payload)
            elif kind == 'GET_STATUS':
                result = self.store.status(payload['alert_id'])
            elif kind == 'LIST_ALERTS':
                offset = payload.get('offset', 0)
                if type(offset) is not int or offset < 0:
                    raise ValueError()
                result = dict(status='OK', code='ALERTS', alerts=self.store.listing(offset))
            elif kind == 'ACK_ALERT':
                result = self.store.acknowledge(payload['alert_id'])
            else:
                result = dict(status='OK', code='AUDIT', events=self.store.audit(payload['alert_id']))
            return dict(result, request_id=rid)
        except (ValueError, TypeError, KeyError, AttributeError):
            return dict(status='ERROR', code='INVALID_REQUEST', request_id=rid if isinstance(rid, str) else None)


def request(address, context, token, kind, payload=None):
    rid = str(uuid4())
    with socket.create_connection(address, timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname='localhost') as sock:
            protocol.send(sock, dict(version=1, type=kind, request_id=rid,
                                     token=token, payload=payload or {}))
            response = protocol.receive(sock)
            if response.get('request_id') != rid:
                raise ValueError('Mismatched response')
            return response
