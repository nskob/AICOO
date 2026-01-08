"""Price optimization and recommendation engine."""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Product
from src.database.repositories.experiments import ExperimentRepository
from src.database.repositories.inventory import InventoryRepository
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository

logger = logging.getLogger(__name__)


@dataclass
class PriceAnalysis:
    """Analysis data for price optimization."""

    product: Product
    days_of_stock: float
    sales_last_30d: int
    sales_trend_pct: float
    current_margin_pct: float
    avg_daily_sales: float


@dataclass
class PriceRecommendation:
    """Price change recommendation with scoring."""

    product_id: int
    product_name: str
    offer_id: str
    current_price: Decimal
    recommended_price: Decimal
    change_pct: Decimal
    direction: str  # UP or DOWN
    factors: list[str]
    score_up: Decimal
    score_down: Decimal
    baseline_sales_7d: int
    baseline_revenue_7d: Decimal


def round_to_nice_price(price: Decimal) -> Decimal:
    """Round price to a nice value (e.g., 990, 1490, 2990)."""
    price_float = float(price)

    if price_float < 100:
        # Round to nearest 9 (e.g., 49, 59, 69)
        return Decimal(str(int(round(price_float / 10) * 10 - 1)))
    elif price_float < 1000:
        # Round to nearest 90 (e.g., 290, 390, 490)
        return Decimal(str(int(round(price_float / 100) * 100 - 10)))
    else:
        # Round to nearest 490, 990, etc.
        return Decimal(str(int(round(price_float / 500) * 500 - 10)))


