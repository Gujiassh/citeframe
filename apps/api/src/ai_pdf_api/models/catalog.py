"""Compatibility alias for citeframe_persistence.models.catalog."""

from __future__ import annotations

import sys

from citeframe_persistence.models import catalog as _impl

sys.modules[__name__] = _impl
