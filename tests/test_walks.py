from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from safesignal.walks import Walks
from safesignal.server_store import Store
from safesignal.sender_store import Outbox
from safesignal.sender_worker import Worker
from test_identity import accounts


@pytest.fixture
def journey(accounts):
    auth,mail,clock,student=accounts
    _,sid,user=student(1)
    store=Store(auth.path)
    walks=Walks(auth,store)
    fields=dict(action_id=str(uuid4()),origin='Synthetic Hostel B',destination='Synthetic Library',duration=15,interval=5)
    return auth,clock,user,store,walks,fields


def test_safe_arrival_without_incident(journey):
    auth,clock,u,store,w,f=journey
    result=w.start(u,f);wid=result['id']
    assert w.start(u,f)['id']==wid
    clock[0]+=300;w.reconcile()
    assert w.get(u,wid)['slots'][0]['status']=='DUE'
    key=str(uuid4())
    w.action(u,wid,'SAFE',key);w.action(u,wid,'SAFE',key)
    assert len(w.get(u,wid)['events'])==2
    done=w.action(u,wid,'ARRIVE',str(uuid4()))
    assert done['walk_state']=='COMPLETED' and done['ended']
    clock[0]+=9000;w.reconcile()
    assert w.get(u,wid)['links']==[] and store.dashboard()['total']==0
    assert all(s['status'] in ('CONFIRMED_SAFE','CANCELLED') for s in w.get(u,wid)['slots'])


def test_help_duplicate_threads_offline_and_delivery(journey,tmp_path):
    auth,clock,u,store,w,f=journey
    wid=w.start(u,f)['id'];key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:w.action(u,wid,'HELP',key),range(2)))
    aid=results[0]['links'][0]['alert_id']
    assert results[1]['links'][0]['alert_id']==aid
    assert len(w.action(u,wid,'HELP',str(uuid4()))['links'])==1
    box=Outbox(tmp_path/'box.sqlite')
    def offline(*args): raise ConnectionError()
    worker=Worker(box,offline,auth,w.reconcile);worker.tick()
    assert box.rows()[0]['status']=='QUEUED'
    # A lost receipt after commit retains the original UUID and intent on retry.
    def deliver(kind,payload):
        if kind=='GET_STATUS': return store.status(payload['alert_id'])
        reply=store.submit(payload,u['id'])
        if not reply['duplicate']: raise EOFError()
        return reply
    worker.call=deliver
    box.retry_now(aid);worker.tick();box.retry_now(aid);worker.tick()
    assert box.rows()[0]['status']=='SERVER_RECEIVED'
    w.action(u,wid,'ARRIVE',str(uuid4()))
    assert store.status(aid)['incident_state']=='REPORTED'
    assert store.dashboard()['total']==1


def test_missed_late_restart_and_withdraw_pending(journey,tmp_path):
    auth,clock,u,store,w,f=journey
    wid=w.start(u,f)['id']
    clock[0]+=419;w.reconcile()
    assert not w.get(u,wid)['links']
    clock[0]+=1
    restarted=Walks(auth,store);restarted.reconcile();restarted.reconcile()
    missed=restarted.get(u,wid)
    assert missed['walk_state']=='NEEDS_FOLLOW_UP' and len(missed['links'])==1
    aid=missed['links'][0]['alert_id']
    safe=restarted.action(u,wid,'SAFE',str(uuid4()))
    assert safe['links'][0]['disposition']=='WITHDRAWN'
    with auth.connect() as db:
        import json
        p=json.loads(db.execute('SELECT payload FROM submission_intents WHERE alert_id=?',(aid,)).fetchone()[0])
    store.submit(p,u['id'])
    assert store.status(aid)['followup_disposition']=='WITHDRAWN'
    assert store.listing()==[] and store.authorized(u,aid)
    assert any(e['event']=='MISSED_STATUS_UNKNOWN' for e in safe['events'])
    clock[0]+=301;restarted.reconcile()
    assert restarted.get(u,wid)['links'][0]['disposition']=='REVIEW_REQUIRED'


def test_late_after_ack_requires_review_and_end_keeps_case(journey):
    auth,clock,u,store,w,f=journey
    import json
    wid=w.start(u,f)['id'];clock[0]+=421;w.reconcile()
    link=w.get(u,wid)['links'][0]
    with auth.connect() as db:
        p=json.loads(db.execute('SELECT payload FROM submission_intents').fetchone()[0])
    store.submit(p,u['id']);store.acknowledge(link['alert_id'])
    safe=w.action(u,wid,'SAFE',str(uuid4()))
    assert safe['links'][0]['disposition']=='REVIEW_REQUIRED'
    assert store.status(link['alert_id'])['incident_state']=='ACKNOWLEDGED'
    w.action(u,wid,'END',str(uuid4()));clock[0]+=9999;w.reconcile()
    assert len(w.get(u,wid)['links'])==1


