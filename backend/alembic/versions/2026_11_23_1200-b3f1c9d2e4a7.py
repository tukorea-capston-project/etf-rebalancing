"""시세 ETF 전체 저장: 날짜별 전체 저장 여부 추가, ETF별 백필 기록 삭제

Revision ID: b3f1c9d2e4a7
Revises: 7ec891a28399
Create Date: 2026-11-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b3f1c9d2e4a7"
down_revision: str | Sequence[str] | None = "7ec891a28399"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 기존 영업일은 일부 ETF만 저장했으므로 거짓으로 두고, 다음 수집 때 다시 받아 채운다.
    op.add_column(
        "price_collection_log",
        sa.Column(
            "all_etfs_saved", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.drop_table("etf_backfill")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "etf_backfill",
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(length=6), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )
    op.drop_column("price_collection_log", "all_etfs_saved")
