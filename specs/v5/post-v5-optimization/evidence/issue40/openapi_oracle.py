"""Compare issue40 OpenAPI with the Git baseline without modifying any worktree."""
import json
import os
import subprocess
import sys
from pathlib import Path

BASE = '8812fda4d69b7f0e654e749c357fa05b5e8da72f'
ROOT = Path(__file__).resolve().parents[5]


def compare(output: Path):
    overlay = output / 'baseline-source'
    for package in ('ai_pdf_api', 'ai_pdf_api/routers'):
        path = overlay / package
        path.mkdir(parents=True, exist_ok=True)
        (path / '__init__.py').write_text('from pkgutil import extend_path\n__path__ = extend_path(__path__, __name__)\n')
    for name in ('assets', 'chat', 'deps', 'evaluation', 'jobs', 'model_settings', 'notes', 'research', 'workspaces'):
        source = f'apps/api/src/ai_pdf_api/routers/{name}.py'
        (overlay / 'ai_pdf_api/routers' / f'{name}.py').write_bytes(subprocess.check_output(['git', 'show', f'{BASE}:{source}'], cwd=ROOT))
    paths = [ROOT / p for p in ('apps/api/src', 'packages/backend-contracts/src', 'packages/backend-persistence/src', 'packages/research-persistence/src')]
    for label, extra in (('baseline', [overlay]), ('after', [])):
        environment = {**os.environ, 'PYTHONPATH': os.pathsep.join(map(str, [*extra, *paths]))}
        target = output / f'openapi-{label}.json'
        command = 'import json; from pathlib import Path; from ai_pdf_api.main import app; Path(' + repr(str(target)) + ').write_text(json.dumps(app.openapi(), sort_keys=True), encoding="utf-8")'
        subprocess.run([sys.executable, '-c', command], env=environment, cwd=ROOT, check=True)
    before = json.loads((output / 'openapi-baseline.json').read_text())
    after = json.loads((output / 'openapi-after.json').read_text())
    for document in (before, after):
        for operations in document['paths'].values():
            for operation in operations.values():
                if 'parameters' in operation:
                    operation['parameters'].sort(key=lambda parameter: (parameter['in'], parameter['name']))
    assert before == after, 'OpenAPI differs beyond parameter presentation order'
    return {'baseline': BASE, 'operations': sum(len(ops) for ops in before['paths'].values()), 'comparison': 'exact equality after sorting parameter presentation order', 'result': 'pass'}


if __name__ == '__main__':
    output = Path(sys.argv[1]).resolve()
    result = compare(output)
    (Path(__file__).parent / 'openapi-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
