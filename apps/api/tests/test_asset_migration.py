from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

import pytest
from ai_pdf_api.core.settings import settings
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import IntegrityError, OperationalError

API_ROOT = Path(__file__).resolve().parents[1]
LEGACY_HEAD = "a8c9d0e1f2a3"
IMAGE_ENABLE_PREVIOUS_HEAD = "f2a4c6e8b0d1"


def _migration_config(database_url: str) -> Config:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    settings.database_url = database_url
    return config


def _database_url(base_url: URL, database: str) -> str:
    return base_url.set(database=database).render_as_string(hide_password=False)


def _postgres_cli_options(database_url: str) -> tuple[list[str], dict[str, str]]:
    url = make_url(database_url)
    options: list[str] = []
    if url.host:
        options.extend(("--host", url.host))
    if url.port:
        options.extend(("--port", str(url.port)))
    if url.username:
        options.extend(("--username", url.username))
    if url.database:
        options.extend(("--dbname", url.database))
    environment = os.environ.copy()
    if url.password:
        environment["PGPASSWORD"] = url.password
    return options, environment


def _seed_legacy_contract(database_url: str) -> None:
    statements = (
        """
        INSERT INTO users VALUES (
          '00000000-0000-0000-0000-000000000001', 'migration@example.com',
          'Migration User', 'hash', '', now(), now()
        )
        """,
        """
        INSERT INTO workspaces VALUES (
          '00000000-0000-0000-0000-000000000010', 'Migration Workspace', NULL,
          '00000000-0000-0000-0000-000000000001', NULL, now(), now(),
          'Answer from evidence.', 6, 1200
        )
        """,
        """
        INSERT INTO documents VALUES (
          '00000000-0000-0000-0000-000000000020',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000001',
          'Legacy PDF', 'legacy.pdf', 'legacy/original.pdf', 'application/pdf',
          12345, 1, 'ready', 7, NULL, NULL, NULL, NULL, now(), now()
        )
        """,
        """
        INSERT INTO document_pages VALUES (
          '00000000-0000-0000-0000-000000000021',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000020',
          4, 'Legacy evidence text.', 21, now(),
          '[{"text":"Legacy OCR","x":0.1,"y":0.2,"width":0.3,"height":0.1}]'::json
        )
        """,
        """
        INSERT INTO document_chunks VALUES (
          '00000000-0000-0000-0000-000000000022',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000020',
          '00000000-0000-0000-0000-000000000021',
          0, 'Legacy evidence text.', 4, 0, 21, 7, now(),
          array_fill(0.001::real, ARRAY[1024])::vector, 1024,
          'fixture-provider', 'fixture-model', 'fixture-v1'
        )
        """,
        """
        INSERT INTO ingestion_jobs VALUES (
          '00000000-0000-0000-0000-000000000023',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000020',
          'ingest', 'completed', 1, '{}'::json, NULL, NULL,
          '00000000-0000-0000-0000-000000000001', now(), now(), now(), now()
        )
        """,
        """
        INSERT INTO chat_threads VALUES (
          '00000000-0000-0000-0000-000000000030',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000001',
          'Legacy thread', NULL, now(), now(), now(), NULL
        )
        """,
        """
        INSERT INTO chat_messages VALUES (
          '00000000-0000-0000-0000-000000000031',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000030',
          'user', 'What is the evidence?', 'completed', NULL, NULL, NULL, NULL, NULL, now(), NULL
        ), (
          '00000000-0000-0000-0000-000000000032',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000030',
          'assistant', 'The evidence is cited.', 'completed',
          'fixture', 'fixture-model', 'v1', 10, 10, now(),
          '00000000-0000-0000-0000-000000000031'
        )
        """,
        """
        INSERT INTO message_citations VALUES (
          '00000000-0000-0000-0000-000000000033',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000032', 0,
          '00000000-0000-0000-0000-000000000020',
          '00000000-0000-0000-0000-000000000022',
          4, 'Legacy PDF', 'Legacy evidence text.', 7, now()
        )
        """,
        """
        INSERT INTO notes VALUES (
          '00000000-0000-0000-0000-000000000040',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000001',
          '00000000-0000-0000-0000-000000000001',
          'Saved evidence', 'Legacy evidence text.', false, NULL, now(), now()
        )
        """,
        """
        INSERT INTO note_sources VALUES (
          '00000000-0000-0000-0000-000000000041',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000040', 0,
          '00000000-0000-0000-0000-000000000033',
          '00000000-0000-0000-0000-000000000020',
          4, 'Legacy PDF', 'Legacy evidence text.', now()
        )
        """,
        """
        INSERT INTO tags VALUES (
          '00000000-0000-0000-0000-000000000050',
          '00000000-0000-0000-0000-000000000010',
          'Important', 'important', '#ff0000',
          '00000000-0000-0000-0000-000000000001', now()
        )
        """,
        """
        INSERT INTO document_tags VALUES (
          '00000000-0000-0000-0000-000000000051',
          '00000000-0000-0000-0000-000000000010',
          '00000000-0000-0000-0000-000000000020',
          '00000000-0000-0000-0000-000000000050', now()
        )
        """,
    )
    with create_engine(database_url).begin() as connection:
        for statement in statements:
            connection.exec_driver_sql(statement)


