"""Compatibility alias for citeframe_persistence.models.content_unit_embedding."""

from __future__ import annotations

import sys

from citeframe_persistence.models import content_unit_embedding as _impl

sys.modules[__name__] = _impl