class PricingEngine:
    """Price optimization and recommendation engine."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.products_repo = ProductRepository(session)
        self.sales_repo = SalesRepository(session)
        self.inventory_repo = InventoryRepository(session)
        self.experiments_repo = ExperimentRepository(session)

    async def analyze_product(self, product_id: int) -> Optional[PriceAnalysis]:
        """Analyze a product for price optimization."""
        product = await self.products_repo.get_by_product_id(product_id)
        if not product:
            return None

        # Get inventory data
        current_stock = await self.inventory_repo.get_current_stock(product_id)
        avg_daily_sales = await self.sales_repo.get_daily_average(product_id, days=30)

        # Calculate days of stock
        if avg_daily_sales > 0:
            days_of_stock = current_stock / avg_daily_sales
        else:
            days_of_stock = float("inf")

        # Get sales last 30 days
        today = date.today()
        start_30d = today - timedelta(days=30)
        end_30d = today - timedelta(days=1)
        sales_last_30d, _ = await self.sales_repo.get_total_sales_for_period(
            product_id, start_30d, end_30d
        )

        # Calculate sales trend (last 7d vs previous 7d)
        last_7d_end = end_30d
        last_7d_start = last_7d_end - timedelta(days=6)
        last_7d_qty, _ = await self.sales_repo.get_total_sales_for_period(
            product_id, last_7d_start, last_7d_end
        )

        prev_7d_end = last_7d_start - timedelta(days=1)
        prev_7d_start = prev_7d_end - timedelta(days=6)
        prev_7d_qty, _ = await self.sales_repo.get_total_sales_for_period(
            product_id, prev_7d_start, prev_7d_end
        )

        sales_trend_pct = (
            ((last_7d_qty - prev_7d_qty) / prev_7d_qty * 100) if prev_7d_qty > 0 else 0.0
        )

        # Calculate current margin
        if product.cost_price > 0 and product.price > 0:
            current_margin_pct = float(
                (product.price - product.cost_price) / product.price * 100
            )
        else:
            current_margin_pct = 0.0

        return PriceAnalysis(
            product=product,
            days_of_stock=days_of_stock,
            sales_last_30d=sales_last_30d,
            sales_trend_pct=sales_trend_pct,
            current_margin_pct=current_margin_pct,
            avg_daily_sales=avg_daily_sales,
        )

    async def generate_recommendation(
        self, product_id: int
    ) -> Optional[PriceRecommendation]:
        """Generate price recommendation for a product based on scoring system."""
        analysis = await self.analyze_product(product_id)
        if not analysis:
            return None

        product = analysis.product
        score_up = Decimal("0")
        score_down = Decimal("0")
        factors = []

        # Inventory factors
        if analysis.days_of_stock > 90:
            score_down += Decimal("2")
            factors.append(f"Затоваривание ({analysis.days_of_stock:.0f} дней запаса)")
        elif analysis.days_of_stock > 60:
            score_down += Decimal("1")
            factors.append(f"Избыток запаса ({analysis.days_of_stock:.0f} дней)")
        elif analysis.days_of_stock < 7:
            score_up += Decimal("2")
            factors.append(f"Дефицит (<7 дней запаса)")
        elif analysis.days_of_stock < 14:
            score_up += Decimal("1")
            factors.append(f"Мало запаса (7-14 дней)")

        # Sales trend factors
        if analysis.sales_trend_pct < -50:
            score_down += Decimal("3")
            factors.append(f"Критическое падение продаж ({analysis.sales_trend_pct:.0f}%)")
        elif analysis.sales_trend_pct < -30:
            score_down += Decimal("2")
            factors.append(f"Сильное падение ({analysis.sales_trend_pct:.0f}%)")
        elif analysis.sales_trend_pct < -15:
            score_down += Decimal("1")
            factors.append(f"Снижение продаж ({analysis.sales_trend_pct:.0f}%)")
        elif analysis.sales_trend_pct > 50:
            score_up += Decimal("2")
            factors.append(f"Взрывной рост ({analysis.sales_trend_pct:.0f}%)")
        elif analysis.sales_trend_pct > 30:
            score_up += Decimal("1.5")
            factors.append(f"Сильный рост ({analysis.sales_trend_pct:.0f}%)")

        # Margin factors
        if analysis.current_margin_pct < float(product.min_margin_pct):
            score_up += Decimal("3")
            factors.append(
                f"Низкая маржа ({analysis.current_margin_pct:.1f}% < {product.min_margin_pct}%)"
            )

        # No sales check
        if analysis.sales_last_30d == 0:
            score_down += Decimal("2")
            factors.append("Нет продаж за 30 дней")

        # Determine recommendation
        if score_up > score_down and score_up >= Decimal("2"):
            direction = "UP"
            change_pct = min(score_up * Decimal("5"), Decimal("15"))  # Max 15%
        elif score_down > score_up and score_down >= Decimal("2"):
            direction = "DOWN"
            change_pct = min(score_down * Decimal("5"), Decimal("15"))  # Max 15%
        else:
            # No strong recommendation
            return None

        # Calculate new price
        if direction == "UP":
            new_price = product.price * (Decimal("1") + change_pct / Decimal("100"))
        else:
            new_price = product.price * (Decimal("1") - change_pct / Decimal("100"))

        # Protect minimum margin
        min_price = product.cost_price * (
            Decimal("1") + product.min_margin_pct / Decimal("100")
        )
        new_price = max(new_price, min_price)

        # Round to nice price
        new_price = round_to_nice_price(new_price)

        # Don't recommend if change is too small
        actual_change_pct = abs(
            (new_price - product.price) / product.price * Decimal("100")
        )
        if actual_change_pct < Decimal("3"):  # Less than 3% change
            return None

        # Get baseline sales
        today = date.today()
        baseline_end = today - timedelta(days=1)
        baseline_start = baseline_end - timedelta(days=6)
        baseline_sales, baseline_revenue = await self.sales_repo.get_total_sales_for_period(
            product_id, baseline_start, baseline_end
        )

        return PriceRecommendation(
            product_id=product_id,
            product_name=product.name,
            offer_id=product.offer_id,
            current_price=product.price,
            recommended_price=new_price,
            change_pct=actual_change_pct,
            direction=direction,
            factors=factors,
            score_up=score_up,
            score_down=score_down,
            baseline_sales_7d=baseline_sales,
            baseline_revenue_7d=baseline_revenue,
        )

    async def get_products_for_analysis(self) -> list[int]:
        """Get list of product IDs that should be analyzed.

        Excludes products with active experiments.
        """
        # Get all active products
        products = await self.products_repo.get_all_active()

        # Get products with active experiments
        active_experiments = await self.experiments_repo.get_active_experiments()
        blocked_ids = {exp.product_id for exp in active_experiments}

        # Filter out blocked products
        eligible_ids = [p.product_id for p in products if p.product_id not in blocked_ids]

        return eligible_ids

    async def generate_all_recommendations(self) -> list[PriceRecommendation]:
        """Generate price recommendations for all eligible products."""
        eligible_product_ids = await self.get_products_for_analysis()
        recommendations = []

        logger.info(f"Analyzing {len(eligible_product_ids)} products for price optimization")

        for product_id in eligible_product_ids:
            try:
                rec = await self.generate_recommendation(product_id)
                if rec:
                    recommendations.append(rec)
            except Exception as e:
                logger.error(f"Failed to generate recommendation for product {product_id}: {e}")

        logger.info(f"Generated {len(recommendations)} price recommendations")
        return recommendations
