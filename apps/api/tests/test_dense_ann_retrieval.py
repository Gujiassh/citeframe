from types import SimpleNamespace

import pytest
from sqlalchemy.dialects import postgresql

from ai_pdf_api.services import retrieval


class _RankedStatement:
    def __init__(self, ann_limit: int) -> None:
        self.ann_limit = ann_limit
        self.ranked_limit: int | None = None

    def limit(self, ranked_limit: int) -> "_RankedStatement":
        self.ranked_limit = ranked_limit
        return self


class _DenseSession:
    def __init__(
        self, rows_by_ann_limit: dict[int, list[tuple]], embedding_count: int
    ) -> None:
        self.rows_by_ann_limit = rows_by_ann_limit
        self.embedding_count = embedding_count
        self.executions: list[tuple[int, int | None]] = []
        self.count_queries = 0

    def execute(self, statement: _RankedStatement):
        self.executions.append((statement.ann_limit, statement.ranked_limit))
        return SimpleNamespace(all=lambda: self.rows_by_ann_limit[statement.ann_limit])

    def scalar(self, _statement) -> int:
        self.count_queries += 1
        return self.embedding_count


class _LexicalSession:
    def __init__(self, rows_by_limit: dict[int, list[tuple]], match_count: int) -> None:
        self.rows_by_limit = rows_by_limit
        self.match_count = match_count
        self.executions: list[int] = []
        self.count_queries = 0

    def execute(self, candidate_limit: int):
        self.executions.append(candidate_limit)
        return SimpleNamespace(all=lambda: self.rows_by_limit[candidate_limit])

    def scalar(self, _statement) -> int:
        self.count_queries += 1
        return self.match_count


def test_dense_ann_statement_is_materialized_ann_first_and_fail_closed() -> None:
    workspace_id = "00000000-0000-0000-0000-000000000001"
    asset_id = "00000000-0000-0000-0000-000000000002"
    statement = retrieval._dense_ann_ranked_statement(
        retrieval.retrieval_scope_statement(
            workspace_id,
            [asset_id],
            retrieval.TEXT_CHANNEL,
        ),
        workspace_id,
        [asset_id],
        [1.0, 0.0],
        "provider-a",
        "model-a",
        "version-a",
        1024,
        ann_limit=48,
    ).limit(6)
    sql = " ".join(
        str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    )
    cosine_sql, binary_separator, remaining_sql = sql.partition(
        "), binary_ann_candidates AS MATERIALIZED "
    )
    binary_sql, ensemble_separator, remaining_sql = remaining_sql.partition(
        "), ann_candidates AS MATERIALIZED "
    )
    ensemble_sql, outer_separator, outer_sql = remaining_sql.partition(") SELECT ")

    assert binary_separator
    assert ensemble_separator
    assert outer_separator
    assert cosine_sql.startswith(
        "WITH cosine_ann_candidates AS MATERIALIZED "
        "(SELECT content_unit_embeddings.id AS embedding_id, "
        "content_unit_embeddings.content_unit_id AS content_unit_id, "
        "content_unit_embeddings.asset_id AS asset_id, "
        "content_unit_embeddings.processing_generation AS processing_generation, "
        "content_unit_embeddings.index_version AS index_version, "
        "content_unit_embeddings.embedding <=> '[1.0,0.0]' AS distance "
        "FROM content_unit_embeddings"
    )
    for candidate_sql in (cosine_sql, binary_sql):
        assert " JOIN " not in candidate_sql
        assert "content_units" not in candidate_sql
        assert "assets" not in candidate_sql
        assert "asset_representations" not in candidate_sql
        assert "evidence_locators" not in candidate_sql
        assert f"content_unit_embeddings.workspace_id = '{workspace_id}'" in candidate_sql
        assert "content_unit_embeddings.is_current IS true" in candidate_sql
        assert f"content_unit_embeddings.asset_id IN ('{asset_id}')" in candidate_sql
        assert "content_unit_embeddings.embedding_space = 'text'" in candidate_sql
        assert "content_unit_embeddings.provider = 'provider-a'" in candidate_sql
        assert "content_unit_embeddings.model = 'model-a'" in candidate_sql
        assert "content_unit_embeddings.version = 'version-a'" in candidate_sql
        assert "content_unit_embeddings.dimensions = 1024" in candidate_sql

    assert "ORDER BY distance, content_unit_embeddings.id LIMIT 48" in cosine_sql
    assert (
        "ORDER BY CAST(binary_quantize(content_unit_embeddings.embedding) AS BIT(1024)) "
        "<~> binary_quantize(CAST('[1.0,0.0]' AS VECTOR(1024))), "
        "content_unit_embeddings.id LIMIT 144"
        in binary_sql
    )
    assert "cosine_ann_candidates.embedding_id AS embedding_id" in ensemble_sql
    assert "UNION SELECT binary_ann_candidates.embedding_id AS embedding_id" in ensemble_sql
    assert "binary_distance" not in ensemble_sql

    assert (
        "JOIN ann_candidates ON ann_candidates.content_unit_id = content_units.id "
        "AND ann_candidates.asset_id = content_units.asset_id"
        in outer_sql
    )
    assert (
        "ann_candidates.processing_generation = "
        "evidence_locators.processing_generation_snapshot" in outer_sql
    )
    assert (
        "ann_candidates.processing_generation = assets.current_processing_generation"
        in outer_sql
    )
    assert "ann_candidates.index_version = content_units.index_version" in outer_sql
    assert "ann_candidates.index_version = assets.current_index_version" in outer_sql
    assert f"content_units.workspace_id = '{workspace_id}'" in outer_sql
    assert f"assets.workspace_id = '{workspace_id}'" in outer_sql
    assert "content_units.index_version = assets.current_index_version" in outer_sql
    assert (
        "asset_representations.processing_generation = assets.current_processing_generation"
        in outer_sql
    )
    assert (
        "evidence_locators.processing_generation_snapshot = "
        "assets.current_processing_generation" in outer_sql
    )
    assert "assets.status = 'ready'" in outer_sql
    assert "assets.deleted_at IS NULL" in outer_sql
    assert (
        "assets.asset_kind = 'image' AND content_units.unit_kind = 'image_caption'"
        in outer_sql
    )
    assert f"content_units.asset_id IN ('{asset_id}')" in outer_sql
    assert outer_sql.endswith(
        "ORDER BY ann_candidates.distance, content_units.id LIMIT 6"
    )
    assert "binary_quantize" not in outer_sql


