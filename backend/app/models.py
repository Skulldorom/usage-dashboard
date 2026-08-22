from datetime import datetime
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

def json_type():
    return JSON().with_variant(JSONB, "postgresql")

class Base(DeclarativeBase):
    pass

class AdminCredential(Base):
    __tablename__ = "admin_credentials"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    session_tokens: Mapped[list] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    setup_code_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    setup_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_code_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    reset_code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ApiToken(Base):
    __tablename__ = "api_tokens"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    token_prefix: Mapped[str] = mapped_column(String(16))
    scopes: Mapped[list] = mapped_column(MutableList.as_mutable(json_type()), default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class ProviderConfig(Base):
    __tablename__ = "provider_configs"
    __table_args__ = (UniqueConstraint("provider", "label", name="uq_provider_label"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    label: Mapped[str] = mapped_column(String(120))
    encrypted_api_key: Mapped[str] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra: Mapped[dict] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    alert_thresholds: Mapped[list] = mapped_column(MutableList.as_mutable(json_type()), default=list)
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


class UsageObservation(Base):
    """Normalized analytics observation derived from snapshots, native history,
    or an external data source (e.g. Hermes telemetry)."""

    __tablename__ = "usage_observations"
    __table_args__ = (
        # Idempotency guard for data-source telemetry: within a single data
        # source, each source event ID is unique. Provider observations leave
        # data_source_id/source_event_id NULL, so the partial predicate keeps
        # them (and provider-only rows) untouched. Scoped to data_source_id so
        # two Hermes instances may legitimately reuse the same event ID.
        Index(
            "ux_usage_observations_source_event",
            "data_source_id",
            "source_event_id",
            unique=True,
            sqlite_where=text("data_source_id IS NOT NULL AND source_event_id IS NOT NULL"),
            postgresql_where=text("data_source_id IS NOT NULL AND source_event_id IS NOT NULL"),
        ),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Provider-backed observations link to a provider config; data-source
    # observations (source="hermes") link to a data source instead and leave
    # provider_config_id null.
    provider_config_id: Mapped[int | None] = mapped_column(ForeignKey("provider_configs.id", ondelete="CASCADE"), index=True, nullable=True)
    data_source_id: Mapped[int | None] = mapped_column(ForeignKey("data_source_configs.id", ondelete="CASCADE"), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), index=True)
    metric: Mapped[str] = mapped_column(String(120), index=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(16))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Telemetry provenance (Hermes and future data sources).
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile: Mapped[str | None] = mapped_column(String(64), nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cost_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    provider_mapping: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class DataSourceConfig(Base):
    """Configuration for an external usage telemetry source (e.g. Hermes Agent).

    Data sources are kept separate from providers: providers are the accounts
    whose usage is being measured, while data sources supply observed telemetry
    about usage flowing through them.
    """

    __tablename__ = "data_source_configs"
    __table_args__ = (UniqueConstraint("kind", "name", name="uq_data_source_kind_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(120))
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    extra: Mapped[dict] = mapped_column(MutableDict.as_mutable(json_type()), default=dict)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    poll_interval_minutes: Mapped[int] = mapped_column(Integer, default=60)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)
    latest_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
