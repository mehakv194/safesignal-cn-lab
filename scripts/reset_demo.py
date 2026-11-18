"""Archive synthetic databases, never delete them. Stop demo processes first."""
from datetime import datetime, timezone
from pathlib import Path
import socket


def archive_databases(local):
    files = [p for p in local.glob('*.sqlite*') if p.is_file()]
    if not files:
        return None
    archive = local / ('archive-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    archive.mkdir()
    for path in files:
        path.rename(archive / path.name)
    return archive


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    for port in (9443, 5001, 5002):
        with socket.socket() as sock:
            sock.settimeout(.5)
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                raise SystemExit('Stop all demo processes before archiving their databases.')
    local = root / 'local'
    archive = archive_databases(local)
    if archive:
        print(f'Archived synthetic database files to {archive}')
    else:
        print('No demo databases to archive.')
    (local / 'faults.json').unlink(missing_ok=True)
