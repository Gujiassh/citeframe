"""Real PostgreSQL + S3 + process-death acceptance (opt in; never production data)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("CITEFRAME_SERVICE_ADMIN_URL"),
    reason="requires isolated PostgreSQL/S3 service acceptance environment",
)


def test_publication_crash_restore_and_new_worker(tmp_path):
    from ai_pdf_api.models import (
        ResearchArtifact,
        ResearchBudgetLedger,
        ResearchEvent,
        ResearchProviderCall,
        ResearchPublicationIntent,
        ResearchRun,
    )
    from ai_pdf_api.services import storage
    from citeframe_evaluation.acceptance.fixture import seed_state
    from research_service_support import (
        ServiceHarness,
        api_client,
        create_run,
        to_publisher,
    )
    from sqlalchemy import func, select

    h = ServiceHarness(tmp_path / "source")
    h.migrate()
    client, sessions = api_client(h)
    seed_state(
        sessions, uploader=storage.upload_bytes, cleanup=storage.delete_object_if_exists
    )
    run_id = create_run(client, "service-crash-source")
    to_publisher(h, client, sessions, run_id)
    with sessions() as db:
        ledger_before = [
            dict(row)
            for row in db.execute(
                select(ResearchBudgetLedger.__table__)
                .where(ResearchBudgetLedger.run_id == run_id)
                .order_by(ResearchBudgetLedger.id)
            ).mappings()
        ]
        calls_before = db.scalar(select(func.count()).select_from(ResearchProviderCall))
    h.worker(run_id, fault="after-put-crash", mode="one", expect=86)
    with sessions() as db:
        intent = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        assert intent.status == "prepared"
        assert (
            db.scalar(
                select(ResearchArtifact).where(
                    ResearchArtifact.run_id == run_id,
                    ResearchArtifact.artifact_kind == "final_report",
                )
            )
            is None
        )
        raw = storage.download_bytes(intent.current_object_key)
        assert hashlib.sha256(raw).hexdigest() == intent.content_sha256
        old_key = intent.current_object_key
        wait_seconds = max(
            0,
            (
                intent.claim_expires_at.replace(tzinfo=UTC) - datetime.now(UTC)
            ).total_seconds(),
        )
    # Real DB time and unchanged production lease duration; no forced expiry or clock mocks.
    time.sleep(wait_seconds + 1)
    h.worker(run_id, mode="one")
    with sessions() as db:
        pending = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        assert pending.last_error_code == "research_publication_attempt_lease_active"
        assert db.get(ResearchRun, run_id).status == "running"
        wait_seconds = max(
            0,
            (
                pending.next_reconcile_at.astimezone(UTC) - datetime.now(UTC)
            ).total_seconds(),
        )
    time.sleep(wait_seconds + 1)
    h.worker(run_id, mode="one")
    with sessions() as db:
        run = db.get(ResearchRun, run_id)
        assert run.status == "completed"
        artifact = db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == run_id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        assert storage.download_bytes(artifact.object_key) == raw
        assert artifact.content_sha256 == hashlib.sha256(raw).hexdigest()
        intent = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        assert (
            intent.status == "committed" and intent.committed_artifact_id == artifact.id
        )
        assert intent.adopted_object_key == artifact.object_key
        assert (
            db.scalar(select(func.count()).select_from(ResearchProviderCall))
            == calls_before
        )
        ledger_after = [
            dict(row)
            for row in db.execute(
                select(ResearchBudgetLedger.__table__)
                .where(ResearchBudgetLedger.run_id == run_id)
                .order_by(ResearchBudgetLedger.id)
            ).mappings()
        ]
        assert ledger_after == ledger_before
        events = list(
            db.scalars(select(ResearchEvent).where(ResearchEvent.run_id == run_id))
        )
        assert sum(e.event_type == "run_completed" for e in events) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(ResearchArtifact)
                .where(
                    ResearchArtifact.run_id == run_id,
                    ResearchArtifact.artifact_kind == "final_report",
                )
            )
            == 1
        )
    h.worker(run_id, mode="one")
    with sessions() as db:
        terminal = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        assert terminal.last_error_code == "publication_terminal_sweep_pending"
        sweep_due = terminal.orphan_sweep_after.astimezone(UTC)
    time.sleep(max(0, (sweep_due - datetime.now(UTC)).total_seconds()) + 1)
    h.worker(run_id, mode="one")
    idle = h.worker(run_id, mode="one")
    assert json.loads(idle.stdout)["outputs"] == [False]
    with sessions() as db:
        assert (
            db.scalar(select(func.count()).select_from(ResearchProviderCall))
            == calls_before
        )
        assert [
            dict(row)
            for row in db.execute(
                select(ResearchBudgetLedger.__table__)
                .where(ResearchBudgetLedger.run_id == run_id)
                .order_by(ResearchBudgetLedger.id)
            ).mappings()
        ] == ledger_before
    source_bucket = h.env["AI_PDF_MINIO_BUCKET"]
    s3 = storage.build_storage_client()
    objects = {
        o.object_name: storage.download_bytes(o.object_name)
        for o in s3.list_objects(source_bucket, recursive=True)
    }
    restored = ServiceHarness(tmp_path / "restored")
    h.restore_into(restored)
    client.close()
    restored_client, restored_sessions = api_client(restored)
    for key, payload in objects.items():
        storage.upload_bytes(key, payload, "application/octet-stream")
    with restored_sessions() as db:
        old = db.get(ResearchRun, run_id)
        artifact = db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == run_id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        assert (
            old.status == "completed"
            and storage.download_bytes(artifact.object_key) == raw
        )
    new_id = create_run(restored_client, "service-after-restore-new-task")
    assert new_id != run_id
    to_publisher(restored, restored_client, restored_sessions, new_id)
    restored.worker(new_id, fault="put-failure", mode="one")
    with restored_sessions() as db:
        assert (
            db.scalar(
                select(ResearchArtifact).where(
                    ResearchArtifact.run_id == new_id,
                    ResearchArtifact.artifact_kind == "final_report",
                )
            )
            is None
        )
        pending = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == new_id
            )
        )
        assert pending.status != "committed"
    time.sleep(6)
    restored.worker(new_id, mode="one")
    with restored_sessions() as db:
        pending = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == new_id
            )
        )
        assert pending.last_error_code == "research_publication_attempt_lease_active"
        wait_seconds = max(
            0,
            (
                pending.next_reconcile_at.astimezone(UTC) - datetime.now(UTC)
            ).total_seconds(),
        )
    time.sleep(wait_seconds + 1)
    restored.worker(new_id, mode="one")
    with restored_sessions() as db:
        final = db.get(ResearchRun, new_id)
        assert final.status == "completed"
        artifact = db.scalar(
            select(ResearchArtifact).where(
                ResearchArtifact.run_id == new_id,
                ResearchArtifact.artifact_kind == "final_report",
            )
        )
        assert (
            hashlib.sha256(storage.download_bytes(artifact.object_key)).hexdigest()
            == artifact.content_sha256
        )
    report = {
        "scope": "real PG migrations/dump/restore, real S3, production Worker child processes; synthetic model+embedding",
        "head": h.command(["git", "rev-parse", "HEAD"]).stdout.strip(),
        "sourceRun": run_id,
        "restoredNewRun": new_id,
        "sourceWorkers": h.processes,
        "restoredWorkers": restored.processes,
        "beforeCrashObjectKey": old_key,
        "result": "pass",
    }
    (tmp_path / "service-evidence.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )


@pytest.mark.parametrize("fence", ["cancel", "revoke"])
def test_crashed_publication_fenced_before_adoption(tmp_path, fence):
    from ai_pdf_api.models import (
        ResearchArtifact,
        ResearchEvent,
        ResearchPublicationIntent,
        ResearchRun,
        WorkspaceMembership,
    )
    from ai_pdf_api.services import storage
    from citeframe_evaluation.acceptance.common import IDS
    from citeframe_evaluation.acceptance.fixture import seed_state
    from research_service_support import (
        ServiceHarness,
        api_client,
        create_run,
        headers,
        to_publisher,
    )
    from sqlalchemy import delete, func, select

    h = ServiceHarness(tmp_path / fence)
    h.migrate()
    client, sessions = api_client(h)
    seed_state(
        sessions, uploader=storage.upload_bytes, cleanup=storage.delete_object_if_exists
    )
    sibling_key = "research/unrelated-owner/do-not-delete.txt"
    storage.upload_bytes(sibling_key, b"unrelated synthetic owner", "text/plain")
    run_id = create_run(client, f"service-fence-{fence}-0001")
    to_publisher(h, client, sessions, run_id)
    h.worker(run_id, fault="after-put-crash", mode="one", expect=86)
    with sessions() as db:
        run = db.get(ResearchRun, run_id)
        intent = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        expiry = intent.claim_expires_at.astimezone(UTC)
        if fence == "revoke":
            assert (
                db.execute(
                    delete(WorkspaceMembership).where(
                        WorkspaceMembership.workspace_id == IDS["workspace"],
                        WorkspaceMembership.user_id == IDS["creator"],
                    )
                ).rowcount
                == 1
            )
            db.commit()
        else:
            response = client.post(
                f"/v1/workspaces/{IDS['workspace']}/research-runs/{run_id}/cancel",
                headers=headers(f"cancel-{run_id}"),
                json={
                    "expectedStateVersion": run.state_version,
                    "reasonCode": "user_requested",
                },
            )
            assert response.status_code == 202, response.text
    h.snapshot("fence-committed")
    time.sleep(max(0, (expiry - datetime.now(UTC)).total_seconds()) + 1)
    h.worker(run_id, mode="one")
    with sessions() as db:
        intent = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        assert intent.status == "compensating"
        assert intent.last_error_code == "publication_compensation_sweep_pending"
        due = intent.next_reconcile_at.astimezone(UTC)
        assert (
            db.scalar(
                select(func.count())
                .select_from(ResearchArtifact)
                .where(
                    ResearchArtifact.run_id == run_id,
                    ResearchArtifact.artifact_kind == "final_report",
                )
            )
            == 0
        )
    time.sleep(max(0, (due - datetime.now(UTC)).total_seconds()) + 1)
    h.worker(run_id, mode="one")
    with sessions() as db:
        intent = db.scalar(
            select(ResearchPublicationIntent).where(
                ResearchPublicationIntent.run_id == run_id
            )
        )
        assert intent.status == "absent"
        assert db.get(ResearchRun, run_id).status == "cancelled"
        assert (
            db.scalar(
                select(func.count())
                .select_from(ResearchEvent)
                .where(
                    ResearchEvent.run_id == run_id,
                    ResearchEvent.event_type == "run_completed",
                )
            )
            == 0
        )
        assert (
            list(
                storage.build_storage_client().list_objects(
                    h.env["AI_PDF_MINIO_BUCKET"],
                    prefix=intent.object_prefix + "/",
                    recursive=True,
                )
            )
            == []
        )
    assert storage.download_bytes(sibling_key) == b"unrelated synthetic owner"
    (tmp_path / "fence-evidence.json").write_text(
        json.dumps(
            {
                "fence": fence,
                "runId": run_id,
                "processes": h.processes,
                "result": "pass",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