def test_latin_lexical_statement_is_materialized_content_unit_first() -> None:
    workspace_id = "00000000-0000-0000-0000-000000000001"
    asset_id = "00000000-0000-0000-0000-000000000002"
    statement = retrieval._latin_lexical_ranked_statement(
        retrieval.retrieval_scope_statement(
            workspace_id,
            [asset_id],
            retrieval.TEXT_CHANNEL,
        ),
        workspace_id,
        [asset_id],
        ["rare", "token"],
        candidate_limit=48,
    ).limit(6)
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())
    parameters = compiled.params
    cte_sql, separator, outer_sql = sql.partition(") SELECT ")

    assert separator
    assert cte_sql.startswith(
        "WITH lexical_candidates AS MATERIALIZED "
        "(SELECT content_units.id AS content_unit_id"
    )
    assert " JOIN " not in cte_sql
    assert "assets" not in cte_sql
    assert "asset_representations" not in cte_sql
    assert "evidence_locators" not in cte_sql
    assert "content_units.workspace_id = %(workspace_id_1)s" in cte_sql
    assert "content_units.asset_id IN (__[POSTCOMPILE_asset_id_1])" in cte_sql
    assert "content_units.search_vector @@" in cte_sql
    assert "to_tsvector" not in cte_sql
    assert "ORDER BY lexical_score DESC, content_units.id LIMIT %(param_7)s" in cte_sql
    assert parameters["workspace_id_1"] == workspace_id
    assert parameters["asset_id_1"] == [asset_id]
    assert parameters["lexical_ts_query"] == "rare | token"
    assert parameters["param_7"] == 48

    assert (
        "JOIN lexical_candidates ON "
        "lexical_candidates.content_unit_id = content_units.id" in outer_sql
    )
    assert "content_units.index_version = assets.current_index_version" in outer_sql
    assert (
        "evidence_locators.processing_generation_snapshot = "
        "assets.current_processing_generation" in outer_sql
    )
    assert "content_units.asset_id IN (__[POSTCOMPILE_asset_id_2])" in outer_sql
    assert parameters["asset_id_2"] == [asset_id]


def test_single_term_latin_score_avoids_redundant_text_scan() -> None:
    statement = retrieval._latin_lexical_ranked_statement(
        retrieval.retrieval_scope_statement(
            "00000000-0000-0000-0000-000000000001",
            None,
            retrieval.TEXT_CHANNEL,
        ),
        "00000000-0000-0000-0000-000000000001",
        None,
        ["raretokenalpha"],
        candidate_limit=20,
    )
    compiled = statement.compile(dialect=postgresql.dialect())
    cte_sql = " ".join(str(compiled).split()).partition(") SELECT ")[0]

    assert "ILIKE" not in cte_sql
    assert compiled.params["param_1"] == 1.0
    assert compiled.params["lexical_ts_query"] == "raretokenalpha"


def test_latin_lexical_window_expands_past_filtered_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _LexicalSession(
        rows_by_limit={
            2: [("eligible-a", 1.0)],
            4: [("eligible-a", 1.0), ("eligible-b", 0.9)],
        },
        match_count=4,
    )
    monkeypatch.setattr(
        retrieval,
        "_load_lexical_candidates",
        lambda _db, _scope, rows, _limit: [row[0] for row in rows],
    )

    result = retrieval._load_unique_lexical_candidates(
        db,
        object(),
        lambda candidate_limit: candidate_limit,
        2,
        match_count_statement=object(),
    )

    assert result == ["eligible-a", "eligible-b"]
    assert db.executions == [2, 4]
    assert db.count_queries == 1


