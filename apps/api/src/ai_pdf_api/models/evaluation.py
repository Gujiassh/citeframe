"""Compatibility alias for citeframe_persistence.models.evaluation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import evaluation as _impl

sys.modules[__name__] = _impl
