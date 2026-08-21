"""Compatibility alias for citeframe_persistence.models.asset_representation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import asset_representation as _impl

sys.modules[__name__] = _impl
