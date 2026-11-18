"""Generate local-only demo secrets and certificate; never overwrite existing config."""
import json
from pathlib import Path
import secrets
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from safesignal.tls import create_certificate


def main():
    Path('local').mkdir(exist_ok=True)
    path = Path('local/config.json')
    if path.exists():
        print('Existing local configuration preserved.')
        return
    create_certificate('certs')
    config = {name: secrets.token_urlsafe(32) for name in ('sender_token', 'responder_token', 'session_secret')}
    path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    print('Created ignored local/config.json and certs/. Certificate valid 30 days.')


if __name__ == '__main__':
    main()
