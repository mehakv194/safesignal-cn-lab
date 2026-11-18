"""Entry points for isolated server, sender and responder processes."""
import argparse
import json
import os
from pathlib import Path
import threading

from .sender_store import Outbox
from .sender_worker import Worker
from .server import AlertServer, request
from .server_store import Store
from .tls import client_context, server_context
from .web import create_app
from .faults import Faults


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('role', choices=['server', 'sender', 'responder'])
    args = parser.parse_args()
    config = json.loads(Path('local/config.json').read_text())
    for key in config:
        config[key] = os.environ.get('SAFESIGNAL_' + key.upper(), config[key])
    faults = Faults('local/faults.json', os.environ.get('ENABLE_DEMO_FAULTS') == '1')
    if args.role == 'server':
        with AlertServer(('127.0.0.1', 9443), server_context('certs'), Store('local/server.sqlite'),
                         config['sender_token'], config['responder_token'], faults) as server:
            server.serve_forever()
    else:
        context = client_context('certs')
        def call(kind, payload=None):
            if args.role == 'sender' and faults.preset() == 'disconnect':
                raise ConnectionError('Simulated sender disconnect')
            return request(('127.0.0.1', 9443), context, config[args.role + '_token'], kind, payload)
        box = Outbox('local/outbox.sqlite') if args.role == 'sender' else None
        if box:
            worker = Worker(box, call)
            threading.Thread(target=worker.run, daemon=True).start()
        app = create_app(args.role, config, call, box, faults)
        app.run(host='127.0.0.1', port=5001 if box else 5002, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()
