"""Shim: alias of ai_pdf_api.services.research.research_context_policy."""
from __future__ import annotations

import sys

from ai_pdf_api.services.research import research_context_policy as _impl

# Make `import ai_pdf_api.services.research_context_policy` resolve to the package submodule object.
sys.modules[__name__] = _impl
