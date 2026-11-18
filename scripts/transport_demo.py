"""Run standalone TLS server, or submit one synthetic alert (--send)."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safesignal.models import new_alert
from safesignal.server import AlertServer, request
from safesignal.server_store import Store
from safesignal.tls import server_context, client_context


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true')
    args = parser.parse_args()
    config = json.loads(Path('local/config.json').read_text())
    if args.send:
        print(request(('127.0.0.1', 9443), client_context('certs'), config['sender_token'],
                      'SUBMIT_ALERT', new_alert('LOW', 'TEST ONLY: transport smoke alert')))
    else:
        with AlertServer(('127.0.0.1', 9443), server_context('certs'), Store('local/server.sqlite'),
                         config['sender_token'], config['responder_token']) as server:
            print('Synthetic lab TLS server: 127.0.0.1:9443')
            try:
                server.serve_forever()
            except KeyboardInterrupt:
                pass
