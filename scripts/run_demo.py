import os
import argparse
from pathlib import Path
import subprocess
import sys
import time
import socket


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    parser = argparse.ArgumentParser()
    parser.add_argument('--enable-demo-faults', action='store_true')
    args = parser.parse_args()
    with socket.socket() as sock:
        sock.settimeout(.3)
        if sock.connect_ex(('127.0.0.1',5000))==0:
            raise SystemExit('Stop the single campus app before starting the separate-process lab demo.')
    os.environ['ENABLE_DEMO_FAULTS'] = '1' if args.enable_demo_faults else '0'
    if args.enable_demo_faults:
        Path('local/faults.json').write_text('{"preset":"normal"}')
    if not Path('local/config.json').exists():
        raise SystemExit('Run scripts/init_demo.py first.')
    processes = []
    try:
        for role in ('server', 'sender', 'responder'):
            processes.append(subprocess.Popen([sys.executable, '-m', 'safesignal.runtime', role]))
            time.sleep(0.5)
        print('SIMULATION ONLY. Sender http://127.0.0.1:5001 | Responder http://127.0.0.1:5002', flush=True)
        print('Login tokens: ignored local/config.json. Ctrl+C stops all three processes.', flush=True)
        while all(p.poll() is None for p in processes):
            time.sleep(0.5)
        raise SystemExit('A demo process stopped. Check its error output above.')
    except KeyboardInterrupt:
        pass
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
        for process in processes:
            process.wait(timeout=10)
