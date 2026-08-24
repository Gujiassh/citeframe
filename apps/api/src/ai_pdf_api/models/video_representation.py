"""Compatibility alias for citeframe_persistence.models.video_representation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import video_representation as _impl

sys.modules[__name__] = _impl
