"""Real PG first-save/CAS/revocation using independent connections and production API."""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("CITEFRAME_SERVICE_ADMIN_URL"),
    reason="requires isolated PostgreSQL/S3 service acceptance environment",
)


def test_default_policy_report_two_connection_editing(tmp_path):
    from ai_pdf_api.models import (
        HumanDecision,
        ResearchArtifact,
        ResearchReportEdit,
        ResearchRun,
        WorkspaceMembership,
    )
    from ai_pdf_api.schemas.research_report_edit import SaveResearchReportEditRequest
    from ai_pdf_api.services import storage
    from ai_pdf_api.services.research import ResearchError
    from ai_pdf_api.services.research.research_report_edit import save_report_edit
    from ai_pdf_worker.r800_acceptance_common import IDS
    from ai_pdf_worker.r800_acceptance_fixture import seed_state
    from research_service_support import ServiceHarness, api_client, create_run, headers
    from sqlalchemy import delete, select, text

    h = ServiceHarness(tmp_path / "edits")
    h.migrate()
    client, sessions = api_client(h)
    seed_state(
        sessions, uploader=storage.upload_bytes, cleanup=storage.delete_object_if_exists
    )
    run_id = create_run(client, "service-default-v3-edit")
    # The default create path must advance without any decision POST.
    h.worker(run_id)
    with sessions() as db:
        run = db.get(ResearchRun, run_id)
        assert run.status == "running"
        decisions = list(
            db.scalars(select(HumanDecision).where(HumanDecision.run_id == run_id))
        )
        assert len(decisions) == 2
        assert all(
            d.status == "submitted"
            and d.decision_origin == "policy"
            and d.decided_by_user_id is None
            for d in decisions
        )
    h.worker(run_id, mode="one")
    with sessions() as db:
        assert db.get(ResearchRun, run_id).status == "completed"
        artifact = db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == run_id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        original_id, original_hash, original_key = (
            artifact.id,
            artifact.content_sha256,
            artifact.object_key,
        )
    original = storage.download_bytes(original_key)
    assert hashlib.sha256(original).hexdigest() == original_hash
    url = f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}/report-edit"
    base = {"originalArtifactId": original_id, "originalSha256": original_hash}
    bad = client.put(
        url,
        headers=headers("obsolete-original-first"),
        json={
            **base,
            "originalSha256": "0" * 64,
            "expectedVersion": 0,
            "markdown": "retained local draft",
        },
    )
    assert (
        bad.status_code == 409
        and bad.json()["error"]["code"] == "report_edit_base_conflict"
    )
    with sessions() as db:
        assert db.get(ResearchReportEdit, run_id) is None
    evidence = []
    for version in (0, 1):
        barrier = Barrier(2)

        def save(editor, barrier=barrier, version=version):
            with sessions() as db:
                pid = db.scalar(text("SELECT pg_backend_pid()"))
                barrier.wait(timeout=10)
                try:
                    result = save_report_edit(
                        db,
                        workspace_id=IDS["workspace"],
                        run_id=run_id,
                        user_id=IDS["creator"],
                        payload=SaveResearchReportEditRequest(
                            **base,
                            expectedVersion=version,
                            markdown=f"# Editor {editor} version {version}",
                        ),
                    )
                    return {"pid": pid, "status": 200, "response": result}
                except ResearchError as error:
                    db.rollback()
                    return {"pid": pid, "status": error.status_code, "code": error.code}

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, ("A", "B")))
        assert len({r["pid"] for r in results}) == 2
        assert sorted(r["status"] for r in results) == [200, 409]
        winner = next(r["response"] for r in results if r["status"] == 200)
        assert (
            winner["version"] == version + 1
            and winner["verificationStatus"] == "unverified"
        )
        assert (
            next(r["code"] for r in results if r["status"] == 409)
            == "report_edit_version_conflict"
        )
        refreshed = client.get(url, headers=headers("refresh-after-cas"))
        assert (
            refreshed.status_code == 200
            and refreshed.json()["markdown"] == winner["markdown"]
        )
        evidence.append(results)
    # A committed revocation on a second physical connection must prevent further writes.
    with sessions() as revoker:
        revoke_pid = revoker.scalar(text("SELECT pg_backend_pid()"))
        revoker.execute(
            delete(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == IDS["workspace"],
                WorkspaceMembership.user_id == IDS["creator"],
            )
        )
        revoker.commit()
    response = client.put(
        url,
        headers=headers("revoked-editor-save"),
        json={**base, "expectedVersion": 2, "markdown": "must not persist"},
    )
    assert response.status_code in (403, 404), response.text
    with sessions() as db:
        edit = db.get(ResearchReportEdit, run_id)
        assert edit.version == 2 and edit.markdown == winner["markdown"]
        assert (
            edit.base_artifact_id == original_id
            and edit.base_artifact_sha256 == original_hash
        )
    assert storage.download_bytes(original_key) == original
    h.snapshot("edits-final")
    (tmp_path / "edit-evidence.json").write_text(
        json.dumps(
            {
                "head": h.command(["git", "rev-parse", "HEAD"]).stdout.strip(),
                "runId": run_id,
                "workers": h.processes,
                "connections": evidence,
                "revokerPid": revoke_pid,
                "revokedStatus": response.status_code,
                "result": "pass",
            },
            default=str,
            indent=2,
        ),
        encoding="utf-8",
    )

