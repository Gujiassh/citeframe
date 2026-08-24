from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Callable

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ai_pdf_api.db.base import Base
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatThread,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
    PdfLocatorDetail,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.schemas.chat import AllReadyAssetScope, AssetScope, SelectedAssetScope
from ai_pdf_api.services.chat import complete_chat, fail_chat, finalize_chat, prepare_chat
from ai_pdf_api.services.multimodal_execution import (
    canonical_generation_messages_sha256,
    evaluate_real_model_output,
    load_multimodal_answer_oracle,
)
from ai_pdf_api.services.multimodal_quality import (
    GoldenCase,
    GoldenEvidenceTarget,
    GoldenFixture,
    GoldenSet,
    load_multimodal_quality_suite,
)
from ai_pdf_api.services.providers import get_generation_provider
from ai_pdf_api.services.retrieval import retrieve_query_content
from ai_pdf_worker.image_ingestion import ImageIngestionAdapter, extract_image_text_with_ocr
from ai_pdf_worker.pdf_ingestion import PdfIngestionAdapter

pytestmark = pytest.mark.acceptance

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = REPOSITORY_ROOT / "docs/evals"
TEST_FILE = "apps/worker/tests/test_multimodal_golden_execution.py"
TEST_NODE = f"{TEST_FILE}::test_m402_worker_executes_every_golden_evidence_target"

# ORM defaults and chat/citation clone paths call uuid4() for entity PKs. Production
# retrieval tie-breaks on ContentUnit.id / EvidenceLocator.id (and embedding.id on
# ANN paths). Random fixture IDs therefore change truncated retrieval sets under
# equal topic-vector distances. Patch only inside this harness so golden ranking
# is repeatable without changing production semantics.
_M402_UUID4_PATCH_TARGETS = (
    "ai_pdf_api.models.asset_representation.uuid4",
    "ai_pdf_api.models.chat_message.uuid4",
    "ai_pdf_api.models.content_unit.uuid4",
    "ai_pdf_api.models.content_unit_embedding.uuid4",
    "ai_pdf_api.models.evidence_locator.uuid4",
    "ai_pdf_api.models.message_citation.uuid4",
    "ai_pdf_api.models.message_input_evidence.uuid4",
    "ai_pdf_api.models.pdf_page.uuid4",
    "ai_pdf_api.models.workspace_membership.uuid4",
    "ai_pdf_api.modalities.evidence.uuid4",
    "ai_pdf_api.services.chat.uuid4",
)


class _DeterministicUuid4:
    """Stable, unique, UUID-shaped IDs for one M402 harness session."""

    def __init__(self, *, namespace: str) -> None:
        self._namespace = namespace
        self._counter = 0

    def __call__(self) -> uuid.UUID:
        self._counter += 1
        return uuid.uuid5(uuid.NAMESPACE_URL, f"{self._namespace}:{self._counter}")


def _install_deterministic_m402_ids(
    monkeypatch: pytest.MonkeyPatch,
    *,
    namespace: str = "m402-golden",
) -> _DeterministicUuid4:
    factory = _DeterministicUuid4(namespace=namespace)
    for target in _M402_UUID4_PATCH_TARGETS:
        monkeypatch.setattr(target, factory)
    return factory


class GoldenCaptionProvider:
    provider = "m402-golden"
    model = "deterministic-caption"
    version = "m402-v1"
    detail = "high"
    max_output_tokens = 320

    def caption(self, payload: bytes, *, content_type: str) -> str:
        assert payload.startswith(b"\x89PNG")
        assert content_type == "image/png"
        return "Release 4 begins the sustained drop. Verify chart and caption together."


