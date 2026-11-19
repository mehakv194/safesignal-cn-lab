import json
import threading
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from safesignal.rooms import Rooms
from safesignal.server_store import Store
from safesignal.server import AlertServer, request
from safesignal.tls import create_certificate, client_context, server_context
from safesignal.models import new_alert
from safesignal import protocol
from test_identity import accounts


@pytest.fixture
def room_lab(accounts,tmp_path):
    auth,mail,clock,student=accounts
    _,sid,owner=student(1);_,other_sid,other=student(2)
    email,_,_=student(3);auth.provision(email,'Medical Team')
    desk_sid=auth.login(email,'correct-password-123','responder');desk=auth.user(desk_sid)
    store=Store(auth.path);rooms=Rooms(auth,store)
    p=new_alert('HIGH','TEST ONLY: private room case');store.submit(p,owner['id'])
    return auth,clock,store,rooms,p['alert_id'],owner,other,desk,sid,other_sid,desk_sid


def test_private_thread_and_duplicate_conflict(room_lab):
    auth,clock,store,rooms,aid,a,b,desk,*_=room_lab
    key=str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        replies=list(pool.map(lambda _:rooms.send(a,aid,key,'TEST ONLY: student question'),range(2)))
    assert replies[0]['message_id']==replies[1]['message_id']
    assert rooms.send(a,aid,key,'Changed question')['code']=='ID_CONFLICT'
    assert rooms.get(b,aid)['code']=='NOT_FOUND'
    assert rooms.send(b,aid,str(uuid4()),'Guessed case')['code']=='NOT_FOUND'
    store.update_incident(aid,'CLAIM','Medical Team',principal=desk)
    assert rooms.send(desk,aid,str(uuid4()),'Are you in a safe place?')['status']=='OK'
    assert len(rooms.get(a,aid)['messages'])==2
    unauthorized=dict(desk,team='Facilities Team')
    assert rooms.get(unauthorized,aid)['code']=='NOT_FOUND'
    assert rooms.feedback(a,aid,str(uuid4()),'CONFIRM','Too early')['code']=='INVALID_TRANSITION'


def test_resolution_feedback_review_without_regression(room_lab):
    auth,clock,store,rooms,aid,a,b,desk,*_=room_lab
    store.update_incident(aid,'CLAIM','Medical Team',principal=desk)
    store.update_incident(aid,'START',principal=desk)
    store.update_incident(aid,'RESOLVE',note='TEST ONLY: proposed resolution',principal=desk)
    key=str(uuid4())
    assert rooms.feedback(a,aid,key,'REOPEN_REQUEST','Still need simulated help')['status']=='OK'
    assert rooms.feedback(a,aid,key,'REOPEN_REQUEST','Still need simulated help')['status']=='OK'
    assert rooms.feedback(b,aid,str(uuid4()),'CONFIRM','Guessing case')['code']=='NOT_FOUND'
    assert rooms.feedback(a,aid,str(uuid4()),'REVIEW','Cannot self-review')['code']=='UNAUTHORIZED'
    assert rooms.feedback(a,aid,str(uuid4()),'CONFIRM','Not while pending')['code']=='REVIEW_PENDING'
    assert store.status(aid)['review_pending']==1 and store.status(aid)['incident_state']=='RESOLVED'
    assert rooms.feedback(desk,aid,str(uuid4()),'REVIEW','TEST ONLY: follow-up response provided')['status']=='OK'
    assert rooms.feedback(a,aid,str(uuid4()),'CONFIRM','Confirmed simulated outcome')['status']=='OK'
    assert not rooms.get(a,aid)['review_pending']
    assert store.status(aid)['incident_state']=='RESOLVED'
    assert store.audit(aid)[-1]['event']=='CONFIRM'


