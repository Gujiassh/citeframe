from __future__ import annotations

from ai_pdf_api.models import (
    ChatMessage,
    ResearchEvent,
    ResearchIdempotencyRecord,
    ResearchPlanRevision,
    ResearchRun,
)
from ai_pdf_api.services.research.research_prompt_provenance import (
    prompt_contract_sha256,
)
from ai_pdf_api.services.research.research_worker import (
    load_planning_input,
)
from research_router_test_support import (
    auth,
    create_run,
)
from sqlalchemy import func, select


def test_create_run_freezes_planning_scope_and_leaves_quick_tables_unchanged(research_app) -> None:
    client, db, context = research_app
    before_messages = db.scalar(select(func.count()).select_from(ChatMessage))

    run = create_run(client, context)

    assert run["status"] == "planning"
    assert run["researchExecution"] is None
    assert run["plan"] is None
    assert run["requestedAssetScope"]["mode"] == "selected"
    assert run["frozenAssetScope"]["assets"] == [
        {
            "assetId": context["asset"].id,
            "assetKind": "pdf",
            "assetTitle": "Source",
            "processingGeneration": 2,
            "indexVersion": 3,
        }
    ]
    assert run["steps"][0]["kind"] == "planner"
    assert run["steps"][0]["status"] == "queued"
    assert run["currentEventSeq"] == 2
    assert db.scalar(select(func.count()).select_from(ResearchRun)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchPlanRevision)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchEvent)) == 2
    assert db.scalar(select(func.count()).select_from(ChatMessage)) == before_messages
    planning = load_planning_input(db, run["id"])
    assert planning["plannerPrompt"]["nodeKey"] == "planner"
    assert planning["plannerPrompt"]["templateSha256"] == prompt_contract_sha256(
        planning["plannerPrompt"]["template"],
        planning["plannerPrompt"]["variablesSchema"],
    )


def test_create_is_persistently_idempotent_and_rejects_key_reuse(research_app) -> None:
    client, db, context = research_app
    first = create_run(client, context, key="research-idempotent-0001")
    creator = context["creator"]
    workspace = context["workspace"]
    asset = context["asset"]

    replay = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs",
        headers=auth(creator, key="research-idempotent-0001"),
        json={
            "question": "Compare the evidence.",
            "assetScope": {"mode": "selected", "assetIds": [asset.id]},
        },
    )
    assert replay.status_code == 201
    assert replay.headers["Idempotency-Replayed"] == "true"
    assert replay.json()["run"]["id"] == first["id"]
    assert db.scalar(select(func.count()).select_from(ResearchRun)) == 1
    assert db.scalar(select(func.count()).select_from(ResearchEvent)) == 2
    assert db.scalar(select(func.count()).select_from(ResearchIdempotencyRecord)) == 1

    conflict = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs",
        headers=auth(creator, key="research-idempotent-0001"),
        json={"question": "A different question.", "assetScope": {"mode": "selected", "assetIds": [asset.id]}},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "idempotency_key_reused"


def test_workspace_members_can_read_but_cross_workspace_ids_do_not_leak(research_app) -> None:
    client, _db, context = research_app
    run = create_run(client, context)
    member = context["member"]
    stranger = context["stranger"]
    workspace = context["workspace"]
    other_workspace = context["otherWorkspace"]

    visible = client.get(f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}", headers=auth(member))
    assert visible.status_code == 200
    assert visible.headers["ETag"] == f'"run-{run["id"]}-v{run["stateVersion"]}"'

    hidden = client.get(
        f"/v1/workspaces/{other_workspace.id}/research-runs/{run['id']}",
        headers=auth(stranger),
    )
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "research_run_not_found"


def test_list_supports_creator_filter_and_opaque_cursor(research_app) -> None:
    client, _db, context = research_app
    first = create_run(client, context, key="research-list-create-01", question="First question")
    second = create_run(client, context, key="research-list-create-02", question="Second question")
    workspace = context["workspace"]
    member = context["member"]
    creator = context["creator"]

    page_one = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs?createdBy=all&limit=1",
        headers=auth(member),
    )
    assert page_one.status_code == 200
    assert len(page_one.json()["items"]) == 1
    assert page_one.json()["nextCursor"]
    page_two = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs?createdBy=all&limit=1&cursor={page_one.json()['nextCursor']}",
        headers=auth(member),
    )
    assert {page_one.json()["items"][0]["id"], page_two.json()["items"][0]["id"]} == {
        first["id"],
        second["id"],
    }
    mine = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs?createdBy=me",
        headers=auth(creator),
    )
    assert len(mine.json()["items"]) == 2
    other_member = client.get(
        f"/v1/workspaces/{workspace.id}/research-runs?createdBy=me",
        headers=auth(member),
    )
    assert other_member.json()["items"] == []


def test_cancel_permissions_and_idempotent_event(research_app) -> None:
    client, db, context = research_app
    run = create_run(client, context)
    member = context["member"]
    owner = context["owner"]
    workspace = context["workspace"]
    denied = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}/cancel",
        headers=auth(member, key="research-cancel-denied-01"),
        json={"expectedStateVersion": run["stateVersion"], "reasonCode": "user_requested"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "research_permission_denied"

    accepted = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}/cancel",
        headers=auth(owner, key="research-owner-cancel-01"),
        json={"expectedStateVersion": run["stateVersion"], "reasonCode": "cost"},
    )
    assert accepted.status_code == 202
    assert accepted.json()["run"]["status"] == "cancelled"
    assert db.scalar(
        select(func.count()).select_from(ResearchEvent).where(ResearchEvent.event_type == "cancel_requested")
    ) == 1
    assert db.scalar(
        select(func.count()).select_from(ResearchEvent).where(ResearchEvent.event_type == "run_cancelled")
    ) == 1

    replay = client.post(
        f"/v1/workspaces/{workspace.id}/research-runs/{run['id']}/cancel",
        headers=auth(owner, key="research-owner-cancel-01"),
        json={"expectedStateVersion": run["stateVersion"], "reasonCode": "cost"},
    )
    assert replay.status_code == 202
    assert replay.headers["Idempotency-Replayed"] == "true"
