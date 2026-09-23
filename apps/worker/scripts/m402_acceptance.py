from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import Session

from ai_pdf_api.core.security import hash_password
from ai_pdf_api.core.settings import settings
from ai_pdf_api.db.base import Base
from ai_pdf_api.modalities.evidence import clone_evidence_locator
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ChatMessage,
    ChatThread,
    EvidenceLocator,
    ImageLocatorDetail,
    MessageCitation,
    PdfLocatorDetail,
    SpatialLocatorRegion,
    User,
    Workspace,
    WorkspaceMembership,
)
from ai_pdf_api.services.multimodal_quality import GoldenEvidenceTarget, load_multimodal_quality_suite
from ai_pdf_api.services.storage import delete_objects_with_prefix, upload_bytes
from ai_pdf_worker.ingestion.image_ingestion import ImageIngestionAdapter, extract_image_text_with_ocr
from ai_pdf_worker.ingestion.pdf_ingestion import PdfIngestionAdapter


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = REPOSITORY_ROOT / "docs/evals"


class AcceptanceCaptionProvider:
    provider = "m402-acceptance"
    model = "deterministic-caption"
    version = "m402-v1"
    detail = "high"
    max_output_tokens = 320

    def caption(self, payload: bytes, *, content_type: str) -> str:
        assert payload.startswith(b"\x89PNG")
        assert content_type == "image/png"
        return "Release 4 begins the sustained drop. Verify chart and caption together."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or clean the live M402 acceptance workspace.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    setup = subparsers.add_parser("setup")
    setup.add_argument("--output", type=Path, required=True)
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--state", type=Path, required=True)
    return parser.parse_args()


def _caption_config() -> dict[str, object]:
    return {
        "imageCaptionProvider": AcceptanceCaptionProvider.provider,
        "imageCaptionModel": AcceptanceCaptionProvider.model,
        "imageCaptionVersion": AcceptanceCaptionProvider.version,
        "imageCaptionDetail": AcceptanceCaptionProvider.detail,
        "imageCaptionMaxOutputTokens": AcceptanceCaptionProvider.max_output_tokens,
    }


def _region(payload: dict[str, object]) -> tuple[float, float, float, float]:
    return tuple(float(payload[key]) for key in ("x", "y", "width", "height"))  # type: ignore[return-value]


def _approved_coverage_ratio(
    approved: tuple[float, float, float, float],
    rendered: tuple[float, float, float, float],
) -> float:
    approved_x, approved_y, approved_width, approved_height = approved
    rendered_x, rendered_y, rendered_width, rendered_height = rendered
    width = max(0.0, min(approved_x + approved_width, rendered_x + rendered_width) - max(approved_x, rendered_x))
    height = max(0.0, min(approved_y + approved_height, rendered_y + rendered_height) - max(approved_y, rendered_y))
    return width * height / (approved_width * approved_height)


def _expected_regions(fixture, target: GoldenEvidenceTarget) -> list[tuple[float, float, float, float]]:
    manifest = json.loads((REPOSITORY_ROOT / fixture.manifest_path).read_text(encoding="utf-8"))
    if fixture.modality == "image":
        by_label = {item["label"]: item for item in manifest["regions"]}
        return [_region(by_label[label]) for label in target.region_labels]
    page = next(item for item in manifest["pages"] if item["label"] == target.page_label)
    return [_region(page["regions"][index]) for index in target.region_indexes]


def _create_asset(
    db: Session,
    *,
    fixture,
    workspace: Workspace,
    user: User,
    now: datetime,
) -> tuple[Asset, bytes]:
    source_path = REPOSITORY_ROOT / fixture.source_path
    payload = source_path.read_bytes()
    asset = Asset(
        id=str(uuid4()),
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        asset_kind=fixture.modality,
        title=source_path.name,
        source_filename=source_path.name,
        object_key=f"workspaces/{workspace.id}/assets/{uuid4()}/source/{source_path.name}",
        mime_type="application/pdf" if fixture.modality == "pdf" else "image/png",
        byte_size=len(payload),
        source_sha256=sha256(payload).hexdigest(),
        status="parsing",
        current_processing_generation=1,
        current_index_version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(asset)
    db.flush()
    upload_bytes(asset.object_key, payload, asset.mime_type)
    if fixture.modality == "pdf":
        PdfIngestionAdapter().ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=1,
            config_snapshot={"chunkSize": 1200},
            created_at=now,
        )
    else:
        result = ImageIngestionAdapter(
            caption_provider=AcceptanceCaptionProvider(),
            ocr_extractor=extract_image_text_with_ocr,
        ).ingest(
            db,
            asset=asset,
            payload=payload,
            processing_generation=1,
            config_snapshot=_caption_config(),
            created_at=now,
        )
        for generated in result.generated_objects:
            upload_bytes(generated.object_key, generated.payload, generated.content_type)
    asset.status = "ready"
    db.flush()
    return asset, payload


