from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from ai_pdf_api.modalities.image_caption import image_caption_config_snapshot
from ai_pdf_api.modalities.document import (
    detect_markdown_mime_type,
    validate_markdown_upload_payload,
)


class ModalityContractError(ValueError):
    pass


@dataclass(frozen=True)
class TypeRegistration:
    kind: str
    contract_version: int = 1
    detail_family: str | None = None


@dataclass(frozen=True)
class RetrievalChannelRegistration:
    kind: str
    embedding_space: str
    type_signatures: frozenset[tuple[str, str, str]]


@dataclass(frozen=True)
class RetrievalChannelScope:
    kind: str
    embedding_space: str
    type_signatures: frozenset[tuple[str, str, str, str]]


@dataclass(frozen=True)
class ModalityModule:
    asset_kind: str
    contract_version: int
    enabled: bool
    supported_mime_types: frozenset[str]
    byte_inspector: Callable[[bytes], str | None]
    representation_types: tuple[TypeRegistration, ...]
    content_unit_types: tuple[TypeRegistration, ...]
    locator_types: tuple[TypeRegistration, ...]
    retrieval_channels: tuple[RetrievalChannelRegistration, ...]
    metrics_namespace: str
    ingestion_config_snapshot: Callable[[], Mapping[str, object]]
    # Optional full-body upload validator. When set, the upload router may load the
    # complete bounded payload for this modality only; PDF/Image leave this unset.
    full_payload_validator: Callable[[bytes], None] | None = None


@dataclass(frozen=True)
class CatalogSnapshot:
    enabled_assets: frozenset[tuple[str, int]]
    representations: frozenset[tuple[str, str, int]]
    content_units: frozenset[tuple[str, str, int]]
    locators: frozenset[tuple[str, int, str]]
    embedding_spaces: frozenset[tuple[str, int]]


