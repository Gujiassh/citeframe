from __future__ import annotations

import importlib.util
import hashlib
from datetime import UTC, datetime
from pathlib import Path

from ai_pdf_api.models import ResearchReportEdit
from ai_pdf_api.services.research import ResearchError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect

from research_router_test_support import auth, seed_final_artifact_detail


def ready_report(research_app):
    client, db, context = research_app
    run, artifact, claim, steps = seed_final_artifact_detail(client, db, context)
    context["objectStore"][artifact.object_key] = b"# Citeframe Research Report\n"
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    run.updated_at = run.finished_at
    db.commit()
    return client, db, context, run, artifact


def path(context, run):
    return f"/v1/workspaces/{context['workspace'].id}/research-runs/{run.id}/report-edit"


def test_report_edit_permissions_versions_refresh_and_original_integrity(research_app):
    client, db, context, run, artifact = ready_report(research_app)
    url = path(context, run)
    original = context["objectStore"][artifact.object_key]
    assert client.get(url, headers=auth(context["stranger"])).status_code == 404
    assert client.get(url, headers=auth(context["member"])).json()["version"] == 0
    assert client.get(url, headers=auth(context["owner"])).status_code == 200
    assert client.put(url, headers=auth(context["member"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "member"}).status_code == 403
    assert client.put(url, headers=auth(context["owner"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "owner"}).status_code == 403
    saved = client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "# Edited"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["version"] == 1
    assert saved.json()["verificationStatus"] == "unverified"
    assert saved.json()["originalArtifactId"] == artifact.id
    assert saved.json()["originalSha256"] == artifact.content_sha256
    assert db.get(ResearchReportEdit, run.id).actor_user_id == context["creator"].id
    assert client.get(url, headers=auth(context["member"])).json()["markdown"] == "# Edited"
    conflict = client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "stale"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "report_edit_version_conflict"
    assert client.get(url, headers=auth(context["creator"])).json()["markdown"] == "# Edited"
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 1, "markdown": "# Revised"}).json()["version"] == 2
    assert context["objectStore"][artifact.object_key] == original
    assert artifact.content_sha256 == saved.json()["originalSha256"]
    context["objectStore"][artifact.object_key] = b"tampered"
    assert client.get(url, headers=auth(context["creator"])).status_code == 410
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 2, "markdown": "bad"}).status_code == 410
    assert db.get(ResearchReportEdit, run.id).version == 2


def test_report_edit_requires_completed_final_markdown_and_valid_content(research_app):
    client, db, context, run, artifact = ready_report(research_app)
    url = path(context, run)
    run.status = "running"
    run.finished_at = None
    db.commit()
    assert client.get(url, headers=auth(context["creator"])).status_code == 409
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "valid"}).status_code == 409
    run.status = "completed"
    run.finished_at = datetime.now(UTC)
    db.commit()
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "   "}).status_code == 422
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "x" * 200_001}).status_code == 422
    assert db.get(ResearchReportEdit, run.id) is None



def test_report_edit_refuses_rebinding_to_replaced_original(research_app):
    client, db, context, run, artifact = ready_report(research_app)
    url = path(context, run)
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 0, "markdown": "# Mine"}).status_code == 200
    replacement = b"# Replacement\n"
    artifact.byte_size = len(replacement)
    artifact.content_sha256 = hashlib.sha256(replacement).hexdigest()
    context["objectStore"][artifact.object_key] = replacement
    db.commit()
    assert client.get(url, headers=auth(context["creator"])).json()["error"]["code"] == "report_edit_base_conflict"
    result = client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion": 1, "markdown": "# New"})
    assert result.status_code == 409
    assert db.get(ResearchReportEdit, run.id).markdown == "# Mine"


def test_report_edit_migration_adds_only_edit_table():
    from ai_pdf_api.db.base import Base
    from sqlalchemy import create_engine

    filename = Path(__file__).parents[1] / "alembic/versions/o9c0d1e2f3a4_add_research_report_edits.py"
    spec = importlib.util.spec_from_file_location("report_edit_migration", filename)
    assert spec and spec.loader
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == "n8b9c0d1e2f3"
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        Base.metadata.tables["research_report_edits"].drop(connection)
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) - before == {"research_report_edits"}
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert set(inspect(connection).get_table_names()) == before


def test_report_edit_refreshes_stale_identity_before_version_check(research_app):
    from sqlalchemy import update
    client, db, context, run, artifact = ready_report(research_app)
    url=path(context, run)
    assert client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion":0,"markdown":"one"}).status_code == 200
    held=db.get(ResearchReportEdit,run.id)
    db.execute(update(ResearchReportEdit).where(ResearchReportEdit.run_id==run.id)
        .values(version=2,markdown="other session").execution_options(synchronize_session=False))
    db.commit()
    assert held.version == 1
    result=client.put(url, headers=auth(context["creator"]), json={"originalArtifactId": artifact.id, "originalSha256": artifact.content_sha256, "expectedVersion":1,"markdown":"stale"})
    assert result.status_code == 409
    db.refresh(held)
    assert held.version == 2 and held.markdown == "other session"


def test_report_edit_service_rechecks_membership_after_run_lock(research_app):
    from sqlalchemy import delete
    from ai_pdf_api.models import WorkspaceMembership
    from ai_pdf_api.services.research.research_report_edit import save_report_edit
    from ai_pdf_api.schemas.research_report_edit import SaveResearchReportEditRequest
    import pytest
    _, db, context, run, artifact=ready_report(research_app)
    db.execute(delete(WorkspaceMembership).where(WorkspaceMembership.user_id == context["creator"].id))
    db.commit()
    with pytest.raises(ResearchError) as caught:
        save_report_edit(db,workspace_id=run.workspace_id,run_id=run.id,user_id=context["creator"].id,
            payload=SaveResearchReportEditRequest(originalArtifactId=artifact.id, originalSha256=artifact.content_sha256, expectedVersion=0,markdown="no longer authorized"))
    assert caught.value.status_code == 403
    assert db.get(ResearchReportEdit, run.id) is None


def test_first_save_rejects_replaced_original_before_any_write(research_app):
    client, db, context, run, artifact = ready_report(research_app)
    url = path(context, run)
    before = client.get(url, headers=auth(context["creator"])).json()
    replacement = b"# Replacement before first save"
    artifact.byte_size = len(replacement)
    artifact.content_sha256 = hashlib.sha256(replacement).hexdigest()
    context["objectStore"][artifact.object_key] = replacement
    db.commit()
    for base_id, base_hash in [(before["originalArtifactId"], before["originalSha256"]),
                               ("different-artifact", artifact.content_sha256)]:
        response = client.put(url, headers=auth(context["creator"]), json={
            "originalArtifactId": base_id, "originalSha256": base_hash,
            "expectedVersion": 0, "markdown": "Draft based on the previous report"})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "report_edit_base_conflict"
        assert db.get(ResearchReportEdit, run.id) is None
    assert client.put(url, headers=auth(context["creator"]), json={
        "expectedVersion": 0, "markdown": "missing base"}).status_code == 422