def _source_pdf_locator(
    db: Session,
    *,
    asset: Asset,
    fixture,
    target: GoldenEvidenceTarget,
) -> EvidenceLocator:
    candidates = db.scalars(
        select(EvidenceLocator)
        .join(PdfLocatorDetail, PdfLocatorDetail.locator_id == EvidenceLocator.id)
        .where(
            EvidenceLocator.asset_id == asset.id,
            EvidenceLocator.locator_kind == target.locator_kind,
            PdfLocatorDetail.page_number == target.page_number,
        )
    ).all()
    if target.locator_kind == "pdf_page":
        if not candidates:
            raise RuntimeError(f"No PDF page locator for {target.page_label}")
        return candidates[0]
    expected = _expected_regions(fixture, target)
    for candidate in candidates:
        actual = [
            (region.x, region.y, region.width, region.height)
            for region in db.scalars(
                select(SpatialLocatorRegion).where(SpatialLocatorRegion.locator_id == candidate.id)
            ).all()
        ]
        if all(any(_approved_coverage_ratio(region, item) >= 0.1 for item in actual) for region in expected):
            return candidate
    raise RuntimeError(f"No PDF region locator covers {target.page_label}")


def _explicit_image_locator(
    db: Session,
    *,
    asset: Asset,
    fixture,
    target: GoldenEvidenceTarget,
    now: datetime,
) -> EvidenceLocator:
    representation = db.scalar(
        select(AssetRepresentation).where(
            AssetRepresentation.asset_id == asset.id,
            AssetRepresentation.representation_kind == "image_caption",
            AssetRepresentation.processing_generation == 1,
        )
    )
    if representation is None:
        raise RuntimeError("Image caption representation is missing")
    locator = EvidenceLocator(
        workspace_id=asset.workspace_id,
        asset_id=asset.id,
        locator_kind="image_region",
        locator_version=1,
        processing_generation_snapshot=1,
        representation_id_snapshot=representation.id,
        created_at=now,
    )
    db.add(locator)
    db.flush()
    db.add(
        ImageLocatorDetail(
            locator_id=locator.id,
            coordinate_space="image_normalized_top_left_v1",
            width_pixels=1200,
            height_pixels=800,
            orientation_applied=True,
        )
    )
    db.add_all(
        [
            SpatialLocatorRegion(
                locator_id=locator.id,
                region_order=index,
                x=region[0],
                y=region[1],
                width=region[2],
                height=region[3],
            )
            for index, region in enumerate(_expected_regions(fixture, target))
        ]
    )
    db.flush()
    return locator


def _seed_evidence_thread(
    db: Session,
    *,
    golden,
    fixtures,
    assets: dict[str, Asset],
    workspace: Workspace,
    user: User,
    now: datetime,
) -> tuple[ChatThread, dict[str, list[str]]]:
    thread = ChatThread(
        workspace_id=workspace.id,
        created_by_user_id=user.id,
        title="M402 Evidence",
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(thread)
    db.flush()
    parent_id: str | None = None
    case_citations: dict[str, list[str]] = {}
    image_locators: dict[tuple[str, ...], EvidenceLocator] = {}
    evidence_cases = [case for case in golden.cases if case.layer == "evidence"]
    for case_index, case in enumerate(evidence_cases):
        created_at = now + timedelta(seconds=case_index + 1)
        user_message = ChatMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            parent_message_id=parent_id,
            role="user",
            content=case.question,
            status="completed",
            created_at=created_at,
        )
        db.add(user_message)
        db.flush()
        assistant = ChatMessage(
            workspace_id=workspace.id,
            thread_id=thread.id,
            parent_message_id=user_message.id,
            role="assistant",
            content=f"M402 evidence case {case.id}",
            status="completed",
            model_provider="m402",
            model_name="seeded-evidence",
            created_at=created_at + timedelta(milliseconds=1),
        )
        db.add(assistant)
        db.flush()
        citation_ids: list[str] = []
        for citation_index, target in enumerate(case.evidence_targets):
            fixture = fixtures[target.fixture_id]
            asset = assets[target.fixture_id]
            if fixture.modality == "pdf":
                source = _source_pdf_locator(db, asset=asset, fixture=fixture, target=target)
            else:
                image_key = tuple(target.region_labels)
                source = image_locators.get(image_key)
                if source is None:
                    source = _explicit_image_locator(
                        db,
                        asset=asset,
                        fixture=fixture,
                        target=target,
                        now=created_at,
                    )
                    image_locators[image_key] = source
            locator = clone_evidence_locator(
                db,
                source.id,
                created_at=created_at,
                workspace_id=workspace.id,
                asset_id=asset.id,
            )
            representation = db.get(AssetRepresentation, locator.representation_id_snapshot)
            if representation is None:
                raise RuntimeError("Evidence representation is missing")
            citation = MessageCitation(
                workspace_id=workspace.id,
                message_id=assistant.id,
                citation_index=citation_index,
                evidence_locator_id=locator.id,
                asset_id=asset.id,
                asset_kind_snapshot=asset.asset_kind,
                asset_title_snapshot=asset.title,
                excerpt_snapshot=f"M402 {case.id}",
                processing_generation_snapshot=locator.processing_generation_snapshot,
                representation_id_snapshot=locator.representation_id_snapshot,
                parser_version_snapshot=representation.generator_version,
                index_version_snapshot=asset.current_index_version,
                created_at=created_at,
            )
            db.add(citation)
            db.flush()
            citation_ids.append(citation.id)
        case_citations[case.id] = citation_ids
        parent_id = assistant.id
    thread.active_message_id = parent_id
    thread.last_message_at = now + timedelta(seconds=len(evidence_cases) + 1)
    thread.updated_at = thread.last_message_at
    db.flush()
    return thread, case_citations


