"""Price recommendations repository for database operations."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import PriceRecommendation


class PriceRecommendationRepository:
    """Repository for price recommendation operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        change_id: str,
        product_id: int,
        current_price: Decimal,
        recommended_price: Decimal,
        change_pct: Decimal,
        direction: str,
        factors: dict,
        score_up: Decimal,
        score_down: Decimal,
        baseline_sales_7d: Optional[int] = None,
        baseline_revenue_7d: Optional[Decimal] = None,
    ) -> PriceRecommendation:
        """Create a new price recommendation."""
        recommendation = PriceRecommendation(
            change_id=change_id,
            product_id=product_id,
            current_price=current_price,
            recommended_price=recommended_price,
            change_pct=change_pct,
            direction=direction,
            factors=factors,
            score_up=score_up,
            score_down=score_down,
            baseline_sales_7d=baseline_sales_7d,
            baseline_revenue_7d=baseline_revenue_7d,
            status="pending",
        )
        self.session.add(recommendation)
        await self.session.flush()
        return recommendation

    async def get_pending_recommendations(self) -> list[PriceRecommendation]:
        """Get all pending price recommendations."""
        result = await self.session.execute(
            select(PriceRecommendation).where(PriceRecommendation.status == "pending")
        )
        return list(result.scalars().all())

    async def get_by_change_id(self, change_id: str) -> Optional[PriceRecommendation]:
        """Get recommendation by change ID."""
        result = await self.session.execute(
            select(PriceRecommendation).where(PriceRecommendation.change_id == change_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, rec_id: int) -> Optional[PriceRecommendation]:
        """Get recommendation by ID."""
        result = await self.session.execute(
            select(PriceRecommendation).where(PriceRecommendation.id == rec_id)
        )
        return result.scalar_one_or_none()

    async def update_status(
        self, recommendation_id: int, status: str, telegram_message_id: Optional[int] = None
    ) -> None:
        """Update recommendation status."""
        values = {"status": status, "reviewed_at": datetime.utcnow()}
        if telegram_message_id is not None:
            values["telegram_message_id"] = telegram_message_id

        await self.session.execute(
            update(PriceRecommendation)
            .where(PriceRecommendation.id == recommendation_id)
            .values(**values)
        )

    async def mark_applied(self, recommendation_id: int) -> None:
        """Mark recommendation as applied."""
        await self.session.execute(
            update(PriceRecommendation)
            .where(PriceRecommendation.id == recommendation_id)
            .values(status="applied", applied_at=datetime.utcnow())
        )
