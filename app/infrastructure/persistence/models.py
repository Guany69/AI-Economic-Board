"""SQLAlchemy ORM models — the 11-table persistence schema.

Metric values are NUMERIC(24,10) (Decimal end to end). Large model/data
artifacts are registered by path + sha256 metadata only, never stored as
blobs (HLD invariant 10).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NUMERIC = Numeric(24, 10)


class Base(DeclarativeBase):
    pass


class SimulationRunRow(Base):
    __tablename__ = "simulation_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING','RUNNING','COMPLETED','FAILED')",
            name="ck_simulation_runs_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    baseline_id: Mapped[int | None] = mapped_column(ForeignKey("baselines.id"), nullable=True)
    horizon_quarters: Mapped[int] = mapped_column(Integer, nullable=False, default=14)
    error_type: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    change: Mapped["EconomicChangeRow | None"] = relationship(back_populates="run", uselist=False)


class EconomicChangeRow(Base):
    __tablename__ = "economic_changes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False, unique=True
    )
    variable_id: Mapped[str] = mapped_column(String(64), nullable=False)
    model_route: Mapped[str] = mapped_column(String(32), nullable=False)
    change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    change_value: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[SimulationRunRow] = relationship(back_populates="change")


class ModelVersionRow(Base):
    __tablename__ = "model_versions"
    __table_args__ = (UniqueConstraint("model_name", "version_label", name="uq_model_versions"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(32), nullable=False)   # FAIR | TAX_CALCULATOR | LLM
    version_label: Mapped[str] = mapped_column(String(128), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SimulationModelVersionRow(Base):
    __tablename__ = "simulation_model_versions"
    __table_args__ = (UniqueConstraint("run_id", "model_version_id", name="uq_sim_model_versions"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)


class ModelArtifactRow(Base):
    __tablename__ = "model_artifacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BaselineRow(Base):
    __tablename__ = "baselines"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE','RETIRED')", name="ck_baselines_status"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    fair_model_version_id: Mapped[int] = mapped_column(ForeignKey("model_versions.id"), nullable=False)
    solve_start: Mapped[str] = mapped_column(String(8), nullable=False)   # e.g. 2026Q3
    solve_end: Mapped[str] = mapped_column(String(8), nullable=False)
    snapshot_artifact_id: Mapped[int | None] = mapped_column(ForeignKey("model_artifacts.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BaselineMetricRow(Base):
    __tablename__ = "baseline_metrics"
    __table_args__ = (
        UniqueConstraint("baseline_id", "metric", "period", name="uq_baseline_metrics"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    baseline_id: Mapped[int] = mapped_column(ForeignKey("baselines.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    value: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)


class SimulationMetricRow(Base):
    __tablename__ = "simulation_metrics"
    __table_args__ = (
        UniqueConstraint("run_id", "metric", "period", name="uq_simulation_metrics"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    value: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    unit: Mapped[str] = mapped_column(String(64), nullable=False)


class MetricDeltaRow(Base):
    __tablename__ = "metric_deltas"
    __table_args__ = (
        UniqueConstraint("run_id", "metric", "period", name="uq_metric_deltas"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("simulation_runs.id"), nullable=False)
    metric: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(8), nullable=False)
    baseline_value: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    changed_value: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    absolute_delta: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    percentage_delta: Mapped[object | None] = mapped_column(NUMERIC, nullable=True)  # NULL when baseline == 0
    unit: Mapped[str] = mapped_column(String(64), nullable=False)


class TaxCalculatorResultRow(Base):
    __tablename__ = "tax_calculator_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False, unique=True
    )
    tax_year: Mapped[int] = mapped_column(Integer, nullable=False)
    reform: Mapped[dict] = mapped_column(JSONB, nullable=False)
    base_iitax: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    reform_iitax: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    base_payrolltax: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    reform_payrolltax: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    base_combined: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    reform_combined: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    base_agi: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    base_expanded_income: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    total_weight: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    soi_iitax: Mapped[bool] = mapped_column(Boolean, nullable=False)
    taxcalc_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaxFairAdapterResultRow(Base):
    __tablename__ = "tax_fair_adapter_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False, unique=True
    )
    tax_calculator_result_id: Mapped[int] = mapped_column(
        ForeignKey("tax_calculator_results.id"), nullable=False
    )
    mapping_id: Mapped[str] = mapped_column(String(64), nullable=False)
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    source_variable_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_fair_variable: Mapped[str] = mapped_column(String(16), nullable=False)
    fair_change_type: Mapped[str] = mapped_column(String(16), nullable=False)
    derived_delta: Mapped[object] = mapped_column(NUMERIC, nullable=False)
    quarterly_allocation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    quarterly_values: Mapped[dict] = mapped_column(JSONB, nullable=False)  # list of 14 strings
    conversion_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LLMInterpretationRow(Base):
    __tablename__ = "llm_interpretations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("simulation_runs.id"), nullable=False, unique=True
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    response_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    stop_reason: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