class ModalityRegistry:
    def __init__(self, modules: Iterable[ModalityModule], *, embedding_spaces: Iterable[TypeRegistration]) -> None:
        modules_by_kind: dict[str, ModalityModule] = {}
        mime_owners: dict[str, str] = {}
        for module in modules:
            self._validate_module(module)
            if module.asset_kind in modules_by_kind:
                raise ModalityContractError(f"Duplicate asset kind: {module.asset_kind}")
            modules_by_kind[module.asset_kind] = module
            for mime_type in module.supported_mime_types:
                previous_owner = mime_owners.setdefault(mime_type, module.asset_kind)
                if previous_owner != module.asset_kind:
                    raise ModalityContractError(
                        f"MIME type {mime_type} is registered by both {previous_owner} and {module.asset_kind}"
                    )

        spaces = tuple(embedding_spaces)
        self._assert_unique_kinds(spaces, owner="embedding space")
        embedding_space_kinds = {item.kind for item in spaces}
        for module in modules_by_kind.values():
            for channel in module.retrieval_channels:
                if channel.embedding_space not in embedding_space_kinds:
                    raise ModalityContractError(
                        f"Retrieval channel {channel.kind} uses an unregistered embedding space"
                    )
        self._modules = modules_by_kind
        self._mime_owners = mime_owners
        self._embedding_spaces = spaces

    @property
    def asset_kinds(self) -> frozenset[str]:
        return frozenset(self._modules)

    @property
    def enabled_asset_kinds(self) -> frozenset[str]:
        return frozenset(
            module.asset_kind for module in self._modules.values() if module.enabled
        )

    def get(self, asset_kind: str) -> ModalityModule:
        try:
            return self._modules[asset_kind]
        except KeyError as error:
            raise ModalityContractError(f"Unsupported asset kind: {asset_kind}") from error

    def ingestion_config_snapshot(self, asset_kind: str) -> dict[str, object]:
        snapshot = self.get(asset_kind).ingestion_config_snapshot()
        if not isinstance(snapshot, Mapping) or any(
            not isinstance(key, str) or not key for key in snapshot
        ):
            raise ModalityContractError(
                f"Modality {asset_kind} returned an invalid ingestion config snapshot"
            )
        reserved = {
            "source",
            "embeddingProvider",
            "embeddingModel",
            "embeddingDimensions",
            "embeddingVersion",
            "chunkSize",
        }
        collisions = reserved.intersection(snapshot)
        if collisions:
            raise ModalityContractError(
                f"Modality {asset_kind} ingestion config overrides shared keys: "
                f"{','.join(sorted(collisions))}"
            )
        return dict(snapshot)

    def retrieval_channel_scope(self, channel_kind: str) -> RetrievalChannelScope:
        registrations = [
            (module, channel)
            for module in self._modules.values()
            for channel in module.retrieval_channels
            if channel.kind == channel_kind
        ]
        if not registrations:
            raise ModalityContractError(f"Unsupported retrieval channel: {channel_kind}")
        embedding_spaces = {channel.embedding_space for _module, channel in registrations}
        if len(embedding_spaces) != 1:
            raise ModalityContractError(
                f"Retrieval channel {channel_kind} uses inconsistent embedding spaces"
            )
        return RetrievalChannelScope(
            kind=channel_kind,
            embedding_space=embedding_spaces.pop(),
            type_signatures=frozenset(
                (module.asset_kind, unit_kind, representation_kind, locator_kind)
                for module, channel in registrations
                for unit_kind, representation_kind, locator_kind in channel.type_signatures
            ),
        )

    def inspect_upload(self, mime_type: str, header: bytes) -> ModalityModule:
        normalized_mime_type = mime_type.lower()
        module = self.for_mime_type(normalized_mime_type)
        detected_mime_type = module.byte_inspector(header)
        if detected_mime_type != normalized_mime_type:
            raise ModalityContractError(
                f"File signature does not match declared MIME type: {normalized_mime_type}"
            )
        return module

    def validate_upload_payload(self, module: ModalityModule, payload: bytes) -> None:
        """Run a modality's optional full-payload validator when registered."""
        validator = module.full_payload_validator
        if validator is None:
            return
        try:
            validator(payload)
        except ValueError as error:
            raise ModalityContractError(str(error)) from error

    def for_mime_type(self, mime_type: str) -> ModalityModule:
        asset_kind = self._mime_owners.get(mime_type.lower())
        if asset_kind is None:
            raise ModalityContractError(f"Unsupported MIME type: {mime_type}")
        module = self._modules[asset_kind]
        if not module.enabled:
            raise ModalityContractError(
                f"Asset kind is not enabled for ingestion: {module.asset_kind}"
            )
        return module

    def expected_catalog(self) -> CatalogSnapshot:
        return CatalogSnapshot(
            enabled_assets=frozenset(
                (module.asset_kind, module.contract_version)
                for module in self._modules.values()
                if module.enabled
            ),
            representations=frozenset(
                (module.asset_kind, item.kind, item.contract_version)
                for module in self._modules.values()
                for item in module.representation_types
            ),
            content_units=frozenset(
                (module.asset_kind, item.kind, item.contract_version)
                for module in self._modules.values()
                for item in module.content_unit_types
            ),
            locators=frozenset(
                (item.kind, item.contract_version, item.detail_family or "")
                for module in self._modules.values()
                for item in module.locator_types
            ),
            embedding_spaces=frozenset(
                (item.kind, item.contract_version) for item in self._embedding_spaces
            ),
        )

    def validate_catalog(self, actual: CatalogSnapshot) -> None:
        expected = self.expected_catalog()
        if actual != expected:
            raise ModalityContractError(
                "Modality catalog does not match the deployment registry: "
                f"expected={expected!r} actual={actual!r}"
            )

    @classmethod
    def _validate_module(cls, module: ModalityModule) -> None:
        if not module.asset_kind or not module.supported_mime_types:
            raise ModalityContractError("A modality requires an asset kind and at least one MIME type")
        if module.contract_version < 1:
            raise ModalityContractError("Contract versions start at 1")
        if not module.metrics_namespace:
            raise ModalityContractError("A modality requires a metrics namespace")
        cls._assert_unique_kinds(module.representation_types, owner=f"{module.asset_kind} representation")
        cls._assert_unique_kinds(module.content_unit_types, owner=f"{module.asset_kind} content unit")
        cls._assert_unique_kinds(module.locator_types, owner=f"{module.asset_kind} locator")
        cls._assert_unique_retrieval_channels(module)
        for locator in module.locator_types:
            if locator.detail_family not in {"spatial", "temporal", "record"}:
                raise ModalityContractError(
                    f"Locator {locator.kind} requires a registered detail family"
                )

    @staticmethod
    def _assert_unique_retrieval_channels(module: ModalityModule) -> None:
        content_unit_kinds = {item.kind for item in module.content_unit_types}
        representation_kinds = {item.kind for item in module.representation_types}
        locator_kinds = {item.kind for item in module.locator_types}
        seen: set[str] = set()
        for channel in module.retrieval_channels:
            if not channel.kind or channel.kind in seen:
                raise ModalityContractError(
                    f"Duplicate or empty {module.asset_kind} retrieval channel: {channel.kind}"
                )
            seen.add(channel.kind)
            if not channel.embedding_space:
                raise ModalityContractError(
                    f"Retrieval channel {channel.kind} requires an embedding space"
                )
            if not channel.type_signatures:
                raise ModalityContractError(
                    f"Retrieval channel {channel.kind} requires type signatures"
                )
            for unit_kind, representation_kind, locator_kind in channel.type_signatures:
                if unit_kind not in content_unit_kinds:
                    raise ModalityContractError(
                        f"Retrieval channel {channel.kind} contains an unregistered content unit kind"
                    )
                if representation_kind not in representation_kinds:
                    raise ModalityContractError(
                        f"Retrieval channel {channel.kind} contains an unregistered representation kind"
                    )
                if locator_kind not in locator_kinds:
                    raise ModalityContractError(
                        f"Retrieval channel {channel.kind} contains an unregistered locator kind"
                    )

    @staticmethod
    def _assert_unique_kinds(items: Iterable[TypeRegistration], *, owner: str) -> None:
        kinds: set[str] = set()
        for item in items:
            if not item.kind:
                raise ModalityContractError(f"Empty {owner} kind")
            if item.contract_version < 1:
                raise ModalityContractError(f"Invalid contract version for {item.kind}")
            if item.kind in kinds:
                raise ModalityContractError(f"Duplicate {owner} kind: {item.kind}")
            kinds.add(item.kind)


