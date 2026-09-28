"""Run from the repository root against the issue40 starting baseline."""
import json
import sys

sys.path[:0] = [
    "apps/api/tests", "apps/api/src", "packages/backend-contracts/src",
    "packages/backend-persistence/src", "packages/research-persistence/src",
]

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from ai_pdf_api.db.session import get_db
from ai_pdf_api.routers.deps import require_user_id
import subprocess
import types
baseline = types.ModuleType("issue40_baseline_model_settings")
exec(subprocess.check_output([
    "git", "show", "8812fda4d69b7f0e654e749c357fa05b5e8da72f:apps/api/src/ai_pdf_api/routers/model_settings.py",
], text=True), baseline.__dict__)
_require_owner = baseline._require_owner
SecretSafeRoute = baseline.SecretSafeRoute
from ai_pdf_api.schemas.model_settings import UpdateModelSettingsRequest
from test_workspace_model_settings import configured_api, headers


def main():
    monkeypatch = pytest.MonkeyPatch()
    fixture = configured_api.__wrapped__(monkeypatch)
    _, db = next(fixture)
    baseline_app = FastAPI()
    baseline_app.include_router(baseline.router)
    baseline_app.dependency_overrides[get_db] = lambda: db
    client = TestClient(baseline_app)
    try:
        def owner(user_id=Depends(require_user_id), db=Depends(get_db)):
            _require_owner(db, "w1", user_id)

        app = FastAPI()
        app.router.route_class = SecretSafeRoute
        app.dependency_overrides[get_db] = lambda: db

        @app.patch("/candidate")
        def candidate(payload: UpdateModelSettingsRequest, access=Depends(owner)):
            return {}

        results = []
        with TestClient(app) as new:
            for user in ("owner", "member", "outsider"):
                old = client.patch("/v1/workspaces/w1/model-settings", headers=headers(user), json={})
                changed = new.patch("/candidate", headers=headers(user), json={})
                results.append({
                    "syntheticRole": user, "requestBody": {},
                    "baseline": {"status": old.status_code, "body": old.json()},
                    "dependencyCandidate": {"status": changed.status_code, "body": changed.json()},
                })
        print(json.dumps(results, indent=2))
    finally:
        client.close()
        fixture.close()
        monkeypatch.undo()


if __name__ == "__main__":
    main()
