"""HTTP boundary for SecureSignal; existing Flask sessions and TLS room transport."""
from io import BytesIO
import json
import secrets
import sqlite3
from uuid import uuid4

import qrcode
from cryptography.exceptions import InvalidTag
from flask import abort, g, jsonify, redirect, render_template, request, send_file, session, url_for

from .cyber_cases import CATEGORIES, CHOICES, next_states, validate, valid_id
from .cyber_monitor import NEXT
from .rooms import text

ENDPOINTS = {'home','login','logout','static','profile','register','verify','recovery','reset_password',
             'cyber_report','cyber_case','cyber_message','cyber_advance','cyber_upload','cyber_download',
             'cyber_manifest','cyber_mfa','cyber_qr','cyber_sessions','cyber_replace','cyber_alerts','cyber_review'}


def register(app, role, cyber, identity, outbox, call, operation_key):
    cases, evidence, monitor = cyber
    mfa = identity.mfa

    def signal(rule, target=''):
        actor = g.user['id']
        monitor.event(rule,actor,actor=actor,target=target if valid_id(target) else '')

    def case(aid):
        row, timeline = cases.read(g.user,aid) if valid_id(aid) else (None,[])
        if not row:
            denied(aid)
        return row,timeline

    def denied(aid, evidence_access=False):
        identity.audit('EVIDENCE_ACCESS' if evidence_access else 'CASE_ACCESS','DENIED',g.user['id'],
                       'case',aid if valid_id(aid) else '', 'SCOPE')
        signal('CASE_ACCESS',aid)
        abort(404)

    def throttle(action):
        if not identity.limit(action,g.user['id'],request.remote_addr or '',window=60,maxima=(20,100)):
            abort(429)

    def page(template, **values):
        return render_template('cyber_'+template+'.html', **values)

    def move(aid, result=303):
        return redirect(url_for('cyber_case',aid=aid),code=result)

    def attach(aid, file, previous=None):
        try:
            evidence.upload(g.user,aid,file,previous)
            return None
        except (ValueError,RuntimeError) as error:
            return str(error)
        except sqlite3.Error:
            return 'Evidence storage is temporarily unavailable. Attach it again from the saved case.'
        except PermissionError:
            denied(aid,True)

    @app.route('/report', methods=['GET','POST'])
    def cyber_report():
        if role!='sender':
            abort(404)
        if request.method=='GET':
            return page('report', fields={}, errors={}, categories=CATEGORIES, choices=CHOICES, operation=str(uuid4()), evidence=evidence)
        fields,errors = validate(request.form)
        operation = request.form.get('operation','')
        if not valid_id(operation):
            abort(400)
        if errors:
            return page('report',fields=request.form,errors=errors,categories=CATEGORIES,choices=CHOICES,operation=operation,evidence=evidence),422
        throttle('cyber-report')
        try:
            created = cases.create(g.user['id'],operation,fields)
        except ValueError as error:
            abort(409,str(error))
        file = request.files.get('file')
        if created and file and file.filename:
            error=attach(operation,file)
            if error:
                session['evidence_error'] = error
        identity.reconcile(outbox)
        return move(operation)

    @app.get('/case/<aid>')
    def cyber_case(aid):
        row,timeline=case(aid)
        poll=request.args.get('poll')=='1'
        room_error = False
        room = dict(messages=[],older=0)
        if row['server_received_at']:
            try:
                reply=call('ROOM_GET',dict(alert_id=aid,before=request.args.get('before',0,type=int)))
                if reply.get('status')!='OK':
                    denied(aid)
                room=reply
            except (OSError,EOFError,ValueError):
                room_error=True
        if poll:
            return page('room_messages',row=row,room=room,room_error=room_error)
        with identity.connect() as db:
            if not cases.get(db,g.user,aid):
                denied(aid)
            files=evidence.list(db,aid)
        return page('case', row=row,timeline=timeline, files=files, evidence=evidence, room=room,room_error=room_error,
                    fields=CATEGORIES[row['category']][1], category=CATEGORIES[row['category']][0],
                    transitions=next_states(row['state']) if role=='responder' else (),
                    operation=str(uuid4()),message_key=operation_key('cyber-message',aid),
                    evidence_error=session.pop('evidence_error',None))

    @app.post('/case/<aid>/message')
    def cyber_message(aid):
        row,_=case(aid)
        body=request.form.get('body','')
        if not row['server_received_at']:
            abort(409,'Wait for the server receipt before messaging.')
        try:
            reply=call('ROOM_SEND',dict(alert_id=aid,client_uuid=request.form.get('client_uuid'),body=body))
        except (OSError,EOFError,ValueError):
            reply={'status':'ERROR','code':'UNCONFIRMED'}
        if reply.get('status')!='OK':
            if reply.get('code')=='NOT_FOUND':
                denied(aid)
            return jsonify(error='Message not confirmed. Your draft is still available.'),409
        key=operation_key('cyber-message',aid,True)
        return jsonify(next_key=key) if request.accept_mimetypes.best=='application/json' else move(aid)

    @app.post('/case/<aid>/advance')
    def cyber_advance(aid):
        if role!='responder' or g.user['team']!='Cyber Response':
            signal('RESPONDER_ACTION',aid)
            denied(aid)
        case(aid)
        try:
            cases.advance(g.user,aid,request.form.get('operation'),request.form.get('target'),request.form.get('reason',''))
        except PermissionError:
            signal('RESPONDER_ACTION',aid)
            denied(aid)
        except ValueError as error:
            signal('RESPONDER_ACTION',aid)
            abort(422,str(error))
        return move(aid)

    @app.post('/case/<aid>/evidence')
    def cyber_upload(aid):
        case(aid)
        throttle('evidence-upload')
        file=request.files.get('file')
        error=attach(aid,file,request.form.get('previous') or None) if file else 'Choose a file.'
        if error:
            session['evidence_error']=error
        return move(aid)

    @app.get('/case/<aid>/evidence/<eid>')
    def cyber_download(aid,eid):
        signal('EVIDENCE_DOWNLOAD',eid)
        throttle('evidence-download')
        try:
            row,raw=evidence.download(g.user,aid,eid)
        except PermissionError:
            denied(aid,True)
        if raw is None:
            abort(503,'Evidence could not be verified. No bytes were sent.')
        return send_file(BytesIO(raw),mimetype='application/octet-stream',download_name=row['name'],
                         as_attachment=True,conditional=False,etag=False)

    @app.get('/case/<aid>/manifest')
    def cyber_manifest(aid):
        throttle('evidence-export')
        try:
            response=jsonify(evidence.manifest(g.user,aid))
        except PermissionError:
            denied(aid,True)
        response.headers['Content-Disposition']='attachment; filename="evidence-manifest.json"'
        return response

    def pending():
        if role!='responder' or not session.get('pending_mfa'):
            return None
        return mfa.pending(session['pending_mfa'])

    @app.route('/mfa',methods=['GET','POST'])
    def cyber_mfa():
        row=pending()
        if not row:
            session.pop('pending_mfa',None)
            return redirect(url_for('login'))
        error=None
        if request.method=='POST':
            if not identity.limit('mfa',row['user_id'],request.remote_addr or ''):
                abort(429)
            try:
                sid,codes=mfa.finish(session['pending_mfa'],request.form.get('code','').strip()[:64])
            except (RuntimeError,InvalidTag):
                abort(503,'Authenticator unavailable. Contact the maintainer.')
            if sid:
                session.clear()
                session.update(sid=sid,role=role,csrf=secrets.token_urlsafe(24))
                return page('mfa',codes=codes) if codes else redirect(url_for('home'),code=303)
            error='The code was invalid, expired, or already used.'
        try:
            uri=mfa.uri(row)
        except (InvalidTag,AttributeError):
            abort(503,'Authenticator unavailable. Contact the maintainer.')
        return page('mfa',uri=uri,error=error)

    @app.get('/mfa/qr')
    def cyber_qr():
        row=pending()
        if not row or row['secret'] is None:
            abort(404)
        try:
            uri=mfa.uri(row)
        except (InvalidTag,AttributeError):
            abort(503,'Authenticator unavailable.')
        image=BytesIO()
        qrcode.make(uri).save(image,format='PNG')
        image.seek(0)
        return send_file(image,mimetype='image/png',etag=False)

    @app.route('/sessions',methods=['GET','POST'])
    def cyber_sessions():
        if request.method=='POST':
            mfa.revoke(g.user['id'],request.form.get('reference','')[:64])
            return redirect(url_for('cyber_sessions'),code=303)
        return page('sessions',sessions=mfa.sessions(g.user['id'],session['sid']))

    @app.post('/mfa/replace')
    def cyber_replace():
        if role!='responder':
            abort(404)
        throttle('mfa-replace')
        try:
            replaced=mfa.replace(g.user['id'],request.form.get('password','')[:129],request.form.get('code','').strip()[:64])
        except InvalidTag:
            abort(503,'Authenticator unavailable.')
        if not replaced:
            abort(400,'Password or factor could not be confirmed.')
        session.clear()
        return redirect(url_for('login'),code=303)

    def reviewer():
        if role!='responder' or g.user['team']!='Security Review':
            signal('RESPONDER_ACTION')
            abort(404)

    @app.get('/security-alerts')
    def cyber_alerts():
        reviewer()
        with identity.connect() as db:
            rows=db.execute('SELECT * FROM security_alerts WHERE id<? ORDER BY id DESC LIMIT 21',
                            (request.args.get('before',2**63-1,type=int),)).fetchall()
            aid=request.args.get('id',type=int)
            selected=db.execute('SELECT * FROM security_alerts WHERE id=?',(aid,)).fetchone() if aid else None
            history=db.execute('SELECT * FROM security_review WHERE alert_id=? ORDER BY id',(aid,)).fetchall() if selected else []
        return page('alerts',rows=rows,selected=selected,history=history,next_status=NEXT,
                    signals=json.loads(selected['sample']) if selected else [])

    @app.post('/security-alerts/<int:aid>')
    def cyber_review(aid):
        reviewer()
        try:
            monitor.review(aid,g.user['id'],request.form.get('target'),text(request.form.get('reason',''),500))
        except ValueError as error:
            abort(422,str(error))
        return redirect(url_for('cyber_alerts',id=aid),code=303)