def _detect_pdf_mime_type(header: bytes) -> str | None:
    return "application/pdf" if header.startswith(b"%PDF-") else None


def _detect_image_mime_type(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if (
        len(header) >= 16
        and header[:4] == b"RIFF"
        and header[8:12] == b"WEBP"
        and header[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
    ):
        return "image/webp"
    return None


PDF_MODULE = ModalityModule(
    asset_kind="pdf",
    contract_version=1,
    enabled=True,
    supported_mime_types=frozenset({"application/pdf"}),
    byte_inspector=_detect_pdf_mime_type,
    representation_types=(
        TypeRegistration("pdf_text_legacy"),
        TypeRegistration("pdf_page_layout"),
        TypeRegistration("pdf_ocr"),
        TypeRegistration("pdf_table"),
        TypeRegistration("pdf_figure"),
    ),
    content_unit_types=(
        TypeRegistration("pdf_text_chunk"),
        TypeRegistration("pdf_ocr_region"),
        TypeRegistration("pdf_table"),
        TypeRegistration("pdf_figure"),
    ),
    locator_types=(
        TypeRegistration("pdf_page", detail_family="spatial"),
        TypeRegistration("pdf_region", detail_family="spatial"),
    ),
    retrieval_channels=(
        RetrievalChannelRegistration(
            kind="text",
            embedding_space="text",
            type_signatures=frozenset(
                {
                    ("pdf_text_chunk", "pdf_text_legacy", "pdf_page"),
                    ("pdf_text_chunk", "pdf_page_layout", "pdf_page"),
                    ("pdf_text_chunk", "pdf_ocr", "pdf_page"),
                    ("pdf_ocr_region", "pdf_ocr", "pdf_region"),
                    ("pdf_table", "pdf_table", "pdf_region"),
                    ("pdf_figure", "pdf_figure", "pdf_region"),
                }
            ),
        ),
    ),
    metrics_namespace="pdf",
    ingestion_config_snapshot=dict,
)


IMAGE_MODULE = ModalityModule(
    asset_kind="image",
    contract_version=1,
    enabled=True,
    supported_mime_types=frozenset({"image/jpeg", "image/png", "image/webp"}),
    byte_inspector=_detect_image_mime_type,
    representation_types=(
        TypeRegistration("image_oriented"),
        TypeRegistration("image_ocr"),
        TypeRegistration("image_caption"),
    ),
    content_unit_types=(
        TypeRegistration("image_ocr_region"),
        TypeRegistration("image_caption"),
    ),
    locator_types=(TypeRegistration("image_region", detail_family="spatial"),),
    retrieval_channels=(
        RetrievalChannelRegistration(
            kind="text",
            embedding_space="text",
            type_signatures=frozenset(
                {
                    ("image_ocr_region", "image_ocr", "image_region"),
                    ("image_caption", "image_caption", "image_region"),
                }
            ),
        ),
    ),
    metrics_namespace="image",
    ingestion_config_snapshot=image_caption_config_snapshot,
)

DOCUMENT_MODULE = ModalityModule(
    asset_kind="document",
    contract_version=1,
    enabled=True,
    supported_mime_types=frozenset({"text/markdown"}),
    byte_inspector=detect_markdown_mime_type,
    representation_types=(
        TypeRegistration("document_source"),
        TypeRegistration("document_normalized"),
    ),
    content_unit_types=(
        TypeRegistration("document_block"),
        TypeRegistration("document_text_chunk"),
    ),
    locator_types=(TypeRegistration("document_anchor", detail_family="record"),),
    retrieval_channels=(
        RetrievalChannelRegistration(
            kind="text",
            embedding_space="text",
            type_signatures=frozenset(
                {
                    ("document_text_chunk", "document_normalized", "document_anchor"),
                }
            ),
        ),
    ),
    metrics_namespace="document",
    ingestion_config_snapshot=lambda: {
        "documentFormat": "markdown",
        "documentParserVersion": "document-parser-v1",
        "documentNormalizationVersion": "document-normalization-v1",
    },
    full_payload_validator=validate_markdown_upload_payload,
)


def build_production_registry() -> ModalityRegistry:
    return ModalityRegistry(
        (PDF_MODULE, IMAGE_MODULE, DOCUMENT_MODULE),
        embedding_spaces=(TypeRegistration("text"),),
    )
