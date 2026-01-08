"""Inventory forecasting and stock management."""

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Product
from src.database.repositories.inventory import InventoryRepository
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository


@dataclass
class StockForecast:
    """Stock forecast for a product."""

    product_id: int
    product_name: str
    offer_id: str
    current_stock: int
    avg_daily_sales: float
    days_remaining: float
    urgency: str  # critical, warning, normal
    reorder_qty: int
    target_days: int = 30
    lead_time_days: int = 14


@dataclass
class ReorderRecommendation:
    """Recommendation to reorder stock."""

    product: Product
    forecast: StockForecast
    order_qty: int
    estimated_cost: float


class InventoryAnalytics:
    """Inventory forecasting and analysis."""

    def __init__(
        self, session: AsyncSession, target_days: int = 30, lead_time_days: int = 14
    ):
        self.session = session
        self.sales_repo = SalesRepository(session)
        self.inventory_repo = InventoryRepository(session)
        self.products_repo = ProductRepository(session)
        self.target_days = target_days
        self.lead_time_days = lead_time_days

    async def calculate_stock_forecast(self, product_id: int) -> Optional[StockForecast]:
        """Calculate stock forecast for a product."""
        product = await self.products_repo.get_by_product_id(product_id)
        if not product:
            return None

        # Get current stock
        current_stock = await self.inventory_repo.get_current_stock(product_id)

        # Get average daily sales (last 30 days)
        avg_daily_sales = await self.sales_repo.get_daily_average(product_id, days=30)

        # Calculate days remaining
        if avg_daily_sales > 0:
            days_remaining = current_stock / avg_daily_sales
        else:
            days_remaining = float("inf")

        # Determine urgency
        if days_remaining < 7:
            urgency = "critical"
        elif days_remaining < 14:
            urgency = "warning"
        else:
            urgency = "normal"

        # Calculate reorder quantity
        # Target: target_days of stock
        # Safety stock: lead_time_days worth of sales
        safety_stock = avg_daily_sales * self.lead_time_days
        target_stock = (avg_daily_sales * self.target_days) + safety_stock
        reorder_qty = max(0, ceil(target_stock - current_stock))

        return StockForecast(
            product_id=product_id,
            product_name=product.name,
            offer_id=product.offer_id,
            current_stock=current_stock,
            avg_daily_sales=avg_daily_sales,
            days_remaining=days_remaining,
            urgency=urgency,
            reorder_qty=reorder_qty,
            target_days=self.target_days,
            lead_time_days=self.lead_time_days,
        )

    async def get_low_stock_products(
        self, urgency_filter: Optional[str] = None
    ) -> list[StockForecast]:
        """Get products with low stock.

        Args:
            urgency_filter: Filter by urgency level (critical, warning, normal)

        Returns:
            List of stock forecasts sorted by urgency
        """
        products = await self.products_repo.get_all_active()
        forecasts = []

        for product in products:
            forecast = await self.calculate_stock_forecast(product.product_id)
            if forecast and forecast.urgency in ["critical", "warning"]:
                if urgency_filter is None or forecast.urgency == urgency_filter:
                    forecasts.append(forecast)

        # Sort by days remaining (ascending)
        forecasts.sort(key=lambda f: f.days_remaining)
        return forecasts

    async def get_reorder_recommendations(
        self, max_total_cost: Optional[float] = None
    ) -> list[ReorderRecommendation]:
        """Get list of products that need reordering.

        Args:
            max_total_cost: Optional maximum total cost limit

        Returns:
            List of reorder recommendations
        """
        low_stock = await self.get_low_stock_products()
        recommendations = []
        total_cost = 0.0

        for forecast in low_stock:
            if forecast.reorder_qty == 0:
                continue

            product = await self.products_repo.get_by_product_id(forecast.product_id)
            if not product:
                continue

            estimated_cost = float(product.cost_price) * forecast.reorder_qty

            # Check budget limit
            if max_total_cost and (total_cost + estimated_cost) > max_total_cost:
                continue

            recommendations.append(
                ReorderRecommendation(
                    product=product,
                    forecast=forecast,
                    order_qty=forecast.reorder_qty,
                    estimated_cost=estimated_cost,
                )
            )

            total_cost += estimated_cost

        return recommendations

    async def get_overstock_products(self, days_threshold: int = 90) -> list[StockForecast]:
        """Get products with excessive stock (more than days_threshold of inventory)."""
        products = await self.products_repo.get_all_active()
        overstock = []

        for product in products:
            forecast = await self.calculate_stock_forecast(product.product_id)
            if forecast and forecast.days_remaining > days_threshold:
                overstock.append(forecast)

        # Sort by days remaining (descending)
        overstock.sort(key=lambda f: f.days_remaining, reverse=True)
        return overstock

    async def get_inventory_summary(self) -> dict[str, any]:
        """Get overall inventory health summary."""
        products = await self.products_repo.get_all_active()
        total_products = len(products)

        critical_count = 0
        warning_count = 0
        normal_count = 0
        overstock_count = 0
        total_value = 0.0
        weighted_days = 0.0

        for product in products:
            forecast = await self.calculate_stock_forecast(product.product_id)
            if not forecast:
                continue

            # Count by urgency
            if forecast.urgency == "critical":
                critical_count += 1
            elif forecast.urgency == "warning":
                warning_count += 1
            else:
                normal_count += 1

            # Count overstock
            if forecast.days_remaining > 90:
                overstock_count += 1

            # Calculate total value
            total_value += float(product.cost_price) * forecast.current_stock

            # Weighted average days of inventory
            if forecast.days_remaining != float("inf"):
                weighted_days += forecast.days_remaining

        avg_days_inventory = weighted_days / total_products if total_products > 0 else 0

        return {
            "total_products": total_products,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "normal_count": normal_count,
            "overstock_count": overstock_count,
            "total_inventory_value": total_value,
            "avg_days_inventory": avg_days_inventory,
        }