class GoldenPdfVisualCaptionProvider:
    """Offline PDF visual captions. Unique per crop so retrieval stays fixture-scoped."""

    provider = "m402-golden-pdf-visual"
    model = "deterministic-pdf-visual-caption"
    version = "m402-v1"
    detail = "high"
    max_output_tokens = 320

    def caption(self, payload: bytes, *, content_type: str) -> str:
        assert payload.startswith(b"\x89PNG")
        assert content_type == "image/png"
        digest = sha256(payload).hexdigest()[:16]
        return f"PDF visual region caption {digest}."


class GoldenEmbeddingProvider:
    provider = "m402-golden"
    model = "deterministic-topics"
    dimensions = 1024
    version = "m402-v1"

    def embed_query(self, text: str) -> list[float]:
        return _topic_vector(text)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [_topic_vector(text) for text in texts]


class GoldenGenerationProvider:
    provider = "m402-golden"
    model = "deterministic-answers"

    def __init__(self, answers: dict[str, str]) -> None:
        self._answers = answers

    def generate(self, messages) -> str:
        prompt = str(messages[-1]["content"])
        matches = [answer for question, answer in self._answers.items() if question in prompt]
        assert len(matches) == 1
        return matches[0]


def _atomic_write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def _case_scope(case: GoldenCase, assets: dict[str, Asset]) -> AssetScope:
    if case.scope.mode == "all_ready":
        return AllReadyAssetScope(mode="all_ready")
    return SelectedAssetScope(
        mode="selected",
        assetIds=[assets[fixture_id].id for fixture_id in case.scope.selected_fixture_ids],
    )


def _run_real_model_if_requested(run: Callable[[Path], None]) -> None:
    report_path = os.environ.get("M402_REAL_MODEL_REPORT_PATH")
    if report_path:
        run(Path(report_path).resolve())


def _caption_config() -> dict[str, object]:
    return {
        "imageCaptionProvider": GoldenCaptionProvider.provider,
        "imageCaptionModel": GoldenCaptionProvider.model,
        "imageCaptionVersion": GoldenCaptionProvider.version,
        "imageCaptionDetail": GoldenCaptionProvider.detail,
        "imageCaptionMaxOutputTokens": GoldenCaptionProvider.max_output_tokens,
    }


def _asset(
    fixture_id: str,
    *,
    kind: str,
    source_path: Path,
    now: datetime,
) -> Asset:
    payload = source_path.read_bytes()
    return Asset(
        id=f"m402-{fixture_id}",
        workspace_id="m402-workspace",
        created_by_user_id="m402-user",
        asset_kind=kind,
        title=source_path.name,
        source_filename=source_path.name,
        object_key=f"m402/{source_path.name}",
        mime_type="application/pdf" if kind == "pdf" else "image/png",
        byte_size=len(payload),
        source_sha256=sha256(payload).hexdigest(),
        status="parsing",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )


def _fixture_object_store(fixtures) -> dict[str, bytes]:
    """Map Asset.object_key values used by M402 fixtures to local source bytes.

    complete_chat visual enrichment defaults to MinIO download_bytes. CI has no
    MinIO service, so the golden harness must stay fully offline.
    """
    store: dict[str, bytes] = {}
    for fixture in fixtures:
        source_path = REPOSITORY_ROOT / fixture.source_path
        store[f"m402/{source_path.name}"] = source_path.read_bytes()
    return store


def _offline_image_bytes_loader(store: dict[str, bytes]):
    def load(object_key: str) -> bytes:
        try:
            return store[object_key]
        except KeyError as error:
            raise KeyError(f"m402 offline store missing object_key={object_key}") from error

    return load


