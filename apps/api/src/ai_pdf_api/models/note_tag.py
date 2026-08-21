"""Compatibility alias for citeframe_persistence.models.note_tag."""

from __future__ import annotations

import sys

from citeframe_persistence.models import note_tag as _impl

sys.modules[__name__] = _impl
