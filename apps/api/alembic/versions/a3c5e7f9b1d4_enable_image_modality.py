"""enable the production image modality

Revision ID: a3c5e7f9b1d4
Revises: f2a4c6e8b0d1
Create Date: 2026-07-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c5e7f9b1d4"
down_revision: str | Sequence[str] | None = "f2a4c6e8b0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_image_enabled(enabled: bool) -> None:
    connection = op.get_bind()
    row = connection.execute(
        sa.text(
            "SELECT contract_version FROM asset_types WHERE kind = 'image'"
        )
    ).one_or_none()
    if row is None or int(row.contract_version) != 1:
        raise RuntimeError("Image modality catalog contract v1 is missing")
    connection.execute(
        sa.text("UPDATE asset_types SET enabled = :enabled WHERE kind = 'image'"),
        {"enabled": enabled},
    )


def upgrade() -> None:
    _set_image_enabled(True)


def downgrade() -> None:
    _set_image_enabled(False)
