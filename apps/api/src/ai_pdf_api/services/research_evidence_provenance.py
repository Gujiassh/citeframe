"""Shim: alias of ai_pdf_api.services.research.research_evidence_provenance."""
from __future__ import annotations

import sys

from ai_pdf_api.services.research import research_evidence_provenance as _impl

# Make `import ai_pdf_api.services.research_evidence_provenance` resolve to the package submodule object.
sys.modules[__name__] = _impl
