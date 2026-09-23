"""Synthetic provider and real-service process entry points; no remote model calls."""

from __future__ import annotations

import argparse
import json
import os

from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.session import SessionLocal
from ai_pdf_api.models import ResearchRun, ResearchStep
from ai_pdf_api.services.research.research_worker_evidence import search_frozen_evidence
from ai_pdf_worker import research_persistence_service as composition
from ai_pdf_worker.research_runtime import (
    ResearchWorkProcessor,
    build_default_research_service,
)
from sqlalchemy import select


class FixtureEmbedding:
    provider = settings.embedding_provider
    model = settings.embedding_model
    version = settings.embedding_version
    dimensions = 1024

    def embed_query(self, query):
        assert query.strip()
        return [1.0, *([0.0] * 1023)]


class FixtureGeneration:
    provider = settings.generation_provider
    model = settings.generation_model

    def generate(self, messages, *, max_output_tokens):
        assert max_output_tokens > 0
        v = json.loads(messages[-1]["content"])
        if "planOutputSchema" in v:
            result = {
                "summary": "One bounded source question.",
                "subproblems": [
                    {
                        "question": "What does the source establish?",
                        "assetIds": [v["frozenAssetScope"]["assets"][0]["assetId"]],
                        "expectedEvidence": [],
                    }
                ],
                "knownGaps": [],
                "estimatedProviderCalls": 5,
            }
        elif "toolContracts" in v:
            result = {
                "claims": [
                    {
                        "text": "The source preserves immutable evidence.",
                        "evidenceHandleIds": [
                            v["toolContracts"]["evidence"][0]["evidenceHandle"]
                        ],
                    }
                ]
            }
        elif "reasonTaxonomy" in v:
            result = {
                "claims": [
                    {"id": item["id"], "status": "supported"} for item in v["claims"]
                ]
            }
        elif "conflictClaimIds" in v.get("resultSchema", {}).get("properties", {}):
            result = {"conflictClaimIds": [item["id"] for item in v["claims"]]}
        else:
            result = {
                "factClaimIds": [],
                "unresolvedClaimIds": [item["id"] for item in v["claims"]],
            }
        return json.dumps(result)


def processor(fault=None):
    # Inject only paid capabilities. Retrieval SQL, persistence, leases and S3 remain production.
    composition.search_frozen_evidence = lambda db, **kw: search_frozen_evidence(
        db, **kw, embedding_provider=FixtureEmbedding()
    )
    if fault:
        original = composition.upload_publication_bytes

        def upload(key, payload, content_type):
            if fault == "put-failure":
                raise ConnectionError("synthetic publication transport failure")
            original(key, payload, content_type)
            if fault == "after-put-crash":
                os._exit(86)

        composition.upload_publication_bytes = upload
    return ResearchWorkProcessor(
        SessionLocal,
        build_default_research_service(),
        worker_instance_id=f"service-worker-{os.getpid()}",
        provider=FixtureGeneration(),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("--mode", choices=["advance", "one"], default="advance")
    parser.add_argument("--fault", choices=["put-failure", "after-put-crash"])
    args = parser.parse_args()
    worker = processor(args.fault)
    outputs = []
    for _ in range(10):
        if args.mode == "advance":
            with SessionLocal() as db:
                run = db.get(ResearchRun, args.run_id)
                publisher = db.scalar(
                    select(ResearchStep).where(
                        ResearchStep.run_id == args.run_id,
                        ResearchStep.step_kind == "artifact_publisher",
                    )
                )
                if run.status in {
                    "awaiting_plan_approval",
                    "awaiting_human_decision",
                    "completed",
                } or (publisher is not None and publisher.status == "queued"):
                    break
                assert run.status not in {"failed", "cancelled", "awaiting_retry"}, (
                    run.status
                )
        handled = worker.process_one()
        outputs.append(handled)
        if args.mode == "one":
            break
        assert handled, "Worker stopped before the expected checkpoint"
    else:
        raise AssertionError("Unexpected extra business steps")
    print(json.dumps({"pid": os.getpid(), "outputs": outputs}), flush=True)


if __name__ == "__main__":
    main()
