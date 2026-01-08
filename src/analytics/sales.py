"""Sales analytics and reporting."""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Product
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository


@dataclass
class SalesTrend:
    """Sales trend analysis for a product."""

    product_id: int
    product_name: str
    last_7d_qty: int
    last_7d_revenue: Decimal
    prev_7d_qty: int
    prev_7d_revenue: Decimal
    qty_change_pct: float
    revenue_change_pct: float
    avg_daily_qty: float
    avg_price: Decimal


@dataclass
class DailySummary:
    """Daily sales summary across all products."""

    date: date
    total_qty: int
    total_revenue: Decimal
    avg_order_value: Decimal
    products_sold: int


@dataclass
class TopProduct:
    """Top-selling product information."""

    product_id: int
    product_name: str
    offer_id: str
    quantity: int
    revenue: Decimal


class SalesAnalytics:
    """Sales analysis and reporting engine."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.sales_repo = SalesRepository(session)
        self.products_repo = ProductRepository(session)

    async def get_daily_summary(self, for_date: date) -> DailySummary:
        """Get sales summary for a specific date."""
        total_qty, total_revenue = await self.sales_repo.get_total_for_date(for_date)

        # Calculate average order value
        avg_order_value = total_revenue / total_qty if total_qty > 0 else Decimal("0")

        # Count unique products sold
        sales = await self.sales_repo.get_all_sales_for_date(for_date)
        products_sold = len([s for s in sales if s.quantity > 0])

        return DailySummary(
            date=for_date,
            total_qty=total_qty,
            total_revenue=total_revenue,
            avg_order_value=avg_order_value,
            products_sold=products_sold,
        )

    async def get_sales_trend(self, product_id: int) -> Optional[SalesTrend]:
        """Analyze sales trend for a product comparing last 7 days vs previous 7 days."""
        product = await self.products_repo.get_by_product_id(product_id)
        if not product:
            return None

        today = date.today()

        # Last 7 days
        last_7d_end = today - timedelta(days=1)
        last_7d_start = last_7d_end - timedelta(days=6)
        last_7d_qty, last_7d_revenue = await self.sales_repo.get_total_sales_for_period(
            product_id, last_7d_start, last_7d_end
        )

        # Previous 7 days
        prev_7d_end = last_7d_start - timedelta(days=1)
        prev_7d_start = prev_7d_end - timedelta(days=6)
        prev_7d_qty, prev_7d_revenue = await self.sales_repo.get_total_sales_for_period(
            product_id, prev_7d_start, prev_7d_end
        )

        # Calculate changes
        qty_change_pct = (
            ((last_7d_qty - prev_7d_qty) / prev_7d_qty * 100) if prev_7d_qty > 0 else 0.0
        )
        revenue_change_pct = (
            ((float(last_7d_revenue) - float(prev_7d_revenue)) / float(prev_7d_revenue) * 100)
            if prev_7d_revenue > 0
            else 0.0
        )

        # Average daily quantity
        avg_daily_qty = last_7d_qty / 7.0

        # Average price
        avg_price = last_7d_revenue / last_7d_qty if last_7d_qty > 0 else Decimal("0")

        return SalesTrend(
            product_id=product_id,
            product_name=product.name,
            last_7d_qty=last_7d_qty,
            last_7d_revenue=last_7d_revenue,
            prev_7d_qty=prev_7d_qty,
            prev_7d_revenue=prev_7d_revenue,
            qty_change_pct=qty_change_pct,
            revenue_change_pct=revenue_change_pct,
            avg_daily_qty=avg_daily_qty,
            avg_price=avg_price,
        )

    async def get_top_products(
        self, start_date: date, end_date: date, limit: int = 5
    ) -> list[TopProduct]:
        """Get top-selling products for a period."""
        top_sales = await self.sales_repo.get_top_products(start_date, end_date, limit)

        result = []
        for product_id, quantity, revenue in top_sales:
            product = await self.products_repo.get_by_product_id(product_id)
            if product:
                result.append(
                    TopProduct(
                        product_id=product_id,
                        product_name=product.name,
                        offer_id=product.offer_id,
                        quantity=quantity,
                        revenue=revenue,
                    )
                )

        return result

    async def detect_anomalies(self, product_id: int, window_days: int = 30) -> dict[str, any]:
        """Detect sales anomalies using statistical analysis.

        Compares recent sales to historical average using standard deviation.
        """
        today = date.today()
        yesterday = today - timedelta(days=1)

        # Get last 30 days of sales
        start_date = yesterday - timedelta(days=window_days - 1)
        sales = await self.sales_repo.get_sales_for_period(product_id, start_date, yesterday)

        if not sales or len(sales) < 7:
            return {"anomaly": False, "reason": "Insufficient data"}

        # Calculate statistics
        daily_quantities = [s.quantity for s in sales]
        avg_qty = statistics.mean(daily_quantities)
        std_dev = statistics.stdev(daily_quantities) if len(daily_quantities) > 1 else 0

        # Check yesterday
        yesterday_sale = next((s for s in sales if s.date == yesterday), None)
        if not yesterday_sale:
            return {"anomaly": False, "yesterday_qty": 0, "avg_qty": avg_qty}

        yesterday_qty = yesterday_sale.quantity

        # Detect anomaly (2 standard deviations)
        lower_bound = avg_qty - (2 * std_dev)
        upper_bound = avg_qty + (2 * std_dev)

        anomaly = False
        anomaly_type = None

        if yesterday_qty < lower_bound:
            anomaly = True
            anomaly_type = "drop"
        elif yesterday_qty > upper_bound:
            anomaly = True
            anomaly_type = "spike"

        return {
            "anomaly": anomaly,
            "type": anomaly_type,
            "yesterday_qty": yesterday_qty,
            "avg_qty": avg_qty,
            "std_dev": std_dev,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
        }

    async def get_products_with_no_sales(self, days: int = 30) -> list[Product]:
        """Get products with zero sales in the last N days."""
        products = await self.products_repo.get_all_active()
        no_sales_products = []

        end_date = date.today() - timedelta(days=1)
        start_date = end_date - timedelta(days=days - 1)

        for product in products:
            total_qty, _ = await self.sales_repo.get_total_sales_for_period(
                product.product_id, start_date, end_date
            )
            if total_qty == 0:
                no_sales_products.append(product)

        return no_sales_products
