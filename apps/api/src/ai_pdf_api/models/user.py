"""Compatibility alias for citeframe_persistence.models.user."""

from __future__ import annotations

import sys

from citeframe_persistence.models import user as _impl

sys.modules[__name__] = _impl
