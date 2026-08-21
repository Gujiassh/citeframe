"""Compatibility alias for citeframe_persistence.models.audio_representation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import audio_representation as _impl

sys.modules[__name__] = _impl