def setup(output: Path) -> None:
    golden, _failures, _report = load_multimodal_quality_suite(
        REPOSITORY_ROOT,
        EVAL_ROOT / "multimodal-golden-v1.json",
        EVAL_ROOT / "multimodal-failures-v1.json",
    )
    fixtures = {fixture.id: fixture for fixture in golden.fixtures}
    engine = create_engine(settings.database_url, future=True)
    run_id = uuid4().hex[:12]
    user_id = str(uuid4())
    workspace_id = str(uuid4())
    email = f"m402-{run_id}@example.com"
    password = f"M402-{run_id}!"
    now = datetime.now(UTC)
    try:
        with Session(engine) as db:
            user = User(
                id=user_id,
                email=email,
                name="M402 Acceptance",
                password_hash=hash_password(password),
                avatar_url="https://example.com/m402.svg",
                created_at=now,
                updated_at=now,
            )
            db.add(user)
            db.flush()
            workspace = Workspace(
                id=workspace_id,
                name=f"M402 Acceptance {run_id}",
                description="Temporary live full-stack acceptance workspace",
                system_prompt="Answer only from supplied evidence.",
                retrieval_top_k=10,
                created_by_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
            db.add(workspace)
            db.flush()
            db.add(WorkspaceMembership(workspace_id=workspace.id, user_id=user.id, role="owner"))
            db.flush()
            assets: dict[str, Asset] = {}
            for fixture in golden.fixtures:
                asset, _payload = _create_asset(
                    db,
                    fixture=fixture,
                    workspace=workspace,
                    user=user,
                    now=now,
                )
                assets[fixture.id] = asset
            thread, case_citations = _seed_evidence_thread(
                db,
                golden=golden,
                fixtures=fixtures,
                assets=assets,
                workspace=workspace,
                user=user,
                now=now,
            )
            db.commit()
            state = {
                "schemaVersion": "m402-live-state-v1",
                "runId": run_id,
                "email": email,
                "password": password,
                "userId": user.id,
                "workspaceId": workspace.id,
                "threadId": thread.id,
                "assets": {fixture_id: asset.id for fixture_id, asset in assets.items()},
                "caseCitations": case_citations,
            }
        _write_state_atomic(output, state)
    except BaseException as setup_error:
        try:
            _cleanup_workspace_resources(engine, workspace_id=workspace_id, user_id=user_id)
        except Exception as cleanup_error:
            raise BaseExceptionGroup(
                "M402 setup failed and compensation cleanup was incomplete.",
                [setup_error, cleanup_error],
            ) from setup_error
        raise
    print(json.dumps({key: value for key, value in state.items() if key != "password"}))


def cleanup(state_path: Path) -> None:
    state = json.loads(state_path.read_text(encoding="utf-8"))
    workspace_id = state["workspaceId"]
    user_id = state["userId"]
    engine = create_engine(settings.database_url, future=True)
    _cleanup_workspace_resources(engine, workspace_id=workspace_id, user_id=user_id)
    print(json.dumps({"cleanedWorkspaceId": workspace_id, "cleanedUserId": user_id}))


def _write_state_atomic(output: Path, state: dict[str, object]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{state['runId']}.tmp")
    try:
        temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)


def _cleanup_workspace_resources(engine, *, workspace_id: str, user_id: str) -> None:
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
        raise ExceptionGroup("M402 resource cleanup failed.", errors)


def main() -> None:
    args = parse_args()
    if args.command == "setup":
        setup(args.output)
    else:
        cleanup(args.state)


if __name__ == "__main__":
    main()
