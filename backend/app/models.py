from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

def json_type():
    return JSON().with_variant(JSONB, "postgresql")

class Base(DeclarativeBase):
    pass

class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("provider", "label", name="uq_provider_label"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(120))
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra: Mapped[dict] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    snapshots: Mapped[list["UsageSnapshot"]] = relationship(back_populates="config", cascade="all, delete-orphan")

class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider_config_id: Mapped[int] = mapped_column(ForeignKey("provider_configs.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32))
    summary: Mapped[str] = mapped_column(String(255))
    metrics: Mapped[list] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    raw: Mapped[dict] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    config: Mapped[ProviderConfig] = relationship(back_populates="snapshots")