def test_bounded_unicode_pagination_quota_and_audit_redaction(room_lab):
    auth,clock,store,rooms,aid,a,b,desk,*_=room_lab
    for i in range(6): rooms.send(a,aid,str(uuid4()),str(i)+'🚦'*299)
    page=rooms.get(a,aid)
    assert len(page['messages'])==4 and page['older']
    assert len(rooms.get(a,aid,page['older'])['messages'])==2
    encoded=json.dumps(page,ensure_ascii=False).encode()
    assert len(encoded)<protocol.MAX_FRAME
    assert '🚦' not in str(store.audit(aid))
    with pytest.raises(ValueError): rooms.send(a,aid,str(uuid4()),'x'*301)
    with pytest.raises(ValueError): rooms.send(a,aid,str(uuid4()),'bad\x00content')
    for i in range(24): rooms.send(a,aid,str(uuid4()),'More synthetic messages')
    assert rooms.send(a,aid,str(uuid4()),'Over quota')['code']=='RATE_LIMITED'
    assert len(rooms.get(a,aid)['messages'])==4


def test_room_over_real_tls_owner_role_and_receipt_retry(room_lab,tmp_path):
    auth,clock,store,rooms,aid,a,b,desk,sa,sb,sr=room_lab
    cert=tmp_path/'cert';create_certificate(cert)
    with AlertServer(('127.0.0.1',0),server_context(cert),store,'sender','responder',identity=auth,rooms=rooms) as server:
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def call(kind,p,sid=sa,token='sender'):
            return request(server.server_address,client_context(cert),token,kind,p,auth,dict(sid=sid))
        p=dict(alert_id=aid,client_uuid=str(uuid4()),body='<script>TEST ONLY</script>')
        first=call('ROOM_SEND',p)
        assert first['code']=='SERVER_RECEIVED'
        assert call('ROOM_SEND',p)['message_id']==first['message_id']
        assert call('ROOM_GET',dict(alert_id=aid),sb)['code']=='NOT_FOUND'
        assert call('ROOM_GET',dict(alert_id=aid),sa,'responder')['code']=='UNAUTHORIZED'
        assert call('ROOM_GET',dict(alert_id=aid),sr,'responder')['messages'][0]['body']==p['body']
        assert request(server.server_address,client_context(cert),'sender','ROOM_GET',dict(alert_id=aid))['status']=='ERROR'
        server.shutdown();thread.join()


def test_room_web_csrf_escaping_and_private_polling(room_lab,tmp_path):
    from safesignal.web import create_app
    from safesignal.sender_store import Outbox
    auth,clock,store,rooms,aid,a,b,desk,sa,sb,sr=room_lab
    box=Outbox(tmp_path/'outbox.sqlite')
    payload=store.status(aid)
    box.enqueue_owned({k:payload[k] for k in ('alert_id','created_at','category','description','location','severity')},a['id'])
    def call(kind,p=None,principal=None):
        user=auth.user(principal['sid'])
        if kind=='GET_STATUS': return store.status(aid)
        if kind=='GET_AUDIT': return dict(events=store.audit(aid))
        if kind=='ROOM_GET': return rooms.get(user,p['alert_id'],p.get('before',0))
        return rooms.send(user,p['alert_id'],p['client_uuid'],p['body'])
    app=create_app('sender',dict(session_secret='test'),call,box,identity=auth)
    c=app.test_client()
    with c.session_transaction() as s:s.update(sid=sa,role='sender',csrf='csrf')
    assert c.post('/incident/'+aid+'/message',data={}).status_code==400
    key=str(uuid4())
    reply=c.post('/incident/'+aid+'/message',headers={'Accept':'application/json'},data=dict(csrf='csrf',client_uuid=key,body='<script>TEST ONLY</script>'))
    assert reply.json['code']=='SERVER_RECEIVED'
    page=c.get('/incident/'+aid).text
    assert '&lt;script&gt;TEST ONLY&lt;/script&gt;' in page
    assert 'data-room-send' in page and 'room-thread' in page
    with c.session_transaction() as s:s.update(sid=sb,role='sender',csrf='csrf')
    assert c.get('/incident/'+aid).status_code==404
    assert c.post('/incident/'+aid+'/message',data=dict(csrf='csrf',client_uuid=str(uuid4()),body='Other student')).status_code==404