def test_latin_lexical_window_stops_at_source_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _LexicalSession(
        rows_by_limit={
            2: [("eligible-a", 1.0)],
            3: [("eligible-a", 1.0)],
        },
        match_count=3,
    )
    monkeypatch.setattr(
        retrieval,
        "_load_lexical_candidates",
        lambda _db, _scope, rows, _limit: [row[0] for row in rows],
    )

    result = retrieval._load_unique_lexical_candidates(
        db,
        object(),
        lambda candidate_limit: candidate_limit,
        2,
        match_count_statement=object(),
    )

    assert result == ["eligible-a"]
    assert db.executions == [2, 3]
    assert db.count_queries == 1


def test_dense_ann_window_expands_independently_after_post_filter_shortage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        2: [("eligible-a",)],
        4: [("eligible-a",)],
        8: [("eligible-a",), ("eligible-b",)],
    }
    db = _DenseSession(rows, embedding_count=8)

    def build_statement(*_args, ann_limit: int, **_kwargs) -> _RankedStatement:
        return _RankedStatement(ann_limit)

    monkeypatch.setattr(retrieval, "_dense_ann_ranked_statement", build_statement)

    result = retrieval._load_dense_ranked_rows(
        db,
        object(),
        "workspace",
        None,
        [1.0],
        "provider",
        "model",
        "version",
        1024,
        2,
    )

    assert result == rows[8]
    assert db.executions == [(2, 2), (4, 2), (8, 2)]
    assert db.count_queries == 1


def test_dense_ann_window_stops_at_matching_embedding_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = {
        3: [("eligible-a",)],
        5: [("eligible-a",), ("eligible-b",)],
    }
    db = _DenseSession(rows, embedding_count=5)

    def build_statement(*_args, ann_limit: int, **_kwargs) -> _RankedStatement:
        return _RankedStatement(ann_limit)

    monkeypatch.setattr(retrieval, "_dense_ann_ranked_statement", build_statement)

    result = retrieval._load_dense_ranked_rows(
        db,
        object(),
        "workspace",
        None,
        [1.0],
        "provider",
        "model",
        "version",
        1024,
        3,
    )

    assert result == rows[5]
    assert db.executions == [(3, 3), (5, 3)]
    assert db.count_queries == 1


def test_dense_replenishes_duplicate_locations_with_a_larger_ranked_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_rows = [
        ("unit-a", "asset", "locator-a", "representation", 0.1),
        ("unit-a-duplicate", "asset", "locator-a-duplicate", "representation", 0.2),
        ("unit-b", "asset", "locator-b", "representation", 0.3),
    ]
    expanded_rows = [
        ("unit-new", "asset", "locator-new", "representation", 0.05),
        ("unit-b", "asset", "locator-b", "representation", 0.1),
        ("unit-c", "asset", "locator-c", "representation", 0.4),
        ("unit-d", "asset", "locator-d", "representation", 0.5),
    ]
    ranked_limits: list[int] = []

    def load_rows(*_args, **_kwargs):
        ranked_limit = _args[-1]
        ranked_limits.append(ranked_limit)
        return first_rows if ranked_limit == 3 else expanded_rows

    location_keys = {
        "unit-a": ("pdf", "page-1"),
        "unit-a-duplicate": ("pdf", "page-1"),
        "unit-b": ("image", "region-1"),
        "unit-new": ("pdf", "page-2"),
        "unit-c": ("image", "region-2"),
        "unit-d": ("image", "region-3"),
    }

    def build_candidates(_db, rows):
        return [
            retrieval.RetrievedContent(
                content_unit=SimpleNamespace(id=unit_id),
                asset=SimpleNamespace(id="asset"),
                locator=SimpleNamespace(id=locator_id),
                channel="text",
                distance=distance,
                location_key=location_keys[unit_id],
            )
            for unit_id, _asset, locator_id, _representation, distance in rows
        ]

    monkeypatch.setattr(retrieval, "_load_dense_ranked_rows", load_rows)
    monkeypatch.setattr(retrieval, "_candidates", build_candidates)
    db = SimpleNamespace(
        bind=SimpleNamespace(dialect=SimpleNamespace(name="postgresql")),
        # Unit test has no SQL contract rows; A004 gate treats None as empty scope.
        scalar=lambda *_args, **_kwargs: None,
    )

    result = retrieval.retrieve_content(
        db,
        "workspace",
        [1.0],
        embedding_provider=SimpleNamespace(
            provider="provider",
            model="model",
            version="version",
            dimensions=1024,
        ),
        limit=3,
    )

    assert ranked_limits == [3, 6]
    assert [item.content_unit.id for item in result] == ["unit-new", "unit-b", "unit-c"]
    assert len({item.location_key for item in result}) == 3
