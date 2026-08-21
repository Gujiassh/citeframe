"""Compatibility alias for citeframe_persistence.models.evidence_locator."""

from __future__ import annotations

import sys

from citeframe_persistence.models import evidence_locator as _impl

sys.modules[__name__] = _impl