def _forbid_live_object_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail closed if any code path tries to reach the default MinIO endpoint."""

    def _blocked(*_args, **_kwargs):
        raise AssertionError(
            "M402 golden acceptance must stay offline; live object storage was invoked"
        )

    monkeypatch.setattr("ai_pdf_api.services.storage.build_storage_client", _blocked)
    monkeypatch.setattr("ai_pdf_api.services.storage.download_bytes", _blocked)
    monkeypatch.setattr("ai_pdf_api.services.storage.upload_bytes", _blocked)
    monkeypatch.setattr("ai_pdf_api.services.chat.download_bytes", _blocked)


def _persist_fixture_assets(db: Session, fixtures) -> dict[str, Asset]:
    now = datetime.now(UTC)
    assets: dict[str, Asset] = {}
    for fixture in fixtures:
        source_path = REPOSITORY_ROOT / fixture.source_path
        asset = _asset(fixture.id, kind=fixture.modality, source_path=source_path, now=now)
        db.add(asset)
        db.flush()
        if fixture.modality == "pdf":
            PdfIngestionAdapter(caption_provider=GoldenPdfVisualCaptionProvider()).ingest(
                db,
                asset=asset,
                payload=source_path.read_bytes(),
                processing_generation=1,
                config_snapshot={"chunkSize": 1200},
                created_at=now,
            )
        else:
            ImageIngestionAdapter(
                caption_provider=GoldenCaptionProvider(),
                ocr_extractor=extract_image_text_with_ocr,
            ).ingest(
                db,
                asset=asset,
                payload=source_path.read_bytes(),
                processing_generation=1,
                config_snapshot=_caption_config(),
                created_at=now,
            )
        assets[fixture.id] = asset
    db.flush()
    return assets


def _persist_identity(db: Session) -> tuple[User, Workspace]:
    now = datetime.now(UTC)
    user = User(
        id="m402-user",
        email="m402@example.com",
        name="M402",
        password_hash="hash",
        avatar_url="https://example.com/m402.svg",
        created_at=now,
        updated_at=now,
    )
    workspace = Workspace(
        id="m402-workspace",
        name="M402 golden execution",
        system_prompt=(
            "Answer only from supplied evidence. If it does not support the question, "
            "state that the selected assets do not contain supporting evidence."
        ),
        retrieval_top_k=10,
        created_by_user_id=user.id,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    db.add(workspace)
    db.flush()
    db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
    db.flush()
    return user, workspace


def _manifest(fixture) -> dict[str, object]:
    return json.loads((REPOSITORY_ROOT / fixture.manifest_path).read_text(encoding="utf-8"))


def _expected_regions(fixture, target: GoldenEvidenceTarget) -> list[tuple[float, float, float, float]]:
    manifest = _manifest(fixture)
    if fixture.modality == "image":
        by_label = {item["label"]: item for item in manifest["regions"]}
        return [_region(by_label[label]) for label in target.region_labels]
    page = next(item for item in manifest["pages"] if item["label"] == target.page_label)
    return [_region(page["regions"][index]) for index in target.region_indexes]


def _region(payload: dict[str, object]) -> tuple[float, float, float, float]:
    return tuple(float(payload[key]) for key in ("x", "y", "width", "height"))  # type: ignore[return-value]


def _actual_regions(db: Session, asset: Asset, target: GoldenEvidenceTarget) -> list[tuple[float, float, float, float]]:
    locator_ids: list[str]
    if target.locator_kind.startswith("pdf_"):
        locator_ids = db.scalars(
            select(EvidenceLocator.id)
            .join(PdfLocatorDetail, PdfLocatorDetail.locator_id == EvidenceLocator.id)
            .where(
                EvidenceLocator.asset_id == asset.id,
                EvidenceLocator.locator_kind == target.locator_kind,
                PdfLocatorDetail.page_number == target.page_number,
            )
        ).all()
    else:
        locator_ids = db.scalars(
            select(EvidenceLocator.id)
            .join(
                AssetRepresentation,
                AssetRepresentation.id == EvidenceLocator.representation_id_snapshot,
            )
            .where(
                EvidenceLocator.asset_id == asset.id,
                EvidenceLocator.locator_kind == "image_region",
                AssetRepresentation.representation_kind.in_(["image_ocr", "image_caption"]),
            )
        ).all()
    return [
        (region.x, region.y, region.width, region.height)
        for region in db.scalars(
            select(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id.in_(locator_ids))
        ).all()
    ]


def _approved_coverage_ratio(
    approved: tuple[float, float, float, float],
    rendered: tuple[float, float, float, float],
) -> float:
    approved_x, approved_y, approved_width, approved_height = approved
    rendered_x, rendered_y, rendered_width, rendered_height = rendered
    width = max(0.0, min(approved_x + approved_width, rendered_x + rendered_width) - max(approved_x, rendered_x))
    height = max(0.0, min(approved_y + approved_height, rendered_y + rendered_height) - max(approved_y, rendered_y))
    return width * height / (approved_width * approved_height)


def _topic_vector(text: str) -> list[float]:
    lowered = text.lower()
    vector = [0.0] * 1024
    topic_terms = (
        (0, ("90-degree", "rotation fixture 90", "rotation=90")),
        (1, ("scan", "rasterized scan")),
        (2, ("atlas", "91.4")),
        (3, ("vector",)),
        (4, ("latency", "sustained drop", "release 4", "falls after", "image observation")),
        (5, ("caption", "verify chart")),
        (6, ("trend", "rises after", "pdf chart")),
    )
    for index, terms in topic_terms:
        if any(term in lowered for term in terms):
            vector[index] = 1.0
    if not any(vector):
        vector[100] = 1.0
    return vector


def _add_embeddings(db: Session, assets: dict[str, Asset]) -> GoldenEmbeddingProvider:
    provider = GoldenEmbeddingProvider()
    units = db.scalars(
        select(ContentUnit).where(ContentUnit.asset_id.in_([asset.id for asset in assets.values()]))
    ).all()
    vectors = provider.embed_documents([unit.text_content for unit in units])
    db.add_all(
        [
            ContentUnitEmbedding(
                workspace_id=unit.workspace_id,
                asset_id=unit.asset_id,
                content_unit_id=unit.id,
                processing_generation=1,
                index_version=unit.index_version,
                is_current=True,
                embedding_space="text",
                provider=provider.provider,
                model=provider.model,
                dimensions=provider.dimensions,
                version=provider.version,
                embedding=vector,
                created_at=datetime.now(UTC),
            )
            for unit, vector in zip(units, vectors, strict=True)
        ]
    )
    for asset in assets.values():
        asset.status = "ready"
    db.commit()
    return provider


def _retrieval_covers_target(db: Session, items, asset: Asset, fixture, target: GoldenEvidenceTarget) -> bool:
    candidates = [
        item
        for item in items
        if item.asset.id == asset.id and item.locator.locator_kind == target.locator_kind
    ]
    if target.locator_kind.startswith("pdf_"):
        candidates = [
            item
            for item in candidates
            if (detail := db.get(PdfLocatorDetail, item.locator.id)) is not None
            and detail.page_number == target.page_number
        ]
    if not candidates:
        return False
    if target.locator_kind == "pdf_page":
        return True
    actual_regions = [
        (region.x, region.y, region.width, region.height)
        for item in candidates
        for region in db.scalars(
            select(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id == item.locator.id)
        ).all()
    ]
    return all(
        any(_approved_coverage_ratio(expected, actual) >= 0.1 for actual in actual_regions)
        for expected in _expected_regions(fixture, target)
    )


def _citations_cover_target(db: Session, citations, asset: Asset, fixture, target: GoldenEvidenceTarget) -> bool:
    candidates = [citation for citation in citations if citation.asset_id == asset.id]
    if target.locator_kind.startswith("pdf_"):
        candidates = [
            citation
            for citation in candidates
            if (locator := db.get(EvidenceLocator, citation.evidence_locator_id)) is not None
            and locator.locator_kind == target.locator_kind
            and (detail := db.get(PdfLocatorDetail, locator.id)) is not None
            and detail.page_number == target.page_number
        ]
    else:
        candidates = [
            citation
            for citation in candidates
            if (locator := db.get(EvidenceLocator, citation.evidence_locator_id)) is not None
            and locator.locator_kind == "image_region"
        ]
    if not candidates:
        return False
    if target.locator_kind == "pdf_page":
        return True
    actual_regions = [
        (region.x, region.y, region.width, region.height)
        for citation in candidates
        for region in db.scalars(
            select(SpatialLocatorRegion).where(
                SpatialLocatorRegion.locator_id == citation.evidence_locator_id
            )
        ).all()
    ]
    return all(
        any(_approved_coverage_ratio(expected, actual) >= 0.1 for actual in actual_regions)
        for expected in _expected_regions(fixture, target)
    )


def _execute_real_model_cases(
    db: Session,
    *,
    output_path: Path,
    golden: GoldenSet,
    fixtures: dict[str, GoldenFixture],
    assets: dict[str, Asset],
    workspace: Workspace,
    user: User,
    embedding_provider: GoldenEmbeddingProvider,
    image_bytes_loader: Callable[[str], bytes] | None = None,
) -> None:
    oracle = load_multimodal_answer_oracle(
        REPOSITORY_ROOT,
        EVAL_ROOT / "multimodal-answer-oracle-v1.json",
        golden,
    )
    oracle_by_id = {case.case_id: case for case in oracle.cases}
    generation_provider = get_generation_provider()
    answer_cases = [case for case in golden.cases if case.layer == "answer"]
    raw_cases: list[dict[str, object]] = []
    failed_case_ids: list[str] = []

    for index, case in enumerate(answer_cases):
        messages: list[dict[str, object]] = []
        output = ""
        error_message: str | None = None
        citation_coverage = [
            {
                "fixtureId": target.fixture_id,
                "locatorKind": target.locator_kind,
                "covered": False,
            }
            for target in case.evidence_targets
        ]
        try:
            thread = ChatThread(
                id=f"m402-real-thread-{index}",
                workspace_id=workspace.id,
                created_by_user_id=user.id,
                last_message_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(thread)
            db.commit()
            prepared = prepare_chat(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                thread=thread,
                question=case.question,
                asset_scope=_case_scope(case, assets),
                embedding_provider=embedding_provider,
                generation_provider=generation_provider,
                image_bytes_loader=image_bytes_loader,
            )
            messages = json.loads(json.dumps(prepared.generation_messages))
            try:
                output = generation_provider.generate(prepared.generation_messages)
            except Exception:
                fail_chat(
                    db,
                    prepared,
                    "m402_real_model_error",
                    "The M402 real-model acceptance call failed.",
                )
                raise
            completed = finalize_chat(db, prepared, output)
            citation_coverage = [
                {
                    "fixtureId": target.fixture_id,
                    "locatorKind": target.locator_kind,
                    "covered": _citations_cover_target(
                        db,
                        completed.citations,
                        assets[target.fixture_id],
                        fixtures[target.fixture_id],
                        target,
                    ),
                }
                for target in case.evidence_targets
            ]
        except Exception as error:
            db.rollback()
            error_message = f"{type(error).__name__}: {error}"

        evaluation = evaluate_real_model_output(oracle_by_id[case.id], output)
        passed = (
            error_message is None
            and evaluation.passed
            and all(item["covered"] is True for item in citation_coverage)
        )
        raw_cases.append(
            {
                "caseId": case.id,
                "question": case.question,
                "generationMessages": messages,
                "generationMessagesSha256": canonical_generation_messages_sha256(messages),
                "provider": generation_provider.provider,
                "model": generation_provider.model,
                "output": output,
                "citationCoverage": citation_coverage,
                "matchedAnswerPoints": list(evaluation.matched_answer_points),
                "refusalMatched": evaluation.refusal_matched,
                "error": error_message,
                "passed": passed,
            }
        )
        if not passed:
            failed_case_ids.append(case.id)
        _atomic_write_json(
            output_path,
            {
                "schemaVersion": "m402-real-model-execution-v1",
                "goldenSchemaVersion": golden.schema_version,
                "testFile": TEST_FILE,
                "testFileSha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                "testNode": TEST_NODE,
                "cases": raw_cases,
                "passed": False,
            },
        )

    _atomic_write_json(
        output_path,
        {
            "schemaVersion": "m402-real-model-execution-v1",
            "goldenSchemaVersion": golden.schema_version,
            "testFile": TEST_FILE,
            "testFileSha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "testNode": TEST_NODE,
            "cases": raw_cases,
            "passed": not failed_case_ids,
        },
    )
    assert not failed_case_ids, f"M402 real-model oracle failed: {failed_case_ids}"


def _run_m402_golden_acceptance(monkeypatch: pytest.MonkeyPatch) -> None:
    """Offline M402 golden acceptance body shared by pytest nodes.

    Not a pytest test: callers must be ordinary test functions so fixtures are
    not invoked by one test calling another.
    """
    _forbid_live_object_storage(monkeypatch)
    _install_deterministic_m402_ids(monkeypatch, namespace="m402-golden-acceptance")
    golden, _failures, _report = load_multimodal_quality_suite(
        REPOSITORY_ROOT,
        EVAL_ROOT / "multimodal-golden-v1.json",
        EVAL_ROOT / "multimodal-failures-v1.json",
    )
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    fixtures = {fixture.id: fixture for fixture in golden.fixtures}
    offline_store = _fixture_object_store(golden.fixtures)
    image_bytes_loader = _offline_image_bytes_loader(offline_store)
    with Session(engine) as db:
        user, workspace = _persist_identity(db)
        assets = _persist_fixture_assets(db, golden.fixtures)
        executed_case_ids: set[str] = set()
        for case in golden.cases:
            if not case.evidence_targets:
                continue
            for target in case.evidence_targets:
                asset = assets[target.fixture_id]
                actual_regions = _actual_regions(db, asset, target)
                if target.locator_kind == "pdf_page":
                    assert db.scalar(
                        select(EvidenceLocator.id)
                        .join(PdfLocatorDetail, PdfLocatorDetail.locator_id == EvidenceLocator.id)
                        .where(
                            EvidenceLocator.asset_id == asset.id,
                            EvidenceLocator.locator_kind == "pdf_page",
                            PdfLocatorDetail.page_number == target.page_number,
                        )
                    ), case.id
                    continue
                expected_regions = _expected_regions(fixtures[target.fixture_id], target)
                assert actual_regions, f"{case.id} produced no {target.locator_kind} regions"
                for expected in expected_regions:
                    assert any(_approved_coverage_ratio(expected, actual) >= 0.1 for actual in actual_regions), (
                        case.id,
                        expected,
                        actual_regions,
                    )
            executed_case_ids.add(case.id)

        assert executed_case_ids == {case.id for case in golden.cases if case.evidence_targets}

        provider = _add_embeddings(db, assets)
        retrieval_case_ids: set[str] = set()
        for case in golden.cases:
            if case.layer != "retrieval":
                continue
            selected_assets = (
                list(assets.values())
                if case.scope.mode == "all_ready"
                else [assets[fixture_id] for fixture_id in case.scope.selected_fixture_ids]
            )
            items = retrieve_query_content(
                db,
                "m402-workspace",
                case.question,
                provider.embed_query(case.question),
                asset_ids=[asset.id for asset in selected_assets],
                embedding_provider=provider,
                limit=10,
                strategy="hybrid",
            )
            for target in case.evidence_targets:
                assert _retrieval_covers_target(
                    db,
                    items,
                    assets[target.fixture_id],
                    fixtures[target.fixture_id],
                    target,
                ), (case.id, target.fixture_id, [(item.asset.id, item.locator.locator_kind) for item in items])
            retrieval_case_ids.add(case.id)

        assert retrieval_case_ids == {case.id for case in golden.cases if case.layer == "retrieval"}

        answer_cases = [case for case in golden.cases if case.layer == "answer"]
        answers = {
            case.question: (
                " ".join(case.expected_answer_points)
                if case.expected_disposition == "answer"
                else "The selected assets do not contain supporting evidence for that claim."
            )
            for case in answer_cases
        }
        generation = GoldenGenerationProvider(answers)
        answered_case_ids: set[str] = set()
        for index, case in enumerate(answer_cases):
            thread = ChatThread(
                id=f"m402-thread-{index}",
                workspace_id=workspace.id,
                created_by_user_id=user.id,
                last_message_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            db.add(thread)
            db.commit()
            completed = complete_chat(
                db,
                workspace_id=workspace.id,
                user_id=user.id,
                thread=thread,
                question=case.question,
                asset_scope=_case_scope(case, assets),
                embedding_provider=provider,
                generation_provider=generation,
                image_bytes_loader=image_bytes_loader,
            )
            if case.expected_disposition == "refuse":
                assert "do not contain supporting evidence" in completed.assistant_message.content
                assert "[" not in completed.assistant_message.content
            else:
                assert all(
                    point in completed.assistant_message.content for point in case.expected_answer_points
                ), case.id
                for target in case.evidence_targets:
                    assert _citations_cover_target(
                        db,
                        completed.citations,
                        assets[target.fixture_id],
                        fixtures[target.fixture_id],
                        target,
                    ), (case.id, target.fixture_id)
            answered_case_ids.add(case.id)

        assert answered_case_ids == {case.id for case in answer_cases}

        report_path = os.environ.get("M402_WORKER_REPORT_PATH")
        if report_path:
            output_path = Path(report_path).resolve()
            output_path.parent.mkdir(parents=True, exist_ok=True)
            report_cases = []
            for case in golden.cases:
                report_cases.append(
                    {
                        "caseId": case.id,
                        "layer": case.layer,
                        "modality": case.modality,
                        "targetCount": len(case.evidence_targets),
                        "adapterExecutionPassed": True if case.evidence_targets else None,
                        "retrievalExecutionPassed": True if case.layer == "retrieval" else None,
                        "chatOrchestrationPassed": True if case.layer == "answer" else None,
                        "generationMode": "scripted" if case.layer == "answer" else None,
                        "passed": (
                            case.id in retrieval_case_ids
                            if case.layer == "retrieval"
                            else case.id in answered_case_ids
                            if case.layer == "answer"
                            else case.id in executed_case_ids
                        ),
                    }
                )
            output_path.write_text(
                json.dumps(
                    {
                        "schemaVersion": "m402-worker-execution-v1",
                        "goldenSchemaVersion": golden.schema_version,
                        "testFile": TEST_FILE,
                        "testFileSha256": sha256(Path(__file__).read_bytes()).hexdigest(),
                        "testNode": TEST_NODE,
                        "cases": report_cases,
                        "passed": all(item["passed"] for item in report_cases),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )

        _run_real_model_if_requested(
            lambda output_path: _execute_real_model_cases(
                db,
                output_path=output_path,
                golden=golden,
                fixtures=fixtures,
                assets=assets,
                workspace=workspace,
                user=user,
                embedding_provider=provider,
                image_bytes_loader=image_bytes_loader,
            )
        )


def test_m402_worker_executes_every_golden_evidence_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _run_m402_golden_acceptance(monkeypatch)


def test_m402_answer_mixed_compare_stays_offline_without_minio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for CI run 32010694251: answer-mixed-compare hit MinIO retries.

    Persist the full golden fixture set (same as the acceptance node) so retrieval
    ranking matches production acceptance; only execute the historically failing
    answer case, and prove chat never touches live object storage.
    """
    _forbid_live_object_storage(monkeypatch)
    _install_deterministic_m402_ids(monkeypatch, namespace="m402-golden-mixed-compare")
    golden, _failures, _report = load_multimodal_quality_suite(
        REPOSITORY_ROOT,
        EVAL_ROOT / "multimodal-golden-v1.json",
        EVAL_ROOT / "multimodal-failures-v1.json",
    )
    case = next(item for item in golden.cases if item.id == "answer-mixed-compare")
    fixtures = {fixture.id: fixture for fixture in golden.fixtures}
    offline_store = _fixture_object_store(golden.fixtures)
    image_bytes_loader = _offline_image_bytes_loader(offline_store)
    loader_hits: list[str] = []

    def tracked_loader(object_key: str) -> bytes:
        loader_hits.append(object_key)
        return image_bytes_loader(object_key)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user, workspace = _persist_identity(db)
        assets = _persist_fixture_assets(db, golden.fixtures)
        provider = _add_embeddings(db, assets)
        generation = GoldenGenerationProvider(
            {case.question: " ".join(case.expected_answer_points)}
        )
        thread = ChatThread(
            id="m402-thread-mixed-compare",
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            last_message_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db.add(thread)
        db.commit()
        completed = complete_chat(
            db,
            workspace_id=workspace.id,
            user_id=user.id,
            thread=thread,
            question=case.question,
            asset_scope=_case_scope(case, assets),
            embedding_provider=provider,
            generation_provider=generation,
            image_bytes_loader=tracked_loader,
        )
        assert all(
            point in completed.assistant_message.content for point in case.expected_answer_points
        )
        for target in case.evidence_targets:
            assert _citations_cover_target(
                db,
                completed.citations,
                assets[target.fixture_id],
                fixtures[target.fixture_id],
                target,
            ), (case.id, target.fixture_id)
        assert loader_hits, "visual enrichment should load offline PDF bytes"
        assert all(key.startswith("m402/") for key in loader_hits)


def test_m402_real_model_runner_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("M402_REAL_MODEL_REPORT_PATH", raising=False)
    called = False

    def run(_path: Path) -> None:
        nonlocal called
        called = True

    _run_real_model_if_requested(run)

    assert called is False


def test_m402_real_model_runner_preserves_all_results_before_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    golden, _failures, _report = load_multimodal_quality_suite(
        REPOSITORY_ROOT,
        EVAL_ROOT / "multimodal-golden-v1.json",
        EVAL_ROOT / "multimodal-failures-v1.json",
    )
    answer_cases = [case for case in golden.cases if case.layer == "answer"]
    answers = {
        case.question: (
            " ".join(case.expected_answer_points)
            if case.expected_disposition == "answer"
            else "The selected assets do not contain supporting evidence for that claim."
        )
        for case in answer_cases
    }

    class FirstCallFailingProvider(GoldenGenerationProvider):
        def generate(self, messages) -> str:
            if answer_cases[0].question in str(messages[-1]["content"]):
                raise RuntimeError("injected provider failure")
            return super().generate(messages)

    output_path = tmp_path / "real-model-execution.json"
    monkeypatch.delenv("M402_WORKER_REPORT_PATH", raising=False)
    monkeypatch.setenv("M402_REAL_MODEL_REPORT_PATH", str(output_path))
    monkeypatch.setattr(
        sys.modules[__name__],
        "get_generation_provider",
        lambda: FirstCallFailingProvider(answers),
    )

    with pytest.raises(AssertionError, match="answer-pdf-table"):
        _run_m402_golden_acceptance(monkeypatch)

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["passed"] is False
    assert len(payload["cases"]) == 7
    assert payload["cases"][0]["output"] == ""
    assert payload["cases"][0]["passed"] is False
    assert payload["cases"][0]["error"] == "RuntimeError: injected provider failure"
    assert len(payload["cases"][0]["generationMessages"]) == 2
    assert all(case["error"] is None for case in payload["cases"][1:])
    assert all(case["passed"] is True for case in payload["cases"][1:])
    assert payload["testFileSha256"] == sha256(Path(__file__).read_bytes()).hexdigest()
