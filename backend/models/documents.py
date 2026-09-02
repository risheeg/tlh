import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from db.session import Base


class Document(Base):
    """Processed personal document indexed by the vault ingest pipeline."""
    __tablename__ = "documents"
    __table_args__ = {"schema": "vault_ingest"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), index=True, nullable=False
    )
    upload_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    category: Mapped[str] = mapped_column(String, index=True, nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), index=True, nullable=True
    )
    r2_original_path: Mapped[str] = mapped_column(Text, nullable=False)
    r2_file_path: Mapped[str] = mapped_column(Text, nullable=False)
    r2_parsed_json_path: Mapped[str] = mapped_column(Text, nullable=False)
    r2_markdown_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_model: Mapped[str] = mapped_column(String, nullable=False)
    parsed_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
