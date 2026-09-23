"""Explicit archived-driver mapping; current runtime must use real relocated modules."""
import ast
from pathlib import Path

from issue25_service_support import RUNTIME, legacy_runtime_source


def test_current_driver_and_archived_driver_have_separate_imports():
    current = RUNTIME.read_text(encoding="utf-8")
    old = legacy_runtime_source(current)
    ast.parse(current)
    ast.parse(old)
    assert "from ai_pdf_worker.research import persistence as composition" in current
    assert "from ai_pdf_worker import research_persistence_service as composition" in old
    assert "from ai_pdf_worker.research.runtime import" in current
    assert "from ai_pdf_worker.research_runtime import" in old
    assert "from citeframe_evaluation.acceptance import fixture" in current
    assert "from ai_pdf_worker import r800_acceptance_fixture as fixture" in old
    assert "ai_pdf_worker.research." not in old
    assert "citeframe_evaluation" not in old


def test_v4_orchestration_and_adapters_use_production_layout():
    from ai_pdf_worker.research import conflict_investigation
    from ai_pdf_worker.research.adapters.generation import LedgeredGeneration
    from ai_pdf_worker.research.adapters.ledger import SqlResearchLedgerAdapter
    from ai_pdf_worker.research.schemas import schemas_for_registry
    from ai_pdf_api.services.research.research_agent_io_registry import require_current_production_registry
    assert callable(conflict_investigation.investigate)
    assert callable(LedgeredGeneration.conflict_turn)
    assert callable(SqlResearchLedgerAdapter.investigation_outcome)
    assert "investigator" in schemas_for_registry(require_current_production_registry())
    package = Path(conflict_investigation.__file__).parents[1]
    assert not (package / "research_runtime_ports.py").exists()
    assert not (package / "research_conflict_investigation.py").exists()
