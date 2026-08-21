"""Compatibility alias for citeframe_persistence.models.workspace."""

from __future__ import annotations

import sys

from citeframe_persistence.models import workspace as _impl

sys.modules[__name__] = _impl
