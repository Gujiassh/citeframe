"""Compatibility alias for citeframe_persistence.models.html_representation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import html_representation as _impl

sys.modules[__name__] = _impl
