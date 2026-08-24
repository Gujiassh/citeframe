from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.models import Asset, ChatThread, User, Workspace

pytestmark = pytest.mark.acceptance

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/m402_acceptance.py"
SCRIPT_SPEC = importlib.util.spec_from_file_location("m402_acceptance", SCRIPT_PATH)
assert SCRIPT_SPEC is not None and SCRIPT_SPEC.loader is not None
m402_acceptance = importlib.util.module_from_spec(SCRIPT_SPEC)
sys.modules[SCRIPT_SPEC.name] = m402_acceptance
SCRIPT_SPEC.loader.exec_module(m402_acceptance)


def _engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return engine


def _assert_no_acceptance_rows(engine) -> None:
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Workspace)) == 0
        assert db.scalar(select(func.count()).select_from(Asset)) == 0
        assert db.scalar(select(func.count()).select_from(ChatThread)) == 0


def test_m402_setup_compensates_when_asset_creation_fails(monkeypatch, tmp_path: Path) -> None:
    engine = _engine()
    deleted_prefixes: list[str] = []
    monkeypatch.setattr(m402_acceptance, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(
        m402_acceptance,
        "_create_asset",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("injected asset failure")),
    )
    monkeypatch.setattr(m402_acceptance, "delete_objects_with_prefix", deleted_prefixes.append)
    output = tmp_path / "state.json"

    with pytest.raises(RuntimeError, match="injected asset failure"):
        m402_acceptance.setup(output)

    _assert_no_acceptance_rows(engine)
    assert len(deleted_prefixes) == 1
    assert deleted_prefixes[0].startswith("workspaces/")
    assert not output.exists()


def test_m402_setup_compensates_after_commit_when_state_write_fails(
    monkeypatch,
    tmp_path: Path,
) -> None:
    engine = _engine()
    deleted_prefixes: list[str] = []
    monkeypatch.setattr(m402_acceptance, "create_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(m402_acceptance, "delete_objects_with_prefix", deleted_prefixes.append)

    def create_asset(db: Session, *, fixture, workspace, user, now):
        payload = (m402_acceptance.REPOSITORY_ROOT / fixture.source_path).read_bytes()
        asset = Asset(
            id=str(uuid4()),
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            asset_kind=fixture.modality,
            title=Path(fixture.source_path).name,
            source_filename=Path(fixture.source_path).name,
            object_key=f"workspaces/{workspace.id}/assets/{uuid4()}/source",
            mime_type="application/pdf" if fixture.modality == "pdf" else "image/png",
            byte_size=len(payload),
            source_sha256="0" * 64,
            status="ready",
            current_processing_generation=1,
            current_index_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(asset)
        db.flush()
        return asset, payload

    def seed_thread(db: Session, *, workspace, user, now, **kwargs):
        thread = ChatThread(
            id=str(uuid4()),
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            title="M402 failure injection",
            last_message_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(thread)
        db.flush()
        return thread, {}

    monkeypatch.setattr(m402_acceptance, "_create_asset", create_asset)
    monkeypatch.setattr(m402_acceptance, "_seed_evidence_thread", seed_thread)
    monkeypatch.setattr(
        m402_acceptance,
        "_write_state_atomic",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected state failure")),
    )
    output = tmp_path / "state.json"

    with pytest.raises(OSError, match="injected state failure"):
        m402_acceptance.setup(output)

    _assert_no_acceptance_rows(engine)
    assert len(deleted_prefixes) == 1
    assert deleted_prefixes[0].startswith("workspaces/")
    assert not output.exists()
