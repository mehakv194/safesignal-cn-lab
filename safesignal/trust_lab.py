"""Bounded local fixtures, never public attack endpoints or external traffic."""
import hmac
from pathlib import Path
import secrets
import tempfile
from uuid import uuid4

from .identity import Identity, canonical
from .models import new_alert
from .server import AlertServer
from .server_store import Store


SCENARIOS={
    'genuine':'Genuine authenticated message',
    'modified':'Modified message rejected',
    'cross_user':"Another student's case denied",
    'role':'Unauthorized responder action denied',
    'burst':'Bounded failed-login burst detected',
}


class TrustLab:
    def __init__(self,identity):
        self.identity=identity
        self.key=hmac.digest(identity.key,b'local-trust-lab-only','sha256')

    def verify(self,payload,signature):
        expected=hmac.new(self.key,canonical(payload).encode(),'sha256').hexdigest()
        return isinstance(signature,str) and hmac.compare_digest(expected,signature)

    def run(self,scenario,actor):
        if scenario not in SCENARIOS:
            raise ValueError('Choose a known local fixture')
        if scenario in ('genuine','modified'):
            payload=dict(case='synthetic-fixture',message='TEST ONLY: authenticated simulated update')
            signature=hmac.new(self.key,canonical(payload).encode(),'sha256').hexdigest()
            if scenario=='modified':
                payload['message']='TEST ONLY: content altered after authentication'
            verified=self.verify(payload,signature)
            result='VERIFIED' if verified else 'REJECTED'
            reason='HMAC_VALID' if verified else 'INTEGRITY_MISMATCH'
        else:
            with tempfile.TemporaryDirectory(prefix='safesignal-trust-') as directory:
                captured=[]
                fixture=Identity(Path(directory)/'fixture.sqlite',secrets.token_urlsafe(32),mail=lambda *args:captured.append(args))
                emails=('0000000101@mail.jiit.ac.in','0000000102@mail.jiit.ac.in')
                password=secrets.token_urlsafe(24)
                sids=[]
                for email in emails:
                    fixture.register(email,password)
                    fixture.consume(captured[-1][2],'VERIFY')
                    sids.append(fixture.login(email,password,'student'))
                store=Store(fixture.path)
                payload=new_alert('LOW','TEST ONLY: isolated private fixture')
                store.submit(payload,fixture.user(sids[0])['id'])
                if scenario=='burst':
                    for _ in range(6):
                        fixture.login(emails[0],'deliberately-wrong-local-password','student','loopback-fixture')
                    with fixture.connect() as db:
                        detected=db.execute("SELECT count(*) FROM security_events WHERE event='LOGIN_BURST'").fetchone()[0]==1
                    result='DETECTED' if detected else 'FAILED'
                    reason='BOUNDED_APPLICATION_LOGIN_RULE'
                else:
                    sender,responder=secrets.token_urlsafe(24),secrets.token_urlsafe(24)
                    # Reuse actual dispatch and ownership guards without sending attack traffic.
                    with AlertServer(('127.0.0.1',0),None,store,sender,responder,identity=fixture) as server:
                        req=dict(version=1,request_id=str(uuid4()),token=sender,
                                 type='GET_STATUS' if scenario=='cross_user' else 'UPDATE_INCIDENT',
                                 payload=dict(alert_id=payload['alert_id'],action='CLAIM',team='Campus Safety'))
                        req['principal']=fixture.sign(req,dict(sid=sids[1] if scenario=='cross_user' else sids[0]))
                        reply=server.dispatch(req)
                        denied=reply.get('code')==('NOT_FOUND' if scenario=='cross_user' else 'UNAUTHORIZED')
                    result='DENIED' if denied else 'FAILED'
                    reason='OBJECT_OWNERSHIP' if scenario=='cross_user' else 'SERVER_ASSIGNED_ROLE'
        self.identity.audit('TRUST_'+scenario.upper(),result,actor,'local_fixture','',reason)
        return dict(scenario=SCENARIOS[scenario],result=result,reason=reason)

    def events(self):
        with self.identity.connect() as db:
            rows=db.execute('SELECT event,result,stamp,reason_code FROM security_events ORDER BY id DESC LIMIT 20').fetchall()
        return [dict(r) for r in rows]
