"""Isolated service fixture: real persistence/storage, scripted unpaid capabilities."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

SOURCE = (
    "Version 1: use port 80. Version 2: use port 443. "
    "For the same unspecified version, source A recommends alpha and source B recommends beta."
)


class FixtureProvider:
    def __init__(self, mode):
        from ai_pdf_api.core.settings import settings

        self.provider, self.model, self.mode = (
            settings.generation_provider,
            settings.generation_model,
            mode,
        )

    def generate(self, messages, *, max_output_tokens):
        assert max_output_tokens > 0
        v = json.loads(messages[-1]["content"])
        if "planOutputSchema" in v:
            asset = v["frozenAssetScope"]["assets"][0]["assetId"]
            result = {
                "summary": "Compare the documented conditions.",
                "subproblems": [
                    {
                        "question": "Compare Version 1 and Version 2 port requirements.",
                        "assetIds": [asset],
                        "expectedEvidence": [],
                    }
                ],
                "knownGaps": [],
                "estimatedProviderCalls": 10,
            }
        elif "toolContracts" in v:
            handle = v["toolContracts"]["evidence"][0]["evidenceHandle"]
            result = {
                "claims": [
                    {"text": text, "evidenceHandleIds": [handle]}
                    for text in (
                        ("Use port 80.", "Use port 443.")
                        if self.mode == "resolved"
                        else ("Recommend alpha.", "Recommend beta.")
                    )
                ]
            }
            if "nextQuery" in v.get("resultSchema", {}).get("properties", {}):
                result["nextQuery"] = None
        elif "investigation" in v:
            investigation = v["investigation"]
            evidence = investigation["evidence"]
            result = {
                "inspections": [
                    {
                        "evidenceHandleId": e["id"],
                        "quote": e["excerpt"],
                        "version": "Version 1" if self.mode == "resolved" else None,
                        "environment": None,
                        "time": None,
                        "conditions": None,
                    }
                    for e in evidence
                ],
                "revisions": [],
                "nextQuery": "Find a documented version for alpha and beta",
                "gaps": [
                    "The same-condition alpha/beta recommendations have no deciding evidence."
                ],
                "reason": "Compared the source text and its explicit version conditions.",
            }
            if self.mode == "resolved":
                result.update(
                    revisions=[
                        {
                            "originalClaimIds": [claim["id"]],
                            "text": "For Version 1 use port 80."
                            if i == 0
                            else "For Version 2 use port 443.",
                            "evidenceHandleIds": claim["evidenceHandleIds"],
                        }
                        for i, claim in enumerate(investigation["claims"])
                    ],
                    nextQuery=None,
                    gaps=[],
                )
        elif "reasonTaxonomy" in v:
            result = {
                "claims": [{"id": c["id"], "status": "supported"} for c in v["claims"]]
            }
        elif "conflictClaimIds" in v.get("resultSchema", {}).get("properties", {}):
            result = {
                "conflictClaimIds": [
                    c["id"]
                    for c in v["claims"]
                    if not c["text"].startswith("For Version ")
                ]
            }
        else:
            result = {
                "factClaimIds": [],
                "unresolvedClaimIds": [c["id"] for c in v["claims"]],
            }
        return json.dumps(result)


def install_capabilities(mode):
    from ai_pdf_api.core.settings import settings
    from ai_pdf_worker import research_persistence_service as composition

    original = composition.search_frozen_evidence

    class Embedding:
        provider, model, version = (
            settings.embedding_provider,
            settings.embedding_model,
            settings.embedding_version,
        )
        dimensions = 1024

        def embed_query(self, query):
            return [1.0, *([0.0] * 1023)]

    def search(db, **kwargs):
        return original(db, **kwargs, embedding_provider=Embedding())

    composition.search_frozen_evidence = search
    return FixtureProvider(mode)


def install_crash(point, marker):
    from ai_pdf_worker.research_runtime_ports import LedgeredGeneration

    original = LedgeredGeneration.conflict_turn

    def die(phase, boundary, operation):
        if point == f"{phase}:{boundary}":
            with Path(marker).open("w", encoding="utf-8") as file:
                json.dump(
                    {"pid": os.getpid(), "point": point, "operation": operation}, file
                )
                file.flush()
                os.fsync(file.fileno())
            os._exit(86)

    def checkpoint(self, lease, operation, phase, request, result=None):
        boundary = "reserve" if result is None else "result"
        die(phase, "before-" + boundary, operation)
        saved = original(self, lease, operation, phase, request, result)
        die(phase, "after-" + boundary, operation)
        return saved

    LedgeredGeneration.conflict_turn = checkpoint


def seed():
    from ai_pdf_api.core.security import hash_password
    from ai_pdf_api.db.session import SessionLocal
    from ai_pdf_api.models import User
    from ai_pdf_api.services.storage import upload_bytes, delete_object_if_exists
    from ai_pdf_worker import r800_acceptance_fixture as fixture
    from ai_pdf_worker.r800_acceptance_common import IDS

    fixture.SOURCE_TEXT = SOURCE
    fixture.seed_state(
        SessionLocal, uploader=upload_bytes, cleanup=delete_object_if_exists
    )
    with SessionLocal() as db:
        user = db.get(User, IDS["creator"])
        user.email, user.name = "issue25@example.test", "Issue 25 Service Fixture"
        user.password_hash = hash_password("issue25-local-fixture-only")
        user.avatar_url = "/favicon.ico"
        db.commit()
    print(
        json.dumps(
            {
                "workspaceId": IDS["workspace"],
                "userId": IDS["creator"],
                "assetId": IDS["asset"],
            }
        )
    )


def consume_tool_budget():
    from datetime import datetime, UTC
    from ai_pdf_worker.research_runtime_ports import LedgeredGeneration
    from citeframe_research_persistence.errors import ResearchError

    original = LedgeredGeneration.conflict_turn
    consumed = False

    def checkpoint(self, lease, operation, phase, request, result=None):
        nonlocal consumed
        if not consumed:
            consumed = True
            for number in range(65):
                self._ledger.heartbeat(lease)
                try:
                    self._call(
                        "search_frozen_evidence",
                        write=True,
                        run_id=self.execution.run_id,
                        execution_snapshot_id=self.execution.execution_snapshot_id,
                        step_id=lease.step_id,
                        attempt_id=lease.attempt_id,
                        branch_key="conflicts",
                        tool_call_key=f"fixture-prior-budget-{number}",
                        query=f"Prior budget query {number}",
                        asset_ids=tuple(
                            a.asset_id for a in self.execution.frozen_assets
                        ),
                        top_k=self.execution.retrieval_top_k,
                        now=datetime.now(UTC),
                    )
                except ResearchError as error:
                    assert error.code in {
                        "research_budget_limit",
                        "research_budget_exceeded",
                    }, error.code
                    break
            else:
                raise AssertionError("Tool budget did not reject the next call")
        return original(self, lease, operation, phase, request, result)

    LedgeredGeneration.conflict_turn = checkpoint


def work(args):
    from ai_pdf_api.db.session import SessionLocal
    from ai_pdf_worker.research_runtime import (
        ResearchWorkProcessor,
        build_default_research_service,
    )
    from ai_pdf_worker import research_runtime_processor, research_runtime_ports

    research_runtime_processor.LEASE_SECONDS = 8
    research_runtime_ports.LEASE_SECONDS = 8
    provider = install_capabilities(args.mode)
    if args.exhaust_tools:
        consume_tool_budget()
    if args.crash:
        install_crash(args.crash, args.marker)
    processor = ResearchWorkProcessor(
        SessionLocal, build_default_research_service(), provider=provider
    )
    for _ in range(args.steps):
        if not processor.process_one():
            break
        if args.until_gate:
            from sqlalchemy import select
            from ai_pdf_api.models import ResearchStep

            with SessionLocal() as db:
                if db.scalar(
                    select(ResearchStep.id).where(
                        ResearchStep.step_kind == "conflict_decision_gate",
                        ResearchStep.status == "queued",
                    )
                ):
                    break


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "work"])
    parser.add_argument(
        "--mode", choices=["resolved", "unresolved"], default="resolved"
    )
    parser.add_argument("--steps", type=int, default=1)
    parser.add_argument("--until-gate", action="store_true")
    parser.add_argument("--exhaust-tools", action="store_true")
    parser.add_argument("--crash")
    parser.add_argument("--marker")
    args = parser.parse_args()
    if args.command == "seed":
        seed()
    else:
        work(args)


if __name__ == "__main__":
    main()
