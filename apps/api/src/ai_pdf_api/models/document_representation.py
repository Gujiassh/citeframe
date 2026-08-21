"""Compatibility alias for citeframe_persistence.models.document_representation."""

from __future__ import annotations

import sys

from citeframe_persistence.models import document_representation as _impl

sys.modules[__name__] = _impl
