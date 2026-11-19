"""Single-instance HTTPS-proxied deployment; TCP/TLS stays private on loopback."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
from .database import connection
import tempfile
import threading

from flask import Flask, jsonify, render_template
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from .faults import Faults
from .sender_store import Outbox
from .sender_worker import Worker
from .server import AlertServer, request
from .server_store import Store
from .tls import create_certificate, client_context, server_context
from .web import create_app
from .identity import Identity, configured_mail
from .walks import Walks
from .rooms import Rooms


@contextmanager
def hosted_runtime(config, data_dir, enable_faults=False):
    """One process, one disk, one outbox worker; never use horizontal replicas."""
    data = Path(data_dir)
    demo_accounts = config.get('demo_accounts')
    if demo_accounts is not None:
        if not config.get('identity') or set(demo_accounts) != {'student', 'responder'}:
            raise ValueError('Demo mode requires exactly one student and one responder account')
        data /= 'password-demo'
    data.mkdir(parents=True, exist_ok=True)
    if config.get('identity'):
        for name in ('server.sqlite','outbox.sqlite'):
            source=data/name
            backup=data/'pre-v2-backup'/name
            if source.exists() and not backup.exists():
                backup.parent.mkdir(exist_ok=True)
                with connection(source.resolve().as_uri()+'?mode=ro',uri=True) as old, connection(backup) as saved:
                    old.backup(saved)
    evidence = Path(config.get('evidence_dir',data / 'artifacts'))
    reviewed = Path(__file__).resolve().parents[1] / 'docs/results'
    if not (evidence / 'latest.json').exists() and (reviewed / 'summary.json').exists():
        report = json.loads((reviewed / 'summary.json').read_text())
        report['source'] = 'Recorded local lab run; not a measurement of this hosted deployment.'
        run_dir = evidence / report['run_id']
        run_dir.mkdir(parents=True, exist_ok=True)
        for name in ('results.csv', 'summary.json', 'comparison.svg'):
            shutil.copyfile(reviewed / name, run_dir / name)
        evidence.joinpath('latest.json').write_text(json.dumps(report))
    settings = dict(config, hosted=config.get('hosted',True), combined=True, evidence_dir=str(evidence))
    enable_faults=enable_faults and not settings['hosted']
    faults = Faults(data / 'faults.json', enable_faults)
    identity = Identity(data/'server.sqlite',config['session_secret'],mail=config.get('mail',configured_mail())) if config.get('identity') else None
    if demo_accounts is not None:
        identity.seed_demo_accounts(demo_accounts)
    if enable_faults:
        faults.set('normal')
    with tempfile.TemporaryDirectory() as certs:
        # Private per-process certificate: verified on loopback, never the public HTTPS certificate.
        create_certificate(certs,valid_days=3650)
        context = client_context(certs)
        store=Store(data/'server.sqlite')
        walks=Walks(identity,store) if identity else None
        rooms=Rooms(identity,store) if identity else None
        with AlertServer(('127.0.0.1', 0), server_context(certs), store,
                         settings['sender_token'], settings['responder_token'], faults,identity,walks,rooms) as server:
            server_thread = threading.Thread(target=server.serve_forever, daemon=True)
            server_thread.start()
            def caller(role):
                def call(kind, payload=None, principal=None):
                    if role == 'sender' and faults.preset() == 'disconnect':
                        raise ConnectionError('Simulated sender disconnect')
                    return request(server.server_address, context, settings[role + '_token'], kind, payload,identity,principal)
                return call
            box = Outbox(data / 'outbox.sqlite')
            sender_call=caller('sender')
            def worker_call(kind,payload):
                return sender_call(kind,payload,dict(intent=payload['alert_id']) if identity else None)
            worker = Worker(box, worker_call,identity,walks.reconcile if walks else None)
            worker_thread = threading.Thread(target=worker.run, daemon=True)
            worker_thread.start()
            root = Flask(__name__)

            @root.get('/')
            def home():
                response = root.make_response(render_template('welcome.html',ephemeral_storage=settings.get('ephemeral_storage',False),identity_enabled=bool(identity),demo_login=demo_accounts is not None))
                response.headers['Cache-Control']='no-store'
                return response

            @root.get('/healthz')
            def health():
                try:
                    ready = request(server.server_address, context, settings['sender_token'], 'HEALTH')['status'] == 'OK' and worker_thread.is_alive()
                except (OSError, EOFError, ValueError):
                    ready = False
                response = jsonify(ready=ready)
                response.headers['Cache-Control'] = 'no-store'
                return response, 200 if ready else 503

            app = DispatcherMiddleware(root, {
                '/sender': create_app('sender', settings, caller('sender'), box, faults,identity),
                '/responder': create_app('responder', settings, caller('responder'),identity=identity),
            })
            try:
                yield app
            finally:
                worker.stop.set()
                worker_thread.join(timeout=10)
                server.shutdown()
                server_thread.join(timeout=10)


def main():
    from waitress import serve
    config = {key: os.environ['SAFESIGNAL_' + key.upper()]
              for key in ('sender_token', 'responder_token', 'session_secret')}
    if any(len(value) < 32 for value in config.values()) or len(set(config.values())) != 3:
        raise ValueError('Provide three distinct random secrets, each at least 32 characters')
    hosts = {h.strip() for h in os.environ.get('SAFESIGNAL_ALLOWED_HOSTS', '').split(',') if h.strip()}
    if os.environ.get('RENDER_EXTERNAL_HOSTNAME'):
        hosts.add(os.environ['RENDER_EXTERNAL_HOSTNAME'])
    if not hosts:
        raise ValueError('Configure explicit SAFESIGNAL_ALLOWED_HOSTS')
    config['allowed_hosts'] = tuple(hosts)
    config['identity'] = True
    config['mail'] = configured_mail() if os.environ.get('SAFESIGNAL_REGISTRATION_ENABLED')=='1' else None
    invite_file = Path(__file__).resolve().with_name('hosted_invite.json')
    if invite_file.is_file():
        config['student_invite'] = json.loads(invite_file.read_text(encoding='utf-8'))
    responder_invite = invite_file.with_name('hosted_responder_invite.json')
    if responder_invite.is_file():
        config['responder_invite'] = json.loads(responder_invite.read_text(encoding='utf-8'))
    demo_file = invite_file.with_name('hosted_demo_accounts.json')
    if demo_file.is_file():
        config['demo_accounts'] = json.loads(demo_file.read_text(encoding='utf-8'))
    config['ephemeral_storage'] = os.environ.get('SAFESIGNAL_EPHEMERAL_STORAGE')=='1'
    data_dir = os.environ['SAFESIGNAL_DATA_DIR']
    with hosted_runtime(config, data_dir, os.environ.get('ENABLE_DEMO_FAULTS') == '1') as app:
        # Only Render ingress reaches this listener. Trust its scheme, never forwarded host.
        serve(app,host='0.0.0.0',port=int(os.environ.get('PORT','10000')),threads=8,
              trusted_proxy='*',trusted_proxy_count=1,
              trusted_proxy_headers={'x-forwarded-proto'})


if __name__ == '__main__':
    main()
