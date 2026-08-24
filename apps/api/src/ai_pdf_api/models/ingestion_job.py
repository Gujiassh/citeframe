"""Compatibility alias for citeframe_persistence.models.ingestion_job."""

from __future__ import annotations

import sys

from citeframe_persistence.models import ingestion_job as _impl

sys.modules[__name__] = _impl
