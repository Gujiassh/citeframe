"""Public production Research runtime ports."""

from ai_pdf_worker.research.agents import GenerationResearchAgents
from ai_pdf_worker.research.core import (
    ResearchPortError,
    ResearchWorkerService,
    VerificationRecord,
    as_approved_execution,
)
from ai_pdf_worker.research.adapters.generation import LedgeredGeneration
from ai_pdf_worker.research.adapters.evidence import SqlEvidenceToolPort
from ai_pdf_worker.research.adapters.ledger import SqlResearchLedgerAdapter
from ai_pdf_worker.research.processor import (
    ClaimedResearchWork,
    ResearchWorkProcessor,
    build_default_research_service,
)

__all__ = [
    "ClaimedResearchWork",
    "GenerationResearchAgents",
    "LedgeredGeneration",
    "ResearchPortError",
    "ResearchWorkProcessor",
    "ResearchWorkerService",
    "SqlEvidenceToolPort",
    "SqlResearchLedgerAdapter",
    "VerificationRecord",
    "as_approved_execution",
    "build_default_research_service",
]
