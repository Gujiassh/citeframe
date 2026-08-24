"""Compatibility alias for citeframe_persistence.models.chat_thread."""

from __future__ import annotations

import sys

from citeframe_persistence.models import chat_thread as _impl

sys.modules[__name__] = _impl
