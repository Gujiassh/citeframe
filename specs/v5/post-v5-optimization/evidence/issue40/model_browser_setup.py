"""Prepare only isolated issue40 A generation settings; never invokes a model.

Requires runtime/run.py to allowlist http://127.0.0.1:18481 for 127.0.0.1/32,
with that isolated API restarted. Do not rerun during a controller settings edit.
"""
import json
from pathlib import Path
import runpy
import sys
from uuid import uuid4

import httpx

repo = Path(__file__).resolve().parents[5]
root = repo / '.local-runtime/artifacts/issue40-dev/runtime'
sys.argv = ['run.py', 'inspect']
runtime = runpy.run_path(str(root / 'run.py'))
fixture = json.loads((root / 'fixture.json').read_text())
headers = {'x-user-id': fixture['actors']['owner'],
           'x-ai-pdf-internal-token': runtime['c']['internal_token']}
url = 'http://127.0.0.1:18400/v1/workspaces/' + fixture['A'] + '/model-settings'
with httpx.Client(timeout=30) as client:
    response = client.get(url, headers=headers)
    assert response.status_code == 200
    before = response.json()
    generation = before['generation']
    base = 'http://127.0.0.1:18481/v1'
    command = dict(action='save', expectedRevision=generation['revision'],
                   protocol='openai_chat_completions', baseUrl=base,
                   model='issue40-synthetic-generation-no-calls')
    retains_key = (generation['source'] == 'workspace' and generation['baseUrl'] == base
                   and generation['apiKeyConfigured'])
    if not retains_key:
        keyfile = root / 'synthetic-provider.json'
        if not keyfile.exists():
            keyfile.write_text(json.dumps({'apiKey': 'issue40-synthetic-local-' + uuid4().hex}))
        command['apiKey'] = json.loads(keyfile.read_text())['apiKey']
    response = client.patch(url, headers=headers, json={'generation': command})
    assert response.status_code == 200, response.status_code
    after = client.get(url, headers=headers).json()
    assert after['generation']['apiKeyConfigured']
    assert after['embedding'] == before['embedding']
    print(json.dumps({'status': 200, 'generation': after['generation'], 'retainedExistingKey': retains_key}))
