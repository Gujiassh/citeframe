from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from math import sqrt

from pgvector.sqlalchemy import BIT, Vector
from sqlalchemy import Select, and_, bindparam, case, cast, desc, func, literal, or_, select
from sqlalchemy.orm import Session

from ai_pdf_api.core.metrics import observe_retrieval
from ai_pdf_api.core.settings import RetrievalStrategy, settings
from ai_pdf_api.modalities.evidence import (
    EvidenceRetrievalSource,
    evidence_retrieval_keys,
)
from ai_pdf_api.modalities.registry import RetrievalChannelScope, build_production_registry
from ai_pdf_api.models import (
    Asset,
    AssetRepresentation,
    ContentUnit,
    ContentUnitEmbedding,
    EvidenceLocator,
)
from ai_pdf_api.services.embedding_index import (
    assert_current_embeddings_match_contract,
    resolve_embedding_index_contract,
)
from ai_pdf_api.services.providers import EmbeddingProvider

logger = logging.getLogger(__name__)

_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_LATIN_WORD = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class RetrievedContent:
    content_unit: ContentUnit
    asset: Asset
    locator: EvidenceLocator
    channel: str
    distance: float
    location_key: tuple[str, str]


RetrievedRow = tuple[ContentUnit, Asset, EvidenceLocator, AssetRepresentation]


TEXT_CHANNEL = build_production_registry().retrieval_channel_scope("text")
BINARY_ANN_CANDIDATE_MULTIPLIER = 3


def retrieval_scope_statement(
    workspace_id: str,
    asset_ids: list[str] | None,
    channel: RetrievalChannelScope,
) -> Select[RetrievedRow]:
    type_filters = [
        and_(
            Asset.asset_kind == asset_kind,
            ContentUnit.unit_kind == unit_kind,
            AssetRepresentation.representation_kind == representation_kind,
            EvidenceLocator.locator_kind == locator_kind,
        )
        for asset_kind, unit_kind, representation_kind, locator_kind in sorted(
            channel.type_signatures
        )
    ]
    statement = (
        select(ContentUnit, Asset, EvidenceLocator, AssetRepresentation)
        .join(Asset, Asset.id == ContentUnit.asset_id)
        .join(AssetRepresentation, AssetRepresentation.id == ContentUnit.representation_id)
        .join(EvidenceLocator, EvidenceLocator.id == ContentUnit.source_locator_id)
        .where(
            ContentUnit.workspace_id == workspace_id,
            Asset.workspace_id == workspace_id,
            AssetRepresentation.workspace_id == workspace_id,
            EvidenceLocator.workspace_id == workspace_id,
            ContentUnit.asset_id == Asset.id,
            AssetRepresentation.asset_id == Asset.id,
            EvidenceLocator.asset_id == Asset.id,
            ContentUnit.representation_id == AssetRepresentation.id,
            EvidenceLocator.representation_id_snapshot == AssetRepresentation.id,
            EvidenceLocator.processing_generation_snapshot == Asset.current_processing_generation,
            AssetRepresentation.processing_generation == Asset.current_processing_generation,
            ContentUnit.index_version == Asset.current_index_version,
            Asset.status == "ready",
            Asset.deleted_at.is_(None),
            or_(*type_filters),
        )
    )
    if asset_ids is not None:
        statement = statement.where(ContentUnit.asset_id.in_(asset_ids))
    return statement


