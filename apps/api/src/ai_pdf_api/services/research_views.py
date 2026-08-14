"""Shim: alias of ai_pdf_api.services.research.research_views."""
from __future__ import annotations

import sys

from ai_pdf_api.services.research import research_views as _impl

# Make `import ai_pdf_api.services.research_views` resolve to the package submodule object.
sys.modules[__name__] = _impl
