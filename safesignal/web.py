import hmac
import secrets
import time

from flask import Flask, abort, redirect, render_template, request, session, url_for, send_from_directory
from pathlib import Path

from .models import SEVERITIES, new_alert


def create_app(role, config, call, outbox=None, faults=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=config['session_secret'], MAX_CONTENT_LENGTH=8192,
                      SESSION_COOKIE_NAME='safesignal_' + role,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
    login_attempts = []

    @app.before_request
    def guard():
        if request.host.split(':')[0] not in ('127.0.0.1', 'localhost'):
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
        try:
            if role == 'sender':
                rows = outbox.rows()
                for row in rows:
                    row['timeline'] = outbox.timeline(row['alert_id'])
            else:
                offset = max(0, int(request.args.get('offset', '0')))
                reply = call('LIST_ALERTS', {'offset': offset})
                if reply['status'] != 'OK':
                    raise ValueError('Backend rejected request')
                rows = reply['alerts']
                rows.sort(key=lambda r: (SEVERITIES.index(r['severity']), r['server_received_at']))
                rows = [dict(r, alert=r, status=r['code'], timeline=call('GET_AUDIT', {'alert_id': r['alert_id']}).get('events', [])) for r in rows]
        except (OSError, EOFError, ValueError):
            rows, error = [], 'TLS backend unavailable. Saved sender alerts remain on disk.'
        return render_template('home.html', role=role, rows=rows, error=error, severities=SEVERITIES,
                               faults=faults, preset=faults.preset() if faults else 'normal',
                               offset=request.args.get('offset', '0'))

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
        path = Path('artifacts/latest.json')
        report = json.loads(path.read_text()) if path.exists() else None
        return render_template('evidence.html', role=role, report=report)

    @app.get('/evidence/<filename>')
    def evidence_file(filename):
        if filename not in ('results.csv', 'summary.json', 'comparison.svg'):
            abort(404)
        import json
        path = Path('artifacts/latest.json')
        if not path.exists():
            abort(404)
        run_id = json.loads(path.read_text())['run_id']
        return send_from_directory(Path('artifacts').resolve() / run_id, filename)

    @app.post('/submit')
    def submit():
        if role != 'sender':
            abort(403)
        try:
            outbox.enqueue(new_alert(request.form.get('severity'), request.form.get('description', ''), request.form.get('location', '')))
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