def retrieve_content(
    db: Session,
    workspace_id: str,
    query_embedding: list[float],
    *,
    asset_ids: list[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    limit: int = 6,
) -> list[RetrievedContent]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if asset_ids == []:
        return []
    contract = resolve_embedding_index_contract(embedding_provider)
    assert_current_embeddings_match_contract(
        db,
        workspace_id,
        contract,
        asset_ids=asset_ids,
    )
    provider_name = contract.provider
    provider_model = contract.model
    provider_version = contract.version
    provider_dimensions = contract.dimensions

    statement = retrieval_scope_statement(workspace_id, asset_ids, TEXT_CHANNEL)
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        sqlite_statement = statement.join(
            ContentUnitEmbedding,
            (ContentUnitEmbedding.content_unit_id == ContentUnit.id)
            & (ContentUnitEmbedding.asset_id == ContentUnit.asset_id)
            & (
                ContentUnitEmbedding.processing_generation
                == EvidenceLocator.processing_generation_snapshot
            )
            & (
                ContentUnitEmbedding.processing_generation
                == Asset.current_processing_generation
            )
            & (ContentUnitEmbedding.index_version == ContentUnit.index_version)
            & (ContentUnitEmbedding.index_version == Asset.current_index_version),
        ).where(
            *_embedding_scope_filters(
                workspace_id,
                provider_name,
                provider_model,
                provider_version,
                provider_dimensions,
                asset_ids,
            )
        )
        return _retrieve_sqlite(db, sqlite_statement, query_embedding, limit)

    candidate_limit = limit
    while True:
        rows = _load_dense_ranked_rows(
            db,
            statement,
            workspace_id,
            asset_ids,
            query_embedding,
            provider_name,
            provider_model,
            provider_version,
            provider_dimensions,
            candidate_limit,
        )
        candidates = _candidates(
            db,
            [
                (unit, asset, locator, representation, float(distance_value))
                for unit, asset, locator, representation, distance_value in rows
            ],
        )
        unique = _dedupe_locations(candidates)
        if len(unique) >= limit or len(rows) < candidate_limit:
            return unique[:limit]
        candidate_limit *= 2


def _embedding_scope_filters(
    workspace_id: str,
    provider_name: str,
    provider_model: str,
    provider_version: str,
    provider_dimensions: int,
    asset_ids: list[str] | None = None,
) -> tuple:
    filters = (
        ContentUnitEmbedding.workspace_id == workspace_id,
        ContentUnitEmbedding.is_current.is_(True),
        ContentUnitEmbedding.embedding_space == TEXT_CHANNEL.embedding_space,
        ContentUnitEmbedding.provider == provider_name,
        ContentUnitEmbedding.model == provider_model,
        ContentUnitEmbedding.version == provider_version,
        ContentUnitEmbedding.dimensions == provider_dimensions,
    )
    if asset_ids is not None:
        return (*filters, ContentUnitEmbedding.asset_id.in_(asset_ids))
    return filters


def _dense_ann_ranked_statement(
    scoped_statement: Select[RetrievedRow],
    workspace_id: str,
    asset_ids: list[str] | None,
    query_embedding: list[float],
    provider_name: str,
    provider_model: str,
    provider_version: str,
    provider_dimensions: int,
    *,
    ann_limit: int,
) -> Select:
    distance = ContentUnitEmbedding.embedding.cosine_distance(query_embedding).label("distance")
    scope_filters = _embedding_scope_filters(
        workspace_id,
        provider_name,
        provider_model,
        provider_version,
        provider_dimensions,
        asset_ids,
    )
    cosine_ann_candidates = (
        select(
            ContentUnitEmbedding.id.label("embedding_id"),
            ContentUnitEmbedding.content_unit_id.label("content_unit_id"),
            ContentUnitEmbedding.asset_id.label("asset_id"),
            ContentUnitEmbedding.processing_generation.label("processing_generation"),
            ContentUnitEmbedding.index_version.label("index_version"),
            distance,
        )
        .where(*scope_filters)
        .order_by(distance, ContentUnitEmbedding.id)
        .limit(ann_limit)
        .cte("cosine_ann_candidates")
        .prefix_with("MATERIALIZED")
    )
    binary_embedding = cast(
        func.binary_quantize(ContentUnitEmbedding.embedding),
        BIT(provider_dimensions),
    )
    binary_query = func.binary_quantize(cast(query_embedding, Vector(provider_dimensions)))
    binary_distance = binary_embedding.hamming_distance(binary_query).label(
        "binary_distance"
    )
    binary_ann_candidates = (
        select(
            ContentUnitEmbedding.id.label("embedding_id"),
            ContentUnitEmbedding.content_unit_id.label("content_unit_id"),
            ContentUnitEmbedding.asset_id.label("asset_id"),
            ContentUnitEmbedding.processing_generation.label("processing_generation"),
            ContentUnitEmbedding.index_version.label("index_version"),
            distance,
        )
        .where(*scope_filters)
        .order_by(binary_distance, ContentUnitEmbedding.id)
        .limit(ann_limit * BINARY_ANN_CANDIDATE_MULTIPLIER)
        .cte("binary_ann_candidates")
        .prefix_with("MATERIALIZED")
    )
    candidate_columns = (
        "embedding_id",
        "content_unit_id",
        "asset_id",
        "processing_generation",
        "index_version",
        "distance",
    )
    ann_candidates = (
        select(*(cosine_ann_candidates.c[name] for name in candidate_columns))
        .union(select(*(binary_ann_candidates.c[name] for name in candidate_columns)))
        .cte("ann_candidates")
        .prefix_with("MATERIALIZED")
    )
    return (
        scoped_statement.join(
            ann_candidates,
            (ann_candidates.c.content_unit_id == ContentUnit.id)
            & (ann_candidates.c.asset_id == ContentUnit.asset_id)
            & (
                ann_candidates.c.processing_generation
                == EvidenceLocator.processing_generation_snapshot
            )
            & (
                ann_candidates.c.processing_generation
                == Asset.current_processing_generation
            )
            & (ann_candidates.c.index_version == ContentUnit.index_version)
            & (ann_candidates.c.index_version == Asset.current_index_version),
        )
        .add_columns(ann_candidates.c.distance)
        .order_by(ann_candidates.c.distance, ContentUnit.id)
    )


def _load_dense_ranked_rows(
    db: Session,
    scoped_statement: Select[RetrievedRow],
    workspace_id: str,
    asset_ids: list[str] | None,
    query_embedding: list[float],
    provider_name: str,
    provider_model: str,
    provider_version: str,
    provider_dimensions: int,
    ranked_limit: int,
) -> list:
    ann_limit = ranked_limit
    embedding_count: int | None = None
    while True:
        ranked_statement = _dense_ann_ranked_statement(
            scoped_statement,
            workspace_id,
            asset_ids,
            query_embedding,
            provider_name,
            provider_model,
            provider_version,
            provider_dimensions,
            ann_limit=ann_limit,
        )
        rows = db.execute(ranked_statement.limit(ranked_limit)).all()
        if len(rows) >= ranked_limit:
            return rows
        if embedding_count is None:
            embedding_count = int(
                db.scalar(
                    select(func.count())
                    .select_from(ContentUnitEmbedding)
                    .where(
                        *_embedding_scope_filters(
                            workspace_id,
                            provider_name,
                            provider_model,
                            provider_version,
                            provider_dimensions,
                            asset_ids,
                        )
                    )
                )
                or 0
            )
        if ann_limit >= embedding_count:
            return rows
        ann_limit = min(ann_limit * 2, embedding_count)


def retrieve_lexical_content(
    db: Session,
    workspace_id: str,
    query: str,
    *,
    asset_ids: list[str] | None = None,
    limit: int = 24,
) -> list[RetrievedContent]:
    if limit < 1:
        raise ValueError("limit must be positive")
    if asset_ids == []:
        return []
    terms = _lexical_terms(query)
    if not terms:
        return []
    scoped_statement = retrieval_scope_statement(workspace_id, asset_ids, TEXT_CHANNEL)
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        return _retrieve_lexical_sqlite(db, scoped_statement, query, terms, limit)

    latin_terms = _unique_latin_terms(query)
    if latin_terms:
        def ranked_statement_factory(candidate_limit: int):
            return _latin_lexical_ranked_statement(
                scoped_statement,
                workspace_id,
                asset_ids,
                latin_terms,
                candidate_limit=candidate_limit,
            )

        match_count_statement = _latin_lexical_match_count_statement(
            workspace_id,
            asset_ids,
            latin_terms,
        )
        initial_candidate_limit = limit * 2
    else:
        query_value = bindparam("lexical_query", value=query)
        lexical_distance = ContentUnit.text_content.op("<->>")(query_value).label(
            "lexical_distance"
        )
        lexical_score = (literal(1.0) - lexical_distance).label("lexical_score")
        candidate_statement = scoped_statement.with_only_columns(
            ContentUnit.id,
            lexical_score,
            maintain_column_froms=True,
        )
        ranked_statement = candidate_statement.order_by(lexical_distance, ContentUnit.id)

        def ranked_statement_factory(candidate_limit: int):
            return ranked_statement.limit(candidate_limit)

        match_count_statement = None
        initial_candidate_limit = limit
    return _load_unique_lexical_candidates(
        db,
        scoped_statement,
        ranked_statement_factory,
        limit,
        match_count_statement=match_count_statement,
        initial_candidate_limit=initial_candidate_limit,
    )


def _latin_lexical_expressions(terms: list[str]):
    text_vector = ContentUnit.search_vector
    text_query = func.to_tsquery(
        "simple",
        bindparam("lexical_ts_query", value=" | ".join(terms)),
    )
    if len(terms) == 1:
        term_coverage = literal(1.0)
    else:
        term_matches = [ContentUnit.text_content.ilike(f"%{term}%") for term in terms]
        term_coverage = sum(
            (case((term_match, 1.0), else_=0.0) for term_match in term_matches),
            start=literal(0.0),
        ) / len(terms)
    lexical_score = (term_coverage + func.ts_rank_cd(text_vector, text_query)).label(
        "lexical_score"
    )
    return text_vector, text_query, lexical_score


def _latin_lexical_ranked_statement(
    scoped_statement: Select[RetrievedRow],
    workspace_id: str,
    asset_ids: list[str] | None,
    terms: list[str],
    *,
    candidate_limit: int,
) -> Select:
    text_vector, text_query, lexical_score = _latin_lexical_expressions(terms)
    candidate_statement = select(
        ContentUnit.id.label("content_unit_id"),
        lexical_score,
    ).where(
        ContentUnit.workspace_id == workspace_id,
        text_vector.op("@@")(text_query),
    )
    if asset_ids is not None:
        candidate_statement = candidate_statement.where(
            ContentUnit.asset_id.in_(asset_ids)
        )
    lexical_candidates = (
        candidate_statement.order_by(desc(lexical_score), ContentUnit.id)
        .limit(candidate_limit)
        .cte("lexical_candidates")
        .prefix_with("MATERIALIZED")
    )
    return (
        scoped_statement.join(
            lexical_candidates,
            lexical_candidates.c.content_unit_id == ContentUnit.id,
        )
        .with_only_columns(
            ContentUnit.id,
            lexical_candidates.c.lexical_score,
            maintain_column_froms=True,
        )
        .order_by(desc(lexical_candidates.c.lexical_score), ContentUnit.id)
    )


def _latin_lexical_match_count_statement(
    workspace_id: str,
    asset_ids: list[str] | None,
    terms: list[str],
) -> Select:
    text_vector, text_query, _lexical_score = _latin_lexical_expressions(terms)
    statement = select(func.count()).select_from(ContentUnit).where(
        ContentUnit.workspace_id == workspace_id,
        text_vector.op("@@")(text_query),
    )
    if asset_ids is not None:
        statement = statement.where(ContentUnit.asset_id.in_(asset_ids))
    return statement


def _load_unique_lexical_candidates(
    db: Session,
    scoped_statement: Select[RetrievedRow],
    ranked_statement_factory: Callable[[int], Select],
    limit: int,
    *,
    match_count_statement: Select | None = None,
    initial_candidate_limit: int | None = None,
) -> list[RetrievedContent]:
    candidate_limit = max(limit, initial_candidate_limit or limit)
    match_count: int | None = None
    while True:
        candidate_rows = db.execute(ranked_statement_factory(candidate_limit)).all()
        unique = _load_lexical_candidates(
            db,
            scoped_statement,
            candidate_rows,
            candidate_limit,
        )
        if len(unique) >= limit:
            return unique[:limit]
        if match_count_statement is None:
            if len(candidate_rows) < candidate_limit:
                return unique[:limit]
            candidate_limit *= 2
            continue
        if match_count is None:
            match_count = int(db.scalar(match_count_statement) or 0)
        if candidate_limit >= match_count:
            return unique[:limit]
        candidate_limit = min(candidate_limit * 2, match_count)


def _load_lexical_candidates(
    db: Session,
    scoped_statement: Select[RetrievedRow],
    candidate_rows: list[tuple[str, float]],
    limit: int,
) -> list[RetrievedContent]:
    if not candidate_rows:
        return []
    ordered_candidates = sorted(candidate_rows, key=lambda row: (-float(row[1]), row[0]))
    candidate_scores = {unit_id: float(score) for unit_id, score in ordered_candidates}
    loaded_rows = db.execute(
        scoped_statement.where(ContentUnit.id.in_(candidate_scores))
    ).all()
    loaded_by_id = {
        item.content_unit.id: item
        for item in _candidates(
            db,
            [
                (
                    unit,
                    asset,
                    locator,
                    representation,
                    _lexical_score_to_distance(candidate_scores[unit.id]),
                )
                for unit, asset, locator, representation in loaded_rows
            ],
        )
    }
    candidates = [
        loaded_by_id[unit_id]
        for unit_id, _score in ordered_candidates
        if unit_id in loaded_by_id
    ]
    return _dedupe_locations(candidates)[:limit]


def retrieve_query_content(
    db: Session,
    workspace_id: str,
    query: str,
    query_embedding: list[float],
    *,
    asset_ids: list[str] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    limit: int = 6,
    strategy: RetrievalStrategy | None = None,
    candidate_limit: int | None = None,
    rrf_constant: int | None = None,
) -> list[RetrievedContent]:
    if limit < 1:
        raise ValueError("limit must be positive")
    effective_strategy = strategy or settings.retrieval_strategy
    started = time.perf_counter()
    try:
        if effective_strategy == "dense":
            results = retrieve_content(
                db,
                workspace_id,
                query_embedding,
                asset_ids=asset_ids,
                embedding_provider=embedding_provider,
                limit=limit,
            )
            total_ms = _elapsed_ms(started)
            _log_retrieval(workspace_id, "dense", limit, len(results), 0, len(results), total_ms)
            observe_retrieval("dense", "success", total_ms, len(results))
            return results

        effective_candidate_limit = max(
            limit,
            candidate_limit if candidate_limit is not None else settings.retrieval_candidate_k,
        )
        effective_rrf_constant = (
            rrf_constant if rrf_constant is not None else settings.retrieval_rrf_constant
        )
        if effective_rrf_constant < 1:
            raise ValueError("rrf_constant must be positive")
        dense_results = retrieve_content(
            db,
            workspace_id,
            query_embedding,
            asset_ids=asset_ids,
            embedding_provider=embedding_provider,
            limit=effective_candidate_limit,
        )
        lexical_results = retrieve_lexical_content(
            db,
            workspace_id,
            query,
            asset_ids=asset_ids,
            limit=effective_candidate_limit,
        )
        results = _rrf_merge(
            dense_results,
            lexical_results,
            limit=limit,
            constant=effective_rrf_constant,
        )
        total_ms = _elapsed_ms(started)
        _log_retrieval(
            workspace_id,
            "hybrid",
            effective_candidate_limit,
            len(dense_results),
            len(lexical_results),
            len(results),
            total_ms,
        )
        observe_retrieval("hybrid", "success", total_ms, len(results))
        return results
    except Exception as error:
        total_ms = _elapsed_ms(started)
        logger.error(
            "retrieval_failed strategy=%s workspace_id=%s error_type=%s total_ms=%.3f",
            effective_strategy,
            workspace_id,
            type(error).__name__,
            total_ms,
        )
        observe_retrieval(effective_strategy, "error", total_ms, 0)
        raise


def _log_retrieval(
    workspace_id: str,
    strategy: str,
    candidate_k: int,
    dense_count: int,
    lexical_count: int,
    result_count: int,
    total_ms: float,
) -> None:
    logger.info(
        "retrieval_complete strategy=%s workspace_id=%s candidate_k=%d dense_count=%d "
        "lexical_count=%d result_count=%d total_ms=%.3f",
        strategy,
        workspace_id,
        candidate_k,
        dense_count,
        lexical_count,
        result_count,
        total_ms,
    )


def _retrieve_sqlite(
    db: Session,
    statement: Select,
    query_embedding: list[float],
    limit: int,
) -> list[RetrievedContent]:
    scored: list[RetrievedContent] = []
    rows = db.execute(
        statement.add_columns(ContentUnitEmbedding.embedding)
    ).all()
    candidate_rows = []
    for unit, asset, locator, representation, embedding in rows:
        vector = embedding
        if not isinstance(vector, list):
            continue
        candidate_rows.append(
            (
                unit,
                asset,
                locator,
                representation,
                _cosine_distance(query_embedding, vector),
            )
        )
    scored.extend(_candidates(db, candidate_rows))
    scored.sort(key=lambda item: (item.distance, item.content_unit.id))
    return _dedupe_locations(scored)[:limit]


def _retrieve_lexical_sqlite(
    db: Session,
    statement: Select[RetrievedRow],
    query: str,
    terms: list[str],
    limit: int,
) -> list[RetrievedContent]:
    query_text = query.casefold()
    scored: list[tuple[float, RetrievedContent]] = []
    candidate_rows = []
    candidate_scores: dict[str, float] = {}
    for unit, asset, locator, representation in db.execute(statement).all():
        content = unit.text_content.casefold()
        matched_terms = sum(term.casefold() in content for term in terms)
        if matched_terms == 0:
            continue
        score = matched_terms / len(terms)
        if query_text in content:
            score += 1.0
        candidate_scores[unit.id] = score
        candidate_rows.append(
            (
                unit,
                asset,
                locator,
                representation,
                _lexical_score_to_distance(score),
            )
        )
    scored.extend(
        (candidate_scores[item.content_unit.id], item)
        for item in _candidates(db, candidate_rows)
    )
    scored.sort(key=lambda item: (-item[0], item[1].content_unit.id))
    return _dedupe_locations([item for _score, item in scored])[:limit]


def _rrf_merge(
    dense_results: list[RetrievedContent],
    lexical_results: list[RetrievedContent],
    *,
    limit: int,
    constant: int,
) -> list[RetrievedContent]:
    scores: dict[tuple[str, str], float] = {}
    items: dict[tuple[str, str], RetrievedContent] = {}
    for rank, item in enumerate(_dedupe_locations(dense_results), start=1):
        key = _location_key(item)
        scores[key] = scores.get(key, 0.0) + 1.0 / (constant + rank)
        items.setdefault(key, item)
    for rank, item in enumerate(_dedupe_locations(lexical_results), start=1):
        key = _location_key(item)
        scores[key] = scores.get(key, 0.0) + 1.0 / (constant + rank)
        items.setdefault(key, item)
    ranked = sorted(scores, key=lambda key: (-scores[key], key[0], key[1]))[:limit]
    return [items[key] for key in ranked]


def _location_key(item: RetrievedContent) -> tuple[str, str]:
    return item.location_key


def _dedupe_locations(items: list[RetrievedContent]) -> list[RetrievedContent]:
    locations: dict[tuple[str, str], RetrievedContent] = {}
    for item in items:
        locations.setdefault(_location_key(item), item)
    return list(locations.values())


def _candidates(
    db: Session,
    rows: list[
        tuple[ContentUnit, Asset, EvidenceLocator, AssetRepresentation, float]
    ],
) -> list[RetrievedContent]:
    keys = evidence_retrieval_keys(
        db,
        (
            EvidenceRetrievalSource(
                locator=locator,
                representation=representation,
                workspace_id=unit.workspace_id,
                asset_id=unit.asset_id,
                processing_generation=asset.current_processing_generation,
                representation_id=unit.representation_id,
            )
            for unit, asset, locator, representation, _distance in rows
        ),
    )
    return [
        RetrievedContent(
            content_unit=unit,
            asset=asset,
            locator=locator,
            channel=TEXT_CHANNEL.kind,
            distance=distance,
            location_key=keys[locator.id],
        )
        for unit, asset, locator, _representation, distance in rows
    ]


def _lexical_terms(query: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()

    def add(term: str) -> None:
        normalized = term.casefold().strip()
        if normalized and normalized not in seen:
            terms.append(normalized)
            seen.add(normalized)

    latin_words = _unique_latin_terms(query)
    for word in latin_words:
        add(word)
    if latin_words:
        return terms
    for run in _CJK_RUN.findall(query):
        if len(run) <= 12:
            add(run)
        for index in range(len(run) - 1):
            add(run[index : index + 2])
    return terms


def _unique_latin_terms(query: str) -> list[str]:
    return list(dict.fromkeys(word.casefold() for word in _LATIN_WORD.findall(query)))


def _lexical_score_to_distance(score: float) -> float:
    return 1.0 - min(1.0, max(0.0, float(score)))


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def _cosine_distance(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        return 1.0
    left_norm = sqrt(sum(value * value for value in left))
    right_norm = sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    similarity = sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
    return 1.0 - similarity


# Evaluation callers use these names; both now return the Asset kernel result shape.
retrieve_chunks = retrieve_content
retrieve_lexical_chunks = retrieve_lexical_content
retrieve_query_chunks = retrieve_query_content
RetrievedChunk = RetrievedContent
