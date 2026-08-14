"""Shim: alias of ai_pdf_api.services.research.research_idempotency."""
from __future__ import annotations

import sys

from ai_pdf_api.services.research import research_idempotency as _impl

# Make `import ai_pdf_api.services.research_idempotency` resolve to the package submodule object.
sys.modules[__name__] = _impl
