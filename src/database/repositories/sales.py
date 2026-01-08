"""Sales repository for database operations."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Sale


class SalesRepository:
    """Repository for sales-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_product_and_date(self, product_id: int, sale_date: date) -> Optional[Sale]:
        """Get sales record for a specific product and date."""
        result = await self.session.execute(
            select(Sale).where(Sale.product_id == product_id, Sale.date == sale_date)
        )
        return result.scalar_one_or_none()

    async def upsert(
        self,
        product_id: int,
        sale_date: date,
        quantity: int,
        revenue: Decimal,
        returns_qty: int = 0,
        returns_amount: Decimal = Decimal("0"),
    ) -> Sale:
        """Create or update a sales record."""
        existing = await self.get_by_product_and_date(product_id, sale_date)
        if existing:
            existing.quantity = quantity
            existing.revenue = revenue
            existing.returns_qty = returns_qty
            existing.returns_amount = returns_amount
            await self.session.flush()
            return existing
        else:
            sale = Sale(
                product_id=product_id,
                date=sale_date,
                quantity=quantity,
                revenue=revenue,
                returns_qty=returns_qty,
                returns_amount=returns_amount,
            )
            self.session.add(sale)
            await self.session.flush()
            return sale

    async def get_sales_for_period(
        self, product_id: int, start_date: date, end_date: date
    ) -> list[Sale]:
        """Get all sales for a product within a date range."""
        result = await self.session.execute(
            select(Sale).where(
                Sale.product_id == product_id, Sale.date >= start_date, Sale.date <= end_date
            )
        )
        return list(result.scalars().all())

    async def get_total_sales_for_period(
        self, product_id: int, start_date: date, end_date: date
    ) -> tuple[int, Decimal]:
        """Get total quantity and revenue for a product in a period."""
        result = await self.session.execute(
            select(func.sum(Sale.quantity), func.sum(Sale.revenue)).where(
                Sale.product_id == product_id, Sale.date >= start_date, Sale.date <= end_date
            )
        )
        row = result.one()
        quantity = row[0] or 0
        revenue = row[1] or Decimal("0")
        return quantity, revenue

    async def get_daily_average(self, product_id: int, days: int) -> float:
        """Get average daily sales for a product over the last N days."""
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        total_qty, _ = await self.get_total_sales_for_period(product_id, start_date, end_date)
        return total_qty / days if days > 0 else 0.0

    async def get_all_sales_for_date(self, sale_date: date) -> list[Sale]:
        """Get all sales for a specific date."""
        result = await self.session.execute(select(Sale).where(Sale.date == sale_date))
        return list(result.scalars().all())

    async def get_total_for_date(self, sale_date: date) -> tuple[int, Decimal]:
        """Get total quantity and revenue for all products on a specific date."""
        result = await self.session.execute(
            select(func.sum(Sale.quantity), func.sum(Sale.revenue)).where(Sale.date == sale_date)
        )
        row = result.one()
        quantity = row[0] or 0
        revenue = row[1] or Decimal("0")
        return quantity, revenue

    async def get_top_products(
        self, start_date: date, end_date: date, limit: int = 5
    ) -> list[tuple[int, int, Decimal]]:
        """Get top selling products by quantity for a period.

        Returns list of (product_id, total_quantity, total_revenue).
        """
        result = await self.session.execute(
            select(
                Sale.product_id,
                func.sum(Sale.quantity).label("total_qty"),
                func.sum(Sale.revenue).label("total_revenue"),
            )
            .where(Sale.date >= start_date, Sale.date <= end_date)
            .group_by(Sale.product_id)
            .order_by(func.sum(Sale.quantity).desc())
            .limit(limit)
        )
        return [(row.product_id, row.total_qty, row.total_revenue) for row in result.all()]
