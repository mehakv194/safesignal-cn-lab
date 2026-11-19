"""Run both dashboards at one local address. Stop run_demo.py before starting."""
import argparse
import json
from pathlib import Path
import socket
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safesignal.hosted import hosted_runtime


if __name__=='__main__':
    from waitress import serve
    parser=argparse.ArgumentParser()
    parser.add_argument('--enable-demo-faults',action='store_true')
    parser.add_argument('--enable-trust-lab',action='store_true')
    args=parser.parse_args()
    for port in (9443,5000):
        with socket.socket() as sock:
            sock.settimeout(.3)
            if sock.connect_ex(('127.0.0.1',port))==0:
                raise SystemExit('Stop the existing demo/app before starting another worker for this outbox.')
    root=Path(__file__).resolve().parents[1]
    config=json.loads((root/'local/config.json').read_text())
    config.update(hosted=False,identity=True,trust_lab=args.enable_trust_lab,allowed_hosts=('127.0.0.1','localhost'),evidence_dir=str(root/'artifacts'))
    with hosted_runtime(config,root/'local',args.enable_demo_faults) as app:
        print('SafeSignal: http://127.0.0.1:5000 — one app, sender and responder dashboards.',flush=True)
        serve(app,host='127.0.0.1',port=5000,threads=8)
