"""Compatibility alias for citeframe_persistence.models.tag."""

from __future__ import annotations

import sys

from citeframe_persistence.models import tag as _impl

sys.modules[__name__] = _impl
