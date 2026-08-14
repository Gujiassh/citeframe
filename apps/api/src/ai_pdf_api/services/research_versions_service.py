"""Shim: alias of ai_pdf_api.services.research.research_versions_service."""
from __future__ import annotations

import sys

from ai_pdf_api.services.research import research_versions_service as _impl

# Make `import ai_pdf_api.services.research_versions_service` resolve to the package submodule object.
sys.modules[__name__] = _impl