def test_owner_limits_state_and_idempotency_conflicts(journey):
    auth,clock,u,store,w,f=journey
    wid=w.start(u,f)['id'];other=dict(u,id='other')
    assert w.get(other,wid)['code']=='NOT_FOUND'
    assert w.action(other,wid,'HELP',str(uuid4()))['code']=='NOT_FOUND'
    with pytest.raises(ValueError): w.start(u,dict(f,action_id=str(uuid4())))
    with pytest.raises(ValueError): w.start(u,dict(f,duration=60))
    with pytest.raises(ValueError): w.start(u,dict(f,interval=1))
    key=str(uuid4());w.action(u,wid,'SAFE',key)
    with pytest.raises(ValueError): w.action(u,wid,'HELP',key)
    key=str(uuid4());w.action(u,wid,'END',key)
    assert w.action(u,wid,'END',key)['walk_state']=='CANCELLED'
    with pytest.raises(ValueError): w.action(u,wid,'HELP',str(uuid4()))


def test_walk_http_to_real_tls_queue_and_owner_denial(tmp_path):
    import re
    import time
    from safesignal.identity import Identity
    from safesignal.hosted import hosted_runtime
    from werkzeug.test import Client
    from werkzeug.wrappers import Response
    mail=[]
    auth=Identity(tmp_path/'server.sqlite','key',mail=lambda *args:mail.append(args))
    email='0000000001@mail.jiit.ac.in'
    auth.register(email,'synthetic-password-123');auth.consume(mail[-1][2],'VERIFY')
    desk_email='0000000002@mail.jiit.ac.in'
    auth.register(desk_email,'synthetic-password-123');auth.consume(mail[-1][2],'VERIFY')
    auth.provision(desk_email,'Campus Safety')
    config=dict(identity=True,hosted=True,session_secret='key',sender_token='sender',responder_token='responder',
                allowed_hosts=('localhost',),mail=None)
    with hosted_runtime(config,tmp_path) as app:
        class HTTPSClient(Client):
            def open(self, *args, **kwargs):
                if args and isinstance(args[0], str):
                    kwargs.setdefault('base_url','https://localhost')
                return super().open(*args, **kwargs)
        c=HTTPSClient(app,Response)
        csrf=lambda page:re.search(r'name="csrf" value="([^"]+)"',page.text).group(1)
        token=csrf(c.get('/sender/login'))
        c.post('/sender/login',data=dict(csrf=token,email=email,password='synthetic-password-123'))
        page=c.get('/sender/walks/start');token=csrf(page)
        key=re.search(r'name="action_id" value="([^"]+)"',page.text).group(1)
        data=dict(csrf=token,action_id=key,origin='Synthetic Hostel',destination='Synthetic Library',duration='15',interval='5')
        reply=c.post('/sender/walks/start',data=data)
        assert reply.status_code==302
        assert c.post('/sender/walks/start',data=data).location==reply.location
        page=c.get(reply.location)
        import html
        assert "I'm Fine" in html.unescape(page.text) and 'I Need Help' in page.text
        key=re.findall(r'name="action_id" value="([^"]+)"',page.text)[1]
        help_data=dict(csrf=csrf(page),action_id=key,action='HELP')
        case=c.post(reply.location+'/action',data=help_data)
        assert '/incident/' in case.location
        assert c.post(reply.location+'/action',data=help_data).location==case.location
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            page=c.get(case.location)
            if 'Server Received' in page.text: break
            time.sleep(.1)
        assert 'Server Received' in page.text
        assert Store(tmp_path/'server.sqlite').dashboard()['total']==1
        anonymous=HTTPSClient(app,Response)
        assert anonymous.get(reply.location).status_code==302
        assert 'Registration unavailable' in anonymous.get('/sender/register').text
        assert anonymous.get('/responder/trust-lab').status_code==404
        desk=HTTPSClient(app,Response)
        token=csrf(desk.get('/responder/login'))
        assert desk.post('/responder/login',data=dict(csrf=token,email=desk_email,password='synthetic-password-123')).status_code==302
        desk_case=case.location.replace('/sender/','/responder/',1)
        assert 'simulated help requested' in desk.get(desk_case).text
        def message(client,path,body):
            token=csrf(client.get(path))
            return client.post(path+'/message',headers={'Accept':'application/json'},
                               data=dict(csrf=token,client_uuid=str(uuid4()),body=body))
        assert message(c,case.location,'Synthetic student check-in').json['code']=='SERVER_RECEIVED'
        assert 'Synthetic student check-in' in desk.get(desk_case).text
        assert message(desk,desk_case,'Synthetic desk reply').json['code']=='SERVER_RECEIVED'
        assert 'Synthetic desk reply' in c.get(case.location).text
