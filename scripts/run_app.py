"""Run both dashboards at one local address. Stop run_demo.py before starting."""
import argparse
import json
from pathlib import Path
import secrets
import socket
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safesignal.hosted import hosted_runtime


if __name__=='__main__':
    from waitress import serve
    parser=argparse.ArgumentParser()
    parser.add_argument('--enable-demo-faults',action='store_true')
    parser.add_argument('--enable-trust-lab',action='store_true')
    parser.add_argument('--classroom-demo', action='store_true', help='Run an isolated, loopback-only Network Lab with two synthetic accounts')
    args=parser.parse_args()
    port = 5070 if args.classroom_demo else 5000
    for checked_port in ((port,) if args.classroom_demo else (9443, port)):
        with socket.socket() as sock:
            sock.settimeout(.3)
            if sock.connect_ex(('127.0.0.1',checked_port))==0:
                raise SystemExit('Stop the existing demo/app before starting another worker for this outbox.')
    root=Path(__file__).resolve().parents[1]
    data = root / 'local'
    if args.classroom_demo:
        from argon2 import PasswordHasher
        hasher = PasswordHasher()
        data /= 'classroom-network-lab'
        config = {key: secrets.token_urlsafe(32) for key in ('sender_token', 'responder_token', 'session_secret')}
        config.update(mail=None, demo_accounts={
            'student': hasher.hash('Student-network-demo'),
            'responder': hasher.hash('Responder-network-demo'),
        })
    else:
        config=json.loads((data/'config.json').read_text())
        config['evidence_dir'] = str(root/'artifacts')
    config.update(hosted=False,identity=True,trust_lab=args.enable_trust_lab,allowed_hosts=('127.0.0.1','localhost'))
    with hosted_runtime(config, data, args.enable_demo_faults or args.classroom_demo) as app:
        print(f'SafeSignal: http://127.0.0.1:{port} — one app, sender and responder dashboards.',flush=True)
        serve(app,host='127.0.0.1',port=port,threads=8)
