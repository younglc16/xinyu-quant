"""Run the shipped launcher in a temporary profile and verify daily and weekly demo data."""
import json
from pathlib import Path
import queue
import re
import subprocess
import sys
import tempfile
from threading import Thread
from time import sleep
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def check():
    with tempfile.TemporaryDirectory() as directory:
        process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'run.py'), '--no-browser', '--data-dir', directory],
            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8',
        )
        lines = queue.Queue()

        def read_lines():
            for line in process.stdout:
                lines.put(line.rstrip())

        reader = Thread(target=read_lines, daemon=True)
        reader.start()
        try:
            port = None
            for _ in range(10):
                line = lines.get(timeout=10)
                found = re.search(r'127\.0\.0\.1:(\d+)', line)
                if found:
                    port = found.group(1)
                    break
            assert port, 'Launcher did not print its loopback address'
            base = f'http://127.0.0.1:{port}'

            def get(path):
                with urlopen(base + path, timeout=3) as response:
                    return response.read()

            for _ in range(60):
                try:
                    health = json.loads(get('/api/health'))
                    break
                except OSError:
                    sleep(.25)
            else:
                raise RuntimeError('Local service did not start')
            assert health['status'] == 'ok'
            assert json.loads(get('/api/v3/bootstrap'))['demo'] is True
            assert b'/assets/main.js' in get('/')
            assert b'chartSignalMode' in get('/assets/main.js')
            for period in ('daily', 'weekly'):
                for _ in range(60):
                    result = json.loads(get('/api/v3/analysis/NVDA?period=' + period))
                    if result['data'] and result['state'] == 'ready':
                        break
                    assert result['state'] != 'error', result['error']
                    sleep(.25)
                else:
                    raise RuntimeError(f'Missing {period} data')
                data = result['data']
                assert data['period'] == period
                assert data['resonance']['available']
                assert data['resonance']['signals']
                assert '合成演示' in data['source']
                assert all(s['time'] in {r['time'][:10] for r in data['chart']} for s in data['resonance']['signals'])
        finally:
            process.terminate()
            process.wait(timeout=15)
            reader.join(timeout=3)
            if process.stdout:
                process.stdout.close()
    print('Local demo launch, daily/weekly signals and frontend verified.')


if __name__ == '__main__':
    check()
