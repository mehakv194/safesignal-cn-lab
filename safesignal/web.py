import hmac
import secrets
import time
from uuid import uuid4

from flask import Flask, abort, redirect, render_template, request, session, url_for, send_from_directory, g, jsonify
from pathlib import Path
from datetime import datetime, timezone

from .models import SEVERITIES, CATEGORIES, INCIDENT_STATES, RESPONSE_TEAMS, new_alert
from .dashboard import summarize
from .faults import PRESETS


def create_app(role, config, call, outbox=None, faults=None, identity=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=config['session_secret'], MAX_CONTENT_LENGTH=8192,
                      SESSION_COOKIE_NAME='safesignal_' + role,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=config.get('hosted', False),
                      SESSION_COOKIE_PATH='/' + role if config.get('hosted') else '/')
    login_attempts = []
    cyber = config.get('cyber_services')
    if cyber:
        from . import cyber_web
        from io import BytesIO
        from flask import Request
        class EvidenceRequest(Request):
            # Keep multipart plaintext in memory; Flask's request cap bounds each request.
            def _get_file_stream(self, total_content_length, content_type, filename=None, content_length=None):
                return BytesIO()
        app.request_class = EvidenceRequest
        app.config.update(MAX_CONTENT_LENGTH=cyber[1].max_size+65536, MAX_FORM_MEMORY_SIZE=65536, MAX_FORM_PARTS=30)
    demo_login = config.get('demo_accounts') is not None
    evidence_dir = Path(config.get('evidence_dir', 'artifacts'))
    raw_call = call
    local_lab=bool(not cyber and identity and config.get('trust_lab') and not config.get('hosted',False)
                   and set(config.get('allowed_hosts',('127.0.0.1','localhost'))) <= {'127.0.0.1','localhost'})
    if config.get('hosted'):
        faults=None
    transfer_view = bool(config.get('combined') and (config.get('hosted') or (faults and faults.enabled)))
    hosted_demo = bool(transfer_view and config.get('hosted') and demo_login and identity and role == 'sender')
    fault_controls = hosted_demo or bool(transfer_view and faults and faults.enabled and role == 'sender')
    if identity:
        def call(kind,payload=None):
            return raw_call(kind,payload,dict(sid=session.get('sid','')))

    def owned_rows():
        return outbox.rows(g.user['id'] if identity else None)

    def enqueue(payload):
        if identity:
            identity.accept(g.user['id'],payload)
            identity.reconcile(outbox)
        else:
            outbox.enqueue(payload)

    def operation_key(purpose,aid,rotate=False):
        keys=dict(session.get('operation_keys',{}))
        name=purpose+aid
        if rotate or name not in keys:
            if len(keys)>=12:
                keys.pop(next(iter(keys)))
            keys[name]=str(uuid4())
            session['operation_keys']=keys
        return keys[name]

    @app.context_processor
    def deployment_context():
        return {'cyber_mode':bool(cyber),'trust_lab_enabled':local_lab,'demo_login':demo_login,'identity_enabled':bool(identity),'current_user':getattr(g,'user',None),'hosted': config.get('hosted', False), 'combined':config.get('combined',False),
                'ephemeral_storage':config.get('ephemeral_storage',False), 'role':role,'categories':CATEGORIES,
                'severities':SEVERITIES,'incident_states':INCIDENT_STATES,'teams':((g.user['team'],) if identity and getattr(g,'user',None) and g.user['role']=='responder' else RESPONSE_TEAMS),
                'today':datetime.now(timezone.utc).strftime('%d %b %Y'), 'local_role_url':
                ('http://127.0.0.1:5002/' if role=='sender' else 'http://127.0.0.1:5001/')}

    @app.template_filter('stamp')
    def stamp(value):
        if not value:
            return '—'
        return datetime.fromisoformat(value).strftime('%d %b · %H:%M UTC')

    @app.template_filter('epoch')
    def epoch(value):
        return datetime.fromtimestamp(value,timezone.utc).strftime('%d %b · %H:%M UTC') if value is not None else '—'

    @app.template_filter('retry_time')
    def retry_time(value):
        return datetime.fromtimestamp(value, timezone.utc).strftime('%H:%M:%S')

    @app.before_request
    def guard():
        if cyber and request.endpoint not in cyber_web.ENDPOINTS:
            abort(404)
        if request.endpoint in ('trust_lab','run_trust_fixture') and (not local_lab or request.remote_addr not in ('127.0.0.1','::1')):
            abort(404)
        if request.host.split(':')[0] not in config.get('allowed_hosts', ('127.0.0.1', 'localhost')):
            abort(400)
        if config.get('hosted') and not request.is_secure:
            abort(400)
        if demo_login and (request.endpoint in ('register','verify','recovery','reset_password','redeem_invite')
                           or (request.endpoint == 'profile' and request.method == 'POST')):
            abort(404)
        session.setdefault('csrf', secrets.token_urlsafe(24))
        if request.method == 'POST':
            if not hmac.compare_digest(session['csrf'], request.form.get('csrf', '')):
                abort(400)
        if identity:
            g.user=identity.user(session.get('sid',''))
            public=('login','static','register','verify','recovery','reset_password','redeem_invite')
            if cyber:
                if session.get('pending_mfa') and not g.user:
                    if request.endpoint not in ('cyber_mfa','cyber_qr','logout','static'):
                        return redirect(url_for('cyber_mfa'))
                public += ('cyber_mfa','cyber_qr')
            if request.endpoint not in public and (not g.user or g.user['role'] != ('student' if role=='sender' else 'responder')):
                return redirect(url_for('login'))
            if request.endpoint in ('evidence','evidence_file') and g.user and g.user['role']!='responder':
                abort(403)
            return
        if request.endpoint != 'login' and request.endpoint != 'static' and session.get('role') != role:
            return redirect(url_for('login'))

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'"
        return response

    @app.errorhandler(503)
    def unavailable(error):
        if cyber:
            return render_template('cyber_error.html',error=error),503
        return render_template('unavailable.html',view='overview'),503

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if identity:
            if request.method=='POST':
                email=request.form.get('email','')[:254]
                if not identity.limit('login',email.lower().strip(),request.remote_addr or ''):
                    abort(429)
                try:
                    sid=identity.login(email,request.form.get('password','')[:129],'student' if role=='sender' else 'responder',
                                       request.remote_addr or '', pending=bool(cyber and role=='responder'))
                except RuntimeError:
                    abort(503,'Authenticator unavailable. Contact the maintainer.')
                if sid:
                    identity.logout(session.get('sid',''))
                    session.clear()
                    if cyber and role=='responder':
                        session.update(pending_mfa=sid,csrf=secrets.token_urlsafe(24))
                        return redirect(url_for('cyber_mfa'))
                    session.update(sid=sid,role=role,csrf=secrets.token_urlsafe(24))
                    return redirect(url_for('home'))
                error=('Sign-in failed. Check your email, password and dashboard role.' if demo_login
                       else 'Sign-in failed. Check your credentials, verification and dashboard role.')
            return render_template('identity.html',mode='login',error=error)
        if request.method == 'POST':
            login_attempts[:] = [t for t in login_attempts if time.monotonic() - t < 60]
            if len(login_attempts) >= 10:
                abort(429)
            login_attempts.append(time.monotonic())
            supplied = request.form.get('token', '').encode()
            if hmac.compare_digest(supplied, config[role + '_token'].encode()):
                session.clear()
                session.update(role=role, csrf=secrets.token_urlsafe(24))
                return redirect(url_for('home'))
            error = 'Invalid local access token'
        return render_template('login.html', role=role, error=error)

    @app.post('/logout')
    def logout():
        if cyber and session.get('pending_mfa'):
            identity.mfa.cancel(session['pending_mfa'])
        if identity:
            identity.logout(session.get('sid',''))
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    def home():
        if cyber:
            if role=='responder' and g.user['team']=='Security Review':
                return redirect(url_for('cyber_alerts'))
            offset=max(0,min(100000,request.args.get('offset',0,type=int)))
            assigned=role=='responder' and request.args.get('view')=='assigned'
            rows=cyber[0].list(g.user,offset,assigned)
            return render_template('cyber_queue.html',rows=rows[:20],more=len(rows)>20,offset=offset,
                                   assigned=assigned,categories=cyber_web.CATEGORIES)
        if transfer_view and request.args.get('view') == 'network':
            rows, events, error = [], [], None
            if role == 'sender':
                owned = owned_rows()
                demo_id = session.get('network_demo_id') if hosted_demo else None
                rows = [row for row in owned if row['alert_id'] == demo_id][:1] or owned[:1]
                if rows:
                    events = outbox.timeline(rows[0]['alert_id'])[-12:]
            else:
                try:
                    reply = call('LIST_ALERTS', {'newest': True})
                    if reply['status'] != 'OK':
                        raise ValueError('Backend rejected request')
                    rows = reply['alerts']
                except (OSError, EOFError, ValueError):
                    error = 'The incident server is unavailable. Its latest receipts could not be checked.'
            return render_template('network_lab.html', rows=rows, events=events, error=error,
                                   fault_controls=fault_controls,
                                   hosted_demo=hosted_demo,
                                   preset=(session.get('network_demo_preset', 'normal') if hosted_demo
                                           else faults.preset() if fault_controls else None), view='network')
        error = None
        reachable = False
        rows = []
        overview = dict(summarize([]),activity=[],duplicates=0)
        try:
            if role == 'sender':
                rows = owned_rows()
                for row in rows:
                    row['timeline'] = outbox.timeline(row['alert_id'])
                overview = dict(summarize([dict(r['alert'],incident_state=r['incident_state']) for r in rows]),
                                activity=sorted([dict(e,alert_id=r['alert_id']) for r in rows for e in r['timeline']],key=lambda e:e['recorded_at'],reverse=True)[:6],
                                duplicates=sum(e['event']=='DUPLICATE_SUPPRESSED' for r in rows for e in r['timeline']),
                                retries=sum(max(0,r['attempt_count']-1) for r in rows),
                                queued=sum(r['status'] in ('QUEUED','SENDING') for r in rows))
                search = request.args.get('search','').lower()
                rows = [r for r in rows if (not request.args.get('incident_state') or r['incident_state']==request.args['incident_state'])
                        and (not request.args.get('category') or r['alert'].get('category','SAFETY')==request.args['category'])
                        and (not request.args.get('severity') or r['alert']['severity']==request.args['severity'])
                        and (not search or search in (r['alert']['description']+' '+r['alert']['location']).lower())]
                try:
                    reachable = call('HEALTH')['status'] == 'OK'
                except (OSError, EOFError, ValueError):
                    pass
            else:
                offset = max(0, int(request.args.get('offset', '0')))
                reply = call('LIST_ALERTS', {'offset':offset,'severity':request.args.get('severity',''),
                    'newest':request.args.get('newest')=='1','incident_state':request.args.get('incident_state',''),
                    'category':request.args.get('category',''),'search':request.args.get('search','')})
                if reply['status'] != 'OK':
                    raise ValueError('Backend rejected request')
                rows = reply['alerts']
                reachable = True
                rows = [dict(r, alert=r, status=r['code']) for r in rows]
                summary = call('DASHBOARD')
                if summary['status']=='OK':
                    overview = summary
        except (OSError, EOFError, ValueError):
            rows, error = [], 'TLS backend unavailable. Saved sender alerts remain on disk.'
        if error and role=='responder':
            abort(503)
        template='student_home.html' if identity and role=='sender' and request.args.get('view','overview')=='overview' else 'home.html'
        active_walk=None
        if identity and role=='sender':
            try:
                active_walk=next((w for w in call('WALK_LIST').get('walks',[]) if w['status'] in ('ACTIVE','NEEDS_FOLLOW_UP')),None)
            except (OSError,EOFError,ValueError):
                pass
        return render_template(template, role=role, rows=rows, error=error, severities=SEVERITIES,active_walk=active_walk,
                               faults=faults, preset=faults.preset() if faults else 'normal',
                               offset=request.args.get('offset', '0'), reachable=reachable,overview=overview,
                               view=request.args.get('view','overview'))

    @app.get('/incident/<aid>')
    def incident(aid):
        reply = None
        events = []
        events_source = 'local'
        if role=='sender':
            row = next((r for r in owned_rows() if r['alert_id']==aid),None)
            if row is None:
                abort(404)
            reply = dict(row['alert'],**{k:row[k] for k in ('incident_state','assigned_team','assigned_to','last_note','resolved_at','server_received_at','responder_acknowledged_at')},code=row['status'])
            events = outbox.timeline(aid)
        try:
            remote = call('GET_STATUS',{'alert_id':aid})
            if remote['status']=='OK':
                reply = remote
                events = call('GET_AUDIT',{'alert_id':aid}).get('events',[])
                events_source = 'server'
            elif reply is None:
                abort(404)
        except (OSError,EOFError,ValueError):
            if reply is None:
                abort(503,'The incident server is unavailable. Please try again.')
        room=None
        if identity:
            try:
                room=call('ROOM_GET',dict(alert_id=aid,before=max(0,int(request.args.get('before','0')))))
                if room.get('status')!='OK':
                    room=None
            except (OSError,EOFError,ValueError):
                pass
        return render_template('incident.html',incident=reply,events=events[-8:],events_source=events_source,view='incidents',
                               room=room,message_key=operation_key('message',aid) if identity else None,
                               feedback_key=operation_key('feedback',aid) if identity else None)

    @app.post('/examples')
    def examples():
        if role!='sender':
            abort(403)
        for category,severity,description,location in (
            ('MEDICAL','HIGH','TEST ONLY: first-aid assistance requested during a campus drill','Synthetic Sports Centre'),
            ('FIRE','CRITICAL','TEST ONLY: simulated smoke alarm in a practice evacuation','Synthetic Science Block'),
            ('SAFETY','MEDIUM','TEST ONLY: safety escort requested for a campus training exercise','Synthetic Library Walkway'),
            ('INFRASTRUCTURE','LOW','TEST ONLY: broken walkway lighting reported in a facility drill','Synthetic North Gate'),
        ):
            enqueue(new_alert(severity,description,location,category))
        return redirect(url_for('home'))

    @app.post('/incident/<aid>/update')
    def update_incident(aid):
        if role!='responder':
            abort(403)
        try:
            reply = call('UPDATE_INCIDENT',{'alert_id':aid,'action':request.form.get('action'),
                'team':request.form.get('team',''),'note':request.form.get('note','')})
            if reply['status']!='OK':
                abort(400,'This action is not valid for the current incident state. Resolution and notes need 5–200 characters.')
        except (OSError,EOFError,ValueError):
            abort(503,'Update was not confirmed; refresh before trying again.')
        if transfer_view and request.args.get('view') == 'network':
            return redirect(url_for('home', view='network'))
        return redirect(url_for('incident',aid=aid))

    @app.post('/simulation')
    def simulation():
        if hosted_demo:
            preset = request.form.get('preset')
            if preset not in PRESETS:
                abort(400)
            if preset == 'normal':
                outbox.restore_demo_link(session.get('network_demo_id'), g.user['id'])
            session['network_demo_preset'] = preset
            return redirect(url_for('home', view='network'))
        if role != 'sender' or not faults or not faults.enabled:
            abort(403)
        try:
            faults.set(request.form.get('preset'))
        except ValueError:
            abort(400)
        if fault_controls:
            return redirect(url_for('home', view='network'))
        return redirect(url_for('home'))

    @app.post('/network-demo/report')
    def network_sample():
        if not fault_controls or role != 'sender':
            abort(404)
        payload = new_alert('MEDIUM', 'TEST ONLY: Network Lab transfer', 'Synthetic classroom')
        if hosted_demo:
            if outbox.demo_fault(session.get('network_demo_id')) == 'disconnect':
                abort(409, 'Restore the current test link before sending another test report.')
            preset = session.get('network_demo_preset', 'normal')
            if preset != 'normal':
                outbox.set_demo_fault(payload['alert_id'], preset)
            session['network_demo_id'] = payload['alert_id']
        enqueue(payload)
        return redirect(url_for('home', view='network'))

    @app.get('/evidence')
    def evidence():
        import json
        path = evidence_dir / 'latest.json'
        report = json.loads(path.read_text()) if path.exists() else None
        return render_template('evidence.html', role=role, report=report)

    @app.get('/evidence/<filename>')
    def evidence_file(filename):
        if filename not in ('results.csv', 'summary.json', 'comparison.svg'):
            abort(404)
        import json
        path = evidence_dir / 'latest.json'
        if not path.exists():
            abort(404)
        run_id = json.loads(path.read_text())['run_id']
        return send_from_directory(evidence_dir.resolve() / run_id, filename)

    @app.post('/submit')
    def submit():
        if role != 'sender':
            abort(403)
        try:
            enqueue(new_alert(request.form.get('severity'), request.form.get('description', ''), request.form.get('location', ''),request.form.get('category','SAFETY')))
        except ValueError:
            abort(400, 'Use a valid severity, description of 10–300 characters and location up to 120 characters.')
        return redirect(url_for('home'))

    @app.post('/retry/<aid>')
    def retry(aid):
        if role != 'sender':
            abort(403)
        if identity and not any(r['alert_id']==aid for r in owned_rows()):
            abort(404)
        outbox.retry_now(aid)
        return redirect(url_for('home'))

    @app.post('/ack/<aid>')
    def ack(aid):
        if role != 'responder':
            abort(403)
        try:
            reply = call('ACK_ALERT', {'alert_id': aid})
            if reply['status'] != 'OK':
                abort(400)
        except (OSError, EOFError, ValueError):
            abort(503, 'Backend unavailable; acknowledgment was not confirmed.')
        return redirect(url_for('home'))

    if identity:
        from .trust_lab import TrustLab, SCENARIOS
        lab=TrustLab(identity) if local_lab else None

        @app.get('/trust-lab')
        def trust_lab():
            if role!='responder' or not lab:
                abort(404)
            return render_template('trust_lab.html',scenarios=SCENARIOS,result=session.get('trust_result'),events=lab.events())

        @app.post('/trust-lab/run')
        def run_trust_fixture():
            if role!='responder' or not lab:
                abort(404)
            if not identity.limit('trust_lab',g.user['id'],request.remote_addr or ''):
                abort(429)
            try:
                session['trust_result']=lab.run(request.form.get('scenario'),g.user['id'])
            except ValueError:
                abort(400)
            return redirect(url_for('trust_lab'))

        @app.post('/incident/<aid>/message')
        def send_message(aid):
            payload=dict(alert_id=aid,client_uuid=request.form.get('client_uuid'),body=request.form.get('body',''))
            try:
                reply=call('ROOM_SEND',payload)
            except (OSError,EOFError,ValueError):
                return jsonify(status='ERROR',code='UNCONFIRMED'),503
            if reply.get('status')!='OK':
                return jsonify(reply),404 if reply.get('code')=='NOT_FOUND' else 400
            key=operation_key('message',aid,True)
            if request.accept_mimetypes.best=='application/json':
                return jsonify(dict(reply,next_key=key))
            return redirect(url_for('incident',aid=aid))

        @app.post('/incident/<aid>/feedback')
        def incident_feedback(aid):
            try:
                reply=call('ROOM_FEEDBACK',dict(alert_id=aid,client_uuid=request.form.get('client_uuid'),
                                               kind=request.form.get('kind'),body=request.form.get('body','')))
            except (OSError,EOFError,ValueError):
                abort(503,'Feedback not confirmed. Refresh before retrying.')
            if reply.get('status')!='OK':
                abort(404 if reply.get('code')=='NOT_FOUND' else 400,'Feedback rejected for this state or role. Refresh the case.')
            operation_key('feedback',aid,True)
            return redirect(url_for('incident',aid=aid))

        def walk_call(kind,payload=None):
            if role!='sender':
                abort(403)
            try:
                reply=call(kind,payload)
            except (OSError,EOFError,ValueError):
                abort(503,'Walk action not confirmed. Reconnect and retry the same action; no offline delivery is claimed.')
            if reply.get('status')!='OK':
                abort(404 if reply.get('code')=='NOT_FOUND' else 400,'Walk request rejected. Check its state, interval and duration.')
            return reply

        @app.get('/walks')
        def my_walks():
            return render_template('walk_list.html',walks=walk_call('WALK_LIST')['walks'])

        @app.route('/walks/start',methods=['GET','POST'])
        def start_walk():
            if role!='sender':
                abort(403)
            session.setdefault('start_walk_key',str(uuid4()))
            if request.method=='POST':
                try:
                    payload=dict(action_id=request.form.get('action_id'),origin=request.form.get('origin'),destination=request.form.get('destination'),
                                 duration=int(request.form.get('duration','0')),interval=int(request.form.get('interval','0')))
                except ValueError:
                    abort(400)
                result=walk_call('WALK_START',payload)
                session['start_walk_key']=str(uuid4())
                return redirect(url_for('walk_detail',wid=result['id']))
            return render_template('walk_start.html',action_id=session['start_walk_key'])

        @app.get('/walks/<wid>')
        def walk_detail(wid):
            result=walk_call('WALK_GET',dict(walk_id=wid))
            if session.get('walk_keys_for')!=wid:
                session['walk_keys_for']=wid
                session['walk_keys']={a:str(uuid4()) for a in ('SAFE','HELP','ARRIVE','END')}
            return render_template('walk_detail.html',walk=result,keys=session['walk_keys'])

        @app.post('/walks/<wid>/action')
        def walk_action(wid):
            action=request.form.get('action')
            result=walk_call('WALK_ACTION',dict(walk_id=wid,action=action,action_id=request.form.get('action_id')))
            if 'walk_keys' in session:
                keys=dict(session['walk_keys']);keys[action]=str(uuid4());session['walk_keys']=keys
            if action=='HELP':
                identity.reconcile(outbox)
                link=next(l for l in result['links'] if l['kind']=='HELP')
                return redirect(url_for('incident',aid=link['alert_id']))
            return redirect(url_for('walk_detail',wid=wid))

        @app.route('/activate-demo', methods=['GET', 'POST'])
        def redeem_invite():
            invited_role = 'student' if role == 'sender' else 'responder'
            invite = config.get(f'{invited_role}_invite')
            if not config.get('hosted') or not invite:
                abort(404)
            error = None
            if request.method == 'POST':
                email = request.form.get('email', '').strip().lower()
                if not identity.limit(f'{invited_role}-invite', email, request.remote_addr or ''):
                    abort(429)
                try:
                    password = request.form.get('password', '')
                    if password != request.form.get('confirm_password'):
                        raise ValueError('Passwords must match.')
                    identity.redeem_invite(email, request.form.get('code', ''), password, invite, role=invited_role)
                    return redirect(url_for('login'))
                except ValueError as exc:
                    error = str(exc)
            return render_template('student_invite.html', error=error, invited_role=invited_role)

        @app.route('/register',methods=['GET','POST'])
        def register():
            error=None
            message=None
            if request.method=='POST':
                if not identity.limit('register',request.form.get('email','').lower().strip()[:254],request.remote_addr or ''):
                    abort(429)
                try:
                    if request.form.get('password') != request.form.get('confirm_password'):
                        raise ValueError('Passwords must match.')
                    identity.register(request.form.get('email',''),request.form.get('password',''))
                    message='If eligible, a verification challenge has been sent. Check your inbox.'
                except ValueError as exc:
                    error=str(exc)
            return render_template('identity.html',mode='register',error=error,message=message,mail_available=identity.mail is not None)

        @app.route('/verify',methods=['GET','POST'])
        def verify():
            error=message=None
            if request.method=='POST':
                if not identity.limit('verify',request.remote_addr or '',request.remote_addr or ''):
                    abort(429)
                try:
                    if request.form.get('resend'):
                        identity.challenge(request.form.get('email',''),'VERIFY')
                        message='If eligible, a fresh challenge has been sent.'
                    else:
                        identity.consume(request.form.get('challenge',''),'VERIFY')
                        message='Email verified. You can now sign in.'
                except ValueError as exc:
                    error=str(exc)
            return render_template('identity.html',mode='verify',error=error,message=message)

        @app.route('/recovery',methods=['GET','POST'])
        def recovery():
            message=None
            if request.method=='POST':
                if not identity.limit('reset',request.form.get('email','').lower().strip()[:254],request.remote_addr or ''):
                    abort(429)
                try:
                    identity.challenge(request.form.get('email',''),'RESET')
                except ValueError:
                    pass
                message='If an eligible verified account exists and mail is configured, a reset challenge has been sent.'
            return render_template('identity.html',mode='recovery',message=message)

        @app.route('/reset-password',methods=['GET','POST'])
        def reset_password():
            error=message=None
            if request.method=='POST':
                if not identity.limit('consume-reset',request.remote_addr or '',request.remote_addr or ''):
                    abort(429)
                try:
                    identity.consume(request.form.get('challenge',''),'RESET',request.form.get('password',''))
                    message='Password reset. Sign in again.'
                except ValueError as exc:
                    error=str(exc)
            return render_template('identity.html',mode='reset',error=error,message=message)

        @app.route('/profile',methods=['GET','POST'])
        def profile():
            error=None
            if request.method=='POST':
                if not identity.limit('change-password',g.user['id'],request.remote_addr or ''):
                    abort(429)
                try:
                    identity.change_password(session['sid'],request.form.get('current',''),request.form.get('password',''))
                    session.clear()
                    return redirect(url_for('login'))
                except ValueError as exc:
                    error=str(exc)
            return render_template('identity.html',mode='profile',error=error)
    if cyber:
        cyber_web.register(app,role,cyber,identity,outbox,call,operation_key)
    return app
