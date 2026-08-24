"""Compatibility alias for citeframe_persistence.models.chat_message."""

from __future__ import annotations

import sys

from citeframe_persistence.models import chat_message as _impl

sys.modules[__name__] = _impl
