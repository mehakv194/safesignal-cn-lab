import hmac
import secrets
import time

from flask import Flask, abort, redirect, render_template, request, session, url_for, send_from_directory
from pathlib import Path
from datetime import datetime, timezone

from .models import SEVERITIES, CATEGORIES, INCIDENT_STATES, RESPONSE_TEAMS, new_alert
from .dashboard import summarize


def create_app(role, config, call, outbox=None, faults=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=config['session_secret'], MAX_CONTENT_LENGTH=8192,
                      SESSION_COOKIE_NAME='safesignal_' + role,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=config.get('hosted', False),
                      SESSION_COOKIE_PATH='/' + role if config.get('hosted') else '/')
    login_attempts = []
    evidence_dir = Path(config.get('evidence_dir', 'artifacts'))

    @app.context_processor
    def deployment_context():
        return {'hosted': config.get('hosted', False), 'combined':config.get('combined',False), 'role':role,'categories':CATEGORIES,
                'severities':SEVERITIES,'incident_states':INCIDENT_STATES,'teams':RESPONSE_TEAMS,
                'today':datetime.now(timezone.utc).strftime('%d %b %Y'), 'local_role_url':
                ('http://127.0.0.1:5002/' if role=='sender' else 'http://127.0.0.1:5001/')}

    @app.template_filter('stamp')
    def stamp(value):
        if not value:
            return '—'
        return datetime.fromisoformat(value).strftime('%d %b · %H:%M UTC')

    @app.before_request
    def guard():
        if request.host.split(':')[0] not in config.get('allowed_hosts', ('127.0.0.1', 'localhost')):
            abort(400)
        if config.get('hosted') and not request.is_secure:
            abort(400)
        session.setdefault('csrf', secrets.token_urlsafe(24))
        if request.method == 'POST':
            if not hmac.compare_digest(session['csrf'], request.form.get('csrf', '')):
                abort(400)
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
        return render_template('unavailable.html',view='overview'),503

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
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
        session.clear()
        return redirect(url_for('login'))

    @app.get('/')
    def home():
        error = None
        reachable = False
        rows = []
        overview = dict(summarize([]),activity=[],duplicates=0)
        try:
            if role == 'sender':
                rows = outbox.rows()
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
        return render_template('home.html', role=role, rows=rows, error=error, severities=SEVERITIES,
                               faults=faults, preset=faults.preset() if faults else 'normal',
                               offset=request.args.get('offset', '0'), reachable=reachable,overview=overview,
                               view=request.args.get('view','overview'))

    @app.get('/incident/<aid>')
    def incident(aid):
        reply = None
        events = []
        events_source = 'local'
        if role=='sender':
            row = next((r for r in outbox.rows() if r['alert_id']==aid),None)
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
        return render_template('incident.html',incident=reply,events=events[-8:],events_source=events_source,view='incidents')

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
            outbox.enqueue(new_alert(severity,description,location,category))
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
        return redirect(url_for('incident',aid=aid))

    @app.post('/simulation')
    def simulation():
        if role != 'sender' or not faults or not faults.enabled:
            abort(403)
        try:
            faults.set(request.form.get('preset'))
        except ValueError:
            abort(400)
        return redirect(url_for('home'))

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
            outbox.enqueue(new_alert(request.form.get('severity'), request.form.get('description', ''), request.form.get('location', ''),request.form.get('category','SAFETY')))
        except ValueError:
            abort(400, 'Use a valid severity, description of 10–300 characters and location up to 120 characters.')
        return redirect(url_for('home'))

    @app.post('/retry/<aid>')
    def retry(aid):
        if role != 'sender':
            abort(403)
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

    return app
