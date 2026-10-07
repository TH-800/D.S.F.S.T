"""Read/write integration check in an isolated test environment.

Starts the built frontend and real FastAPI routes with an in-memory Mongo
replacement. Requires free ports 3000, 8000 and 8008. Never starts injections.
Run after building the frontend. Requires tests/requirements.txt.
"""
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
for port in (3000, 8000, 8008):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', port))

commands = [
    [sys.executable, '-c', 'import mongomock, metrics_api, uvicorn; metrics_api._mongo_client=mongomock.MongoClient(); uvicorn.run(metrics_api.app,host="127.0.0.1",port=8008)'],
    [sys.executable, '-m', 'uvicorn', 'ExperimentMonitor:app', '--host', '127.0.0.1', '--port', '8000'],
    ['node', 'dist/index.cjs'],
]
processes = []
with tempfile.TemporaryFile() as log:
    try:
        for i, command in enumerate(commands):
            env = {**os.environ, 'NODE_ENV': 'production', 'PORT': '3000'}
            env.pop('DSFST_VM_IP', None)
            processes.append(subprocess.Popen(command, cwd=ROOT / 'dsft-frontend' if i == 2 else ROOT, env=env, stdout=log, stderr=log))
        for _ in range(100):
            try:
                if requests.get('http://127.0.0.1:3000/api/8008/health', timeout=.5).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Test servers did not start')
        base = 'http://127.0.0.1:3000/api/8008'
        payload = {'name': 'Gateway test', 'failure_type': 'cpu_stress', 'parameters': {'cpu_percent': 25, 'duration_seconds': 10}}
        response = requests.post(base + '/presets', json=payload, timeout=5)
        assert response.status_code == 201, response.text
        saved = response.json()
        assert requests.get(base + '/presets/' + saved['preset_id'], timeout=5).json() == saved
        assert requests.get(base + '/presets', timeout=5).json() == [saved]
        assert requests.get(base + '/experiments', timeout=5).json() == []
        status = requests.get('http://127.0.0.1:3000/api/8000/status', timeout=5)
        assert status.status_code == 200, status.text
        assert status.json()['services']['8008']['online'] is True
        print('PASS: built frontend gateway → actual FastAPI save/list/load routes → in-memory Mongo; actual monitor; no experiments created.')
    except Exception:
        log.seek(0)
        print(log.read().decode(), file=sys.stderr)
        raise
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
