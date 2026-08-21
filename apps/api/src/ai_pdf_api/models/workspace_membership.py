"""Compatibility alias for citeframe_persistence.models.workspace_membership."""

from __future__ import annotations

import sys

from citeframe_persistence.models import workspace_membership as _impl

sys.modules[__name__] = _impl
