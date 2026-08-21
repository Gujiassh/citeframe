"""Compatibility alias for citeframe_persistence.models.message_citation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import message_citation as _impl

sys.modules[__name__] = _impl