def _assert_migrated_contract(database_url: str) -> None:
    with create_engine(database_url).begin() as connection:
        asset_types = connection.execute(
            text("SELECT kind, contract_version, enabled FROM asset_types ORDER BY kind")
        ).all()
        assert asset_types == [
            ("audio", 1, True),
            ("document", 1, True),
            ("docx", 1, True),
            ("html", 1, True),
            ("image", 1, True),
            ("pdf", 1, True),
            ("pptx", 1, True),
            ("video", 1, True),
            ("xlsx", 1, True),
        ]

        asset = connection.execute(
            text(
                "SELECT asset_kind, title, current_processing_generation, current_index_version "
                "FROM assets"
            )
        ).one()
        assert asset == ("pdf", "Legacy PDF", 1, 7)

        content = connection.execute(
            text(
                """
                SELECT cu.unit_kind, cu.unit_order, cu.text_content, cu.char_start, cu.char_end,
                       cu.index_version, l.locator_kind, p.page_number
                FROM content_units cu
                JOIN evidence_locators l ON l.id = cu.source_locator_id
                JOIN pdf_locator_details p ON p.locator_id = l.id
                """
            )
        ).one()
        assert content == ("pdf_text_chunk", 0, "Legacy evidence text.", 0, 21, 7, "pdf_page", 4)

        embedding = connection.execute(
            text(
                "SELECT asset_id, processing_generation, index_version, is_current, "
                "embedding_space, provider, model, dimensions, version, "
                "vector_dims(embedding) FROM content_unit_embeddings"
            )
        ).one()
        assert embedding == (
            "00000000-0000-0000-0000-000000000020",
            1,
            7,
            True,
            "text",
            "fixture-provider",
            "fixture-model",
            1024,
            "fixture-v1",
            1024,
        )
        trigger_names = set(
            connection.scalars(
                text(
                    "SELECT tgname FROM pg_trigger "
                    "WHERE tgrelid='content_unit_embeddings'::regclass AND NOT tgisinternal"
                )
            )
        )
        assert trigger_names == {
            "trg_content_unit_embeddings_scope_insert",
            "trg_content_unit_embeddings_scope_update",
        }
        with pytest.raises(IntegrityError, match="projection does not match"), connection.begin_nested():
            connection.execute(
                text(
                    "UPDATE content_unit_embeddings "
                    "SET processing_generation = 99 WHERE is_current IS TRUE"
                )
            )
        with connection.begin_nested() as inactive_scope:
            connection.execute(
                text(
                    "UPDATE content_unit_embeddings "
                    "SET is_current = false, processing_generation = 99"
                )
            )
            assert connection.execute(
                text(
                    "SELECT is_current, processing_generation "
                    "FROM content_unit_embeddings"
                )
            ).one() == (False, 99)
            inactive_scope.rollback()

        citation = connection.execute(
            text(
                """
                SELECT c.asset_kind_snapshot, c.asset_title_snapshot, c.excerpt_snapshot,
                       c.index_version_snapshot, l.locator_kind, p.page_number
                FROM message_citations c
                JOIN evidence_locators l ON l.id = c.evidence_locator_id
                JOIN pdf_locator_details p ON p.locator_id = l.id
                """
            )
        ).one()
        note_source = connection.execute(
            text(
                """
                SELECT ns.asset_kind_snapshot, ns.asset_title_snapshot, ns.excerpt_snapshot,
                       ns.index_version_snapshot, l.locator_kind, p.page_number
                FROM note_sources ns
                JOIN evidence_locators l ON l.id = ns.evidence_locator_id
                JOIN pdf_locator_details p ON p.locator_id = l.id
                """
            )
        ).one()
        expected_snapshot = ("pdf", "Legacy PDF", "Legacy evidence text.", 7, "pdf_page", 4)
        assert citation == expected_snapshot
        assert note_source == expected_snapshot

        citation_locator_id = connection.scalar(
            text("SELECT evidence_locator_id FROM message_citations")
        )
        connection.execute(
            text(
                """
                UPDATE evidence_locators SET locator_kind = 'pdf_region'
                WHERE id = :locator_id
                """
            ),
            {"locator_id": citation_locator_id},
        )
        connection.execute(
            text(
                """
                UPDATE pdf_locator_details SET
                    coordinate_space = 'pdf_crop_box_normalized_top_left_v1',
                    crop_x0_points = 0, crop_y0_points = 0,
                    crop_x1_points = 612, crop_y1_points = 792,
                    rotation_degrees = 0,
                    display_width_points = 612, display_height_points = 792
                WHERE locator_id = :locator_id
                """
            ),
            {"locator_id": citation_locator_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO spatial_locator_regions(
                    id, locator_id, region_order, x, y, width, height
                ) VALUES (
                    '00000000-0000-0000-0000-000000000060',
                    :locator_id, 0, 0.1, 0.2, 0.3, 0.1
                )
                """
            ),
            {"locator_id": citation_locator_id},
        )

        ocr_blocks = connection.scalar(text("SELECT legacy_ocr_blocks FROM pdf_pages"))
        assert ocr_blocks == [
            {"text": "Legacy OCR", "x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}
        ]
        assert connection.scalar(text("SELECT asset_id FROM ingestion_jobs")) == (
            "00000000-0000-0000-0000-000000000020"
        )
        assert connection.scalar(text("SELECT asset_id FROM asset_tags")) == (
            "00000000-0000-0000-0000-000000000020"
        )
        legacy_tables = connection.execute(
            text(
                "SELECT to_regclass('documents'), to_regclass('document_pages'), "
                "to_regclass('document_chunks'), to_regclass('document_tags')"
            )
        ).one()
        assert legacy_tables == (None, None, None, None)
        assert connection.scalar(text("SELECT count(*) FROM message_input_evidence")) == 0
        constraints = set(
            connection.scalars(
                text(
                    """
                    SELECT conname
                    FROM pg_constraint
                    WHERE conname IN (
                        'uq_message_input_evidence_order',
                        'uq_message_input_evidence_locator',
                        'ck_message_input_evidence_target_order',
                        'uq_note_sources_note_order',
                        'ck_note_sources_source_order'
                    )
                    """
                )
            )
        )
        assert constraints == {
            "uq_message_input_evidence_order",
            "uq_message_input_evidence_locator",
            "ck_message_input_evidence_target_order",
            "uq_note_sources_note_order",
            "ck_note_sources_source_order",
        }


def _payload_snapshot(database_url: str) -> dict[str, list[dict[str, object]]]:
    queries = {
        "assets": """
            SELECT id, workspace_id, asset_kind, title, source_filename, object_key,
                   mime_type, byte_size, source_sha256, status,
                   current_processing_generation, current_index_version,
                   latest_ingestion_job_id, last_error_code, last_error_message,
                   deleted_at, created_at, updated_at
            FROM assets ORDER BY id
        """,
        "representations": """
            SELECT id, workspace_id, asset_id, representation_kind,
                   processing_generation, generator_provider, generator_model,
                   generator_version, object_key, content_sha256, created_at
            FROM asset_representations ORDER BY id
        """,
        "pdf_pages": """
            SELECT id, workspace_id, asset_id, representation_id, page_number,
                   media_x0_points, media_y0_points, media_x1_points, media_y1_points,
                   crop_x0_points, crop_y0_points, crop_x1_points, crop_y1_points,
                   rotation_degrees, display_width_points, display_height_points,
                   extracted_text, char_count, legacy_ocr_blocks, created_at
            FROM pdf_pages ORDER BY id
        """,
        "content_units": """
            SELECT id, workspace_id, asset_id, representation_id, source_locator_id,
                   unit_kind, unit_order, text_content, token_count, char_start,
                   char_end, index_version, created_at
            FROM content_units ORDER BY id
        """,
        "embeddings": """
            SELECT id, workspace_id, asset_id, content_unit_id, processing_generation,
                   index_version, is_current, embedding_space, provider, model,
                   dimensions, version, embedding::text AS embedding, created_at
            FROM content_unit_embeddings ORDER BY id
        """,
        "locators": """
            SELECT l.id, l.workspace_id, l.asset_id, l.locator_kind,
                   l.locator_version, l.processing_generation_snapshot,
                   l.representation_id_snapshot, p.page_id, p.page_number,
                   p.coordinate_space, p.crop_x0_points, p.crop_y0_points,
                   p.crop_x1_points, p.crop_y1_points, p.rotation_degrees,
                   p.display_width_points, p.display_height_points, l.created_at
            FROM evidence_locators l
            LEFT JOIN pdf_locator_details p ON p.locator_id = l.id
            ORDER BY l.id
        """,
        "spatial_regions": """
            SELECT id, locator_id, region_order, x, y, width, height
            FROM spatial_locator_regions ORDER BY locator_id, region_order, id
        """,
        "citations": """
            SELECT id, workspace_id, message_id, citation_index,
                   evidence_locator_id, asset_id, asset_kind_snapshot,
                   asset_title_snapshot, excerpt_snapshot,
                   processing_generation_snapshot, representation_id_snapshot,
                   parser_version_snapshot, index_version_snapshot, created_at
            FROM message_citations ORDER BY id
        """,
        "message_input_evidence": """
            SELECT id, workspace_id, message_id, target_order,
                   evidence_locator_id, asset_id, asset_kind_snapshot,
                   asset_title_snapshot, excerpt_snapshot,
                   processing_generation_snapshot, representation_id_snapshot,
                   parser_version_snapshot, index_version_snapshot, created_at
            FROM message_input_evidence ORDER BY id
        """,
        "note_sources": """
            SELECT id, workspace_id, note_id, source_order, message_citation_id,
                   evidence_locator_id, asset_id, asset_kind_snapshot,
                   asset_title_snapshot, excerpt_snapshot,
                   processing_generation_snapshot, representation_id_snapshot,
                   parser_version_snapshot, index_version_snapshot, created_at
            FROM note_sources ORDER BY id
        """,
        "asset_tags": """
            SELECT id, workspace_id, asset_id, tag_id, created_at
            FROM asset_tags ORDER BY id
        """,
        "ingestion_jobs": """
            SELECT id, workspace_id, asset_id, job_type, status, attempt_count,
                   config_snapshot, error_code, error_message, requested_by_user_id,
                   queued_at, started_at, finished_at, created_at
            FROM ingestion_jobs ORDER BY id
        """,
    }
    with create_engine(database_url).connect() as connection:
        return {
            name: [dict(row) for row in connection.execute(text(query)).mappings()]
            for name, query in queries.items()
        }


def _dump_and_restore(source_url: str, restored_url: str) -> None:
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        pytest.skip("Dump/restore oracle requires pg_dump and pg_restore")

    with TemporaryDirectory(prefix="ai-pdf-asset-migration-") as directory:
        archive = Path(directory) / "asset-migration.dump"
        source_options, source_environment = _postgres_cli_options(source_url)
        restored_options, restored_environment = _postgres_cli_options(restored_url)
        subprocess.run(
            [
                pg_dump,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(archive),
                *source_options,
            ],
            check=True,
            capture_output=True,
            text=True,
            env=source_environment,
        )
        subprocess.run(
            [
                pg_restore,
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                *restored_options,
                str(archive),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=restored_environment,
        )


def test_image_enable_migration_round_trip() -> None:
    base_url = make_url(settings.database_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.skip("Image enable migration oracle requires PostgreSQL")

    admin_url = _database_url(base_url, "postgres")
    database_name = f"ai_pdf_image_enable_{uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except OperationalError:
        admin_engine.dispose()
        pytest.skip("Image enable migration oracle requires a reachable PostgreSQL server")

    original_url = settings.database_url
    database_url = _database_url(base_url, database_name)
    try:
        config = _migration_config(database_url)
        command.upgrade(config, IMAGE_ENABLE_PREVIOUS_HEAD)
        with create_engine(database_url).connect() as connection:
            assert connection.scalar(text("SELECT enabled FROM asset_types WHERE kind='image'")) is False
        command.upgrade(config, "head")
        with create_engine(database_url).connect() as connection:
            assert connection.scalar(text("SELECT enabled FROM asset_types WHERE kind='image'")) is True
        command.downgrade(config, IMAGE_ENABLE_PREVIOUS_HEAD)
        with create_engine(database_url).connect() as connection:
            assert connection.scalar(text("SELECT enabled FROM asset_types WHERE kind='image'")) is False
    finally:
        settings.database_url = original_url
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname = :name"
                ),
                {"name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def test_postgres_asset_migration_preserves_legacy_evidence_contract() -> None:
    base_url = make_url(settings.database_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.skip("Asset migration oracle requires PostgreSQL")

    admin_url = _database_url(base_url, "postgres")
    source_database = f"ai_pdf_asset_migration_{uuid4().hex}"
    restored_database = f"ai_pdf_asset_restore_{uuid4().hex}"
    database_names = (source_database, restored_database)
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        admin_engine.dispose()
        pytest.skip("Asset migration oracle requires a reachable PostgreSQL server")

    original_url = settings.database_url
    source_url = _database_url(base_url, source_database)
    restored_url = _database_url(base_url, restored_database)
    try:
        with admin_engine.connect() as connection:
            for database_name in database_names:
                connection.execute(text(f'CREATE DATABASE "{database_name}"'))
        config = _migration_config(source_url)
        command.upgrade(config, LEGACY_HEAD)
        _seed_legacy_contract(source_url)
        command.upgrade(config, "head")
        _assert_migrated_contract(source_url)
        source_snapshot = _payload_snapshot(source_url)
        _dump_and_restore(source_url, restored_url)
        assert _payload_snapshot(restored_url) == source_snapshot
        with pytest.raises(RuntimeError, match="irreversible"):
            command.downgrade(config, LEGACY_HEAD)
    finally:
        settings.database_url = original_url
        with admin_engine.connect() as connection:
            for database_name in database_names:
                connection.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity WHERE datname = :name"
                    ),
                    {"name": database_name},
                )
                connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()


def test_embedding_scope_migration_rejects_cross_workspace_backfill() -> None:
    base_url = make_url(settings.database_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.skip("Embedding scope migration oracle requires PostgreSQL")

    admin_url = _database_url(base_url, "postgres")
    database_name = f"ai_pdf_embedding_scope_{uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except OperationalError:
        admin_engine.dispose()
        pytest.skip("Embedding scope migration oracle requires a reachable PostgreSQL server")

    original_url = settings.database_url
    database_url = _database_url(base_url, database_name)
    try:
        config = _migration_config(database_url)
        command.upgrade(config, LEGACY_HEAD)
        _seed_legacy_contract(database_url)
        command.upgrade(config, "e1f3a5c7d9b2")
        with create_engine(database_url).begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO workspaces(
                      id,name,created_by_user_id,created_at,updated_at,
                      system_prompt,retrieval_top_k,chunk_size
                    ) VALUES (
                      '00000000-0000-0000-0000-000000000099','Corrupt Workspace',
                      '00000000-0000-0000-0000-000000000001',now(),now(),
                      'Evidence only.',6,1200
                    )
                    """
                )
            )
            connection.execute(
                text(
                    """
                    UPDATE content_unit_embeddings
                    SET workspace_id='00000000-0000-0000-0000-000000000099'
                    """
                )
            )

        with pytest.raises(RuntimeError, match="backfill found invalid"):
            command.upgrade(config, "head")
        with create_engine(database_url).connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                "e1f3a5c7d9b2"
            )
    finally:
        settings.database_url = original_url
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname = :name"
                ),
                {"name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()



def test_document_modality_migration_round_trip() -> None:
    base_url = make_url(settings.database_url)
    if not base_url.drivername.startswith("postgresql"):
        pytest.skip("Document modality migration oracle requires PostgreSQL")

    admin_url = _database_url(base_url, "postgres")
    database_name = f"ai_pdf_document_enable_{uuid4().hex}"
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            connection.execute(text(f'CREATE DATABASE "{database_name}"'))
    except OperationalError:
        admin_engine.dispose()
        pytest.skip("Document modality migration oracle requires a reachable PostgreSQL server")

    original_url = settings.database_url
    database_url = _database_url(base_url, database_name)
    try:
        config = _migration_config(database_url)
        command.upgrade(config, "e8f1a2b3c4d5")
        with create_engine(database_url).connect() as connection:
            assert connection.scalar(
                text("SELECT COUNT(*) FROM asset_types WHERE kind='document'")
            ) == 0
        command.upgrade(config, "head")
        with create_engine(database_url).connect() as connection:
            assert connection.execute(
                text(
                    "SELECT kind, contract_version, enabled FROM asset_types "
                    "WHERE kind='document'"
                )
            ).one() == ("document", 1, True)
            assert connection.execute(
                text(
                    "SELECT kind, detail_family FROM locator_types "
                    "WHERE kind='document_anchor'"
                )
            ).one() == ("document_anchor", "record")
            assert connection.scalar(
                text("SELECT to_regclass('document_locator_details')")
            ) is not None
            assert connection.scalar(
                text("SELECT to_regclass('document_normalized_contents')")
            ) is not None
            assert connection.scalar(
                text("SELECT to_regclass('document_blocks')")
            ) is not None
            # representation ownership only; no independently writable workspace/asset columns
            columns = {
                row[0]
                for row in connection.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'document_blocks'"
                    )
                )
            }
            assert "workspace_id" not in columns
            assert "asset_id" not in columns
            assert "heading_level" in columns
        # Empty-data downgrade remains reversible.
        command.downgrade(config, "e8f1a2b3c4d5")
        with create_engine(database_url).connect() as connection:
            assert connection.scalar(
                text("SELECT COUNT(*) FROM asset_types WHERE kind='document'")
            ) == 0
            assert connection.scalar(
                text("SELECT to_regclass('document_locator_details')")
            ) is None
        # Re-upgrade and refuse populated document modality downgrade.
        command.upgrade(config, "head")
        with create_engine(database_url).begin() as connection:
            user_id = str(uuid4())
            workspace_id = str(uuid4())
            asset_id = str(uuid4())
            connection.execute(
                text(
                    "INSERT INTO users(id, email, name, password_hash, avatar_url, created_at, updated_at) "
                    "VALUES (:id, :email, 'Doc', 'x', 'https://example.com/a.png', NOW(), NOW())"
                ),
                {"id": user_id, "email": f"{user_id}@example.com"},
            )
            connection.execute(
                text(
                    "INSERT INTO workspaces("
                    "id, name, created_by_user_id, created_at, updated_at, "
                    "system_prompt, retrieval_top_k, chunk_size"
                    ") VALUES ("
                    ":id, 'Doc WS', :user_id, NOW(), NOW(), "
                    "'Evidence only.', 6, 1200"
                    ")"
                ),
                {"id": workspace_id, "user_id": user_id},
            )
            connection.execute(
                text(
                    "INSERT INTO assets("
                    "id, workspace_id, created_by_user_id, asset_kind, title, source_filename, "
                    "object_key, mime_type, byte_size, status, current_processing_generation, "
                    "current_index_version, created_at, updated_at"
                    ") VALUES ("
                    ":id, :workspace_id, :user_id, 'document', 'Note', 'note.md', "
                    "'obj', 'text/markdown', 12, 'ready', 1, 1, NOW(), NOW()"
                    ")"
                ),
                {
                    "id": asset_id,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
            )
        with pytest.raises(Exception, match="irreversible document modality downgrade"):
            command.downgrade(config, "e8f1a2b3c4d5")
    finally:
        settings.database_url = original_url
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity WHERE datname = :name"
                ),
                {"name": database_name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{database_name}"'))
        admin_engine.dispose()
