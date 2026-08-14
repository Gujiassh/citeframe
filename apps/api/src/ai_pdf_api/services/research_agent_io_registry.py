"""Shim: alias of ai_pdf_api.services.research.research_agent_io_registry."""
from __future__ import annotations

import sys

from ai_pdf_api.services.research import research_agent_io_registry as _impl

# Make `import ai_pdf_api.services.research_agent_io_registry` resolve to the package submodule object.
sys.modules[__name__] = _impl
