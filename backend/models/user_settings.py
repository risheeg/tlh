import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from db.session import Base


# JSONB on Postgres; plain JSON elsewhere (e.g. sqlite unit tests)
JsonType = JSON().with_variant(JSONB(), "postgresql")


class UserSettings(Base):
    """Per-user product configuration (spreadsheet layout, Sheets sync, TLH policy)."""

    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), primary_key=True
    )
    default_group_by: Mapped[str] = mapped_column(
        String(20), nullable=False, default="type"
    )
    spreadsheet_columns: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    category_order: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    ticker_order: Mapped[list] = mapped_column(
        JsonType, nullable=False, default=list
    )
    portfolio_snapshot_sheet_id: Mapped[str | None] = mapped_column(
        String, nullable=True
    )
    google_sheets_credentials: Mapped[dict | None] = mapped_column(
        JsonType, nullable=True
    )
    tlh_notify_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), nullable=False, default=Decimal("1000")
    )
    tlh_excluded_categories: Mapped[list] = mapped_column(
        JsonType,
        nullable=False,
        default=lambda: ["Indvl Company", "Individual Stocks"],
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    user: Mapped["User"] = relationship("User")
