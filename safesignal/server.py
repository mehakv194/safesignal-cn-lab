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

    def __init__(self, address, context, store, sender_token, responder_token, faults=None, identity=None, walks=None):
        if not sender_token or not responder_token or sender_token == responder_token:
            raise ValueError('Distinct nonempty role tokens required')
        self.context, self.store = context, store
        self.faults = faults
        self.identity = identity
        self.walks = walks
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
            required = {'SUBMIT_ALERT': 'sender', 'GET_STATUS': ('sender','responder'),
                        'LIST_ALERTS': 'responder', 'ACK_ALERT': 'responder',
                        'UPDATE_INCIDENT':'responder','DASHBOARD':'responder',
                        'GET_AUDIT': ('sender','responder'), 'HEALTH': 'sender',
                        'WALK_START':'sender','WALK_GET':'sender','WALK_LIST':'sender','WALK_ACTION':'sender'}
            permitted = required.get(kind, ())
            if role is None or (role not in permitted if isinstance(permitted,tuple) else permitted != role):
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
            principal = None
            if self.identity and kind != 'HEALTH':
                principal = self.identity.principal(req)
                if principal['role'] != ('student' if role=='sender' else 'responder'):
                    return dict(status='ERROR',code='UNAUTHORIZED',request_id=rid)
                if kind in ('GET_STATUS','GET_AUDIT','ACK_ALERT','UPDATE_INCIDENT') and not self.store.authorized(principal,payload.get('alert_id')):
                    return dict(status='ERROR',code='NOT_FOUND',request_id=rid)
                if kind == 'SUBMIT_ALERT' and not principal.get('job'):
                    return dict(status='ERROR',code='UNAUTHORIZED',request_id=rid)
                if kind == 'UPDATE_INCIDENT' and payload.get('action')=='CLAIM' and payload.get('team') != principal['team']:
                    return dict(status='ERROR',code='UNAUTHORIZED',request_id=rid)
                if kind == 'ACK_ALERT' and principal['team'] != 'Campus Safety':
                    return dict(status='ERROR',code='UNAUTHORIZED',request_id=rid)
            if kind in ('GET_STATUS','GET_AUDIT','ACK_ALERT','UPDATE_INCIDENT'):
                if not isinstance(payload.get('alert_id'),str):
                    raise ValueError()
                UUID(payload['alert_id'])
            if kind == 'HEALTH':
                result = dict(status='OK', code='HEALTHY')
            elif kind.startswith('WALK_'):
                if not self.walks or not principal or principal.get('job'):
                    raise ValueError('Walks unavailable')
                if kind=='WALK_START':
                    result=self.walks.start(principal,payload)
                elif kind=='WALK_GET':
                    result=self.walks.get(principal,payload['walk_id'])
                elif kind=='WALK_LIST':
                    result=self.walks.listing(principal)
                else:
                    result=self.walks.action(principal,payload['walk_id'],payload['action'],payload['action_id'])
            elif kind == 'SUBMIT_ALERT':
                result = self.store.submit(payload, principal['id'] if principal else None)
            elif kind == 'GET_STATUS':
                result = self.store.status(payload['alert_id'])
            elif kind == 'LIST_ALERTS':
                offset = payload.get('offset', 0)
                if type(offset) is not int or offset < 0:
                    raise ValueError()
                result = dict(status='OK', code='ALERTS', alerts=self.store.listing(
                    offset, payload.get('severity', ''), payload.get('state', ''), payload.get('newest') is True,
                    payload.get('incident_state',''),payload.get('category',''),payload.get('search',''),principal))
            elif kind == 'ACK_ALERT':
                result = self.store.acknowledge(payload['alert_id'],principal)
            elif kind == 'UPDATE_INCIDENT':
                result = self.store.update_incident(payload['alert_id'],payload['action'],payload.get('team',''),payload.get('note',''),principal)
            elif kind == 'DASHBOARD':
                result = dict(status='OK',code='DASHBOARD', **self.store.dashboard(principal))
            else:
                result = dict(status='OK', code='AUDIT', events=self.store.audit(payload['alert_id']))
            return dict(result, request_id=rid)
        except (ValueError, TypeError, KeyError, AttributeError):
            return dict(status='ERROR', code='INVALID_REQUEST', request_id=rid if isinstance(rid, str) else None)


def request(address, context, token, kind, payload=None, identity=None, principal=None):
    rid = str(uuid4())
    with socket.create_connection(address, timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname='localhost') as sock:
            req = dict(version=1,type=kind,request_id=rid,token=token,payload=payload or {})
            if identity and principal:
                req['principal'] = identity.sign(req,principal)
            protocol.send(sock,req)
            response = protocol.receive(sock)
            if response.get('request_id') != rid:
                raise ValueError('Mismatched response')
            return response
