"""Provision and clean a temporary workspace for the live M403B browser gate."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ai_pdf_api.core.security import hash_password
from ai_pdf_api.db.base import Base
from ai_pdf_api.db.session import SessionLocal, engine
from ai_pdf_api.models import ChatThread, User, Workspace, WorkspaceMembership
from ai_pdf_api.services.storage import delete_objects_with_prefix
from sqlalchemy import delete, update

SCHEMA_VERSION = "m403b-browser-state-v1"


def setup(output: Path) -> None:
    user_id = str(uuid4())
    workspace_id = str(uuid4())
    run_id = uuid4().hex[:12]
    email = f"m403b-browser-{run_id}@example.com"
    password = f"M403B-browser-{run_id}!"
    now = datetime.now(UTC)
    with SessionLocal() as db:
        db.add(
            User(
                id=user_id,
                email=email,
                name="M403B Browser Acceptance",
                password_hash=hash_password(password),
                avatar_url="https://example.invalid/m403b-browser.png",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            Workspace(
                id=workspace_id,
                name=f"M403B Browser {run_id}",
                description="Temporary live production Image browser acceptance workspace",
                system_prompt="Answer only from supplied evidence.",
                retrieval_top_k=6,
                chunk_size=1200,
                created_by_user_id=user_id,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            WorkspaceMembership(
                id=str(uuid4()),
                workspace_id=workspace_id,
                user_id=user_id,
                role="owner",
                created_at=now,
            )
        )
        db.commit()

    state = {
        "schemaVersion": SCHEMA_VERSION,
        "runId": run_id,
        "userId": user_id,
        "email": email,
        "password": password,
        "workspaceId": workspace_id,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in state.items() if key != "password"}, sort_keys=True))


def cleanup(state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError("M403B browser state schema mismatch")
    workspace_id = str(state["workspaceId"])
    user_id = str(state["userId"])
    errors: list[Exception] = []
    try:
        delete_objects_with_prefix(f"workspaces/{workspace_id}/")
    except Exception as error:
        errors.append(error)
    try:
        with engine.begin() as connection:
            connection.execute(
                update(ChatThread)
                .where(ChatThread.workspace_id == workspace_id)
                .values(active_message_id=None)
            )
            for table in reversed(Base.metadata.sorted_tables):
                if "workspace_id" in table.c:
                    connection.execute(delete(table).where(table.c.workspace_id == workspace_id))
            connection.execute(delete(Workspace).where(Workspace.id == workspace_id))
            connection.execute(delete(User).where(User.id == user_id))
    except Exception as error:
        errors.append(error)
    if errors:
        detail = "; ".join(f"{type(error).__name__}: {error}" for error in errors)
        raise RuntimeError(f"M403B browser cleanup failed: {detail}") from errors[0]
    print(json.dumps({"cleanedWorkspaceId": workspace_id, "cleanedUserId": user_id}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup_parser = subparsers.add_parser("setup")
    setup_parser.add_argument("--output", type=Path, required=True)
    cleanup_parser = subparsers.add_parser("cleanup")
    cleanup_parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "setup":
        setup(args.output)
    else:
        cleanup(args.state)


if __name__ == "__main__":
    main()
