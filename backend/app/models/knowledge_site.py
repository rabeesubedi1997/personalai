"""
A website a tenant has connected as a knowledge source. The crawled page
chunks themselves live in `memory_records` (memory_type=KNOWLEDGE,
subject_id=<this site's id>) — this row is just the bookkeeping: what URL,
how the last crawl went, and how much content it produced.
"""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TenantScopedMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SiteStatus(str, enum.Enum):
    PENDING = "pending"
    CRAWLING = "crawling"
    READY = "ready"
    FAILED = "failed"


class KnowledgeSite(UUIDPrimaryKeyMixin, TenantScopedMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_sites"

    url: Mapped[str] = mapped_column(String(2048))
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[SiteStatus] = mapped_column(Enum(SiteStatus), default=SiteStatus.PENDING)
    max_pages: Mapped[int] = mapped_column(Integer, default=30)
    # Render pages in a headless browser (for React/Vue/etc. sites whose
    # HTML is an empty shell until JavaScript runs).
    render_js: Mapped[bool] = mapped_column(default=False)
    pages_count: Mapped[int] = mapped_column(Integer, default=0)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
