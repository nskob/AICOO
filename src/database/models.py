"""SQLAlchemy database models."""

from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models."""

    pass


class Product(Base):
    """Product catalog with pricing and margin configuration."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    offer_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    old_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    cost_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("0"))
    min_margin_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("20"))
    category: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Sale(Base):
    """Daily sales aggregates per product."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=Decimal("0"))
    returns_qty: Mapped[int] = mapped_column(Integer, default=0)
    returns_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("product_id", "date", name="uq_sales_product_date"),
        Index("idx_sales_product_date", "product_id", "date"),
    )


class Inventory(Base):
    """Inventory snapshots per warehouse."""

    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    warehouse_name: Mapped[str] = mapped_column(String(200), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved: Mapped[int] = mapped_column(Integer, default=0)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "product_id", "warehouse_name", "snapshot_date", name="uq_inventory_snapshot"
        ),
    )


class PriceHistory(Base):
    """Historical price changes tracking."""

    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    old_price: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False)  # sync, manual, experiment
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class PriceRecommendation(Base):
    """Price change recommendations with approval workflow."""

    __tablename__ = "price_recommendations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    change_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    current_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    recommended_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    change_pct: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)  # UP or DOWN
    factors: Mapped[dict] = mapped_column(JSON, nullable=False)
    score_up: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    score_down: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"))
    status: Mapped[str] = mapped_column(
        String(20), default="pending", index=True
    )  # pending, approved, rejected, applied
    telegram_message_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    baseline_sales_7d: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    baseline_revenue_7d: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Experiment(Base):
    """A/B price testing experiments."""

    __tablename__ = "experiments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recommendation_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    product_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    old_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    review_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    baseline_sales: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    baseline_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    result_sales: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    result_revenue: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    sales_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    revenue_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    profit_change_pct: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", index=True
    )  # active, completed
    verdict: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # SUCCESS, FAILED, NEUTRAL
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Log(Base):
    """System logs for auditing and debugging."""

    __tablename__ = "logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    component: Mapped[str] = mapped_column(String(50), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
