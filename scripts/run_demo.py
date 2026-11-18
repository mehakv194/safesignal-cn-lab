import os
from pathlib import Path
import subprocess
import sys
import time


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
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
