"""Compatibility alias for citeframe_persistence.models.pdf_page."""

from __future__ import annotations

import sys

from citeframe_persistence.models import pdf_page as _impl

sys.modules[__name__] = _impl
