"""Compatibility alias for citeframe_persistence.models.content_unit."""

from __future__ import annotations

import sys

from citeframe_persistence.models import content_unit as _impl

sys.modules[__name__] = _impl
