"""Experiments repository for database operations."""

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Experiment


class ExperimentRepository:
    """Repository for experiment-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        product_id: int,
        old_price: Decimal,
        new_price: Decimal,
        start_date: date,
        review_date: date,
        baseline_sales: Optional[int] = None,
        baseline_revenue: Optional[Decimal] = None,
        recommendation_id: Optional[int] = None,
    ) -> Experiment:
        """Create a new price experiment."""
        experiment = Experiment(
            product_id=product_id,
            old_price=old_price,
            new_price=new_price,
            start_date=start_date,
            review_date=review_date,
            baseline_sales=baseline_sales,
            baseline_revenue=baseline_revenue,
            recommendation_id=recommendation_id,
            status="active",
        )
        self.session.add(experiment)
        await self.session.flush()
        return experiment

    async def get_active_experiments(self) -> list[Experiment]:
        """Get all active experiments."""
        result = await self.session.execute(
            select(Experiment).where(Experiment.status == "active")
        )
        return list(result.scalars().all())

    async def get_experiments_for_review(self, today: date) -> list[Experiment]:
        """Get experiments that should be reviewed today."""
        result = await self.session.execute(
            select(Experiment).where(
                Experiment.status == "active", Experiment.review_date <= today
            )
        )
        return list(result.scalars().all())

    async def get_by_product_id(self, product_id: int) -> Optional[Experiment]:
        """Get active experiment for a product."""
        result = await self.session.execute(
            select(Experiment).where(
                Experiment.product_id == product_id, Experiment.status == "active"
            )
        )
        return result.scalar_one_or_none()

    async def complete_experiment(
        self,
        experiment_id: int,
        result_sales: int,
        result_revenue: Decimal,
        sales_change_pct: Decimal,
        revenue_change_pct: Decimal,
        profit_change_pct: Decimal,
        verdict: str,
    ) -> None:
        """Mark an experiment as completed with results."""
        from datetime import datetime

        await self.session.execute(
            update(Experiment)
            .where(Experiment.id == experiment_id)
            .values(
                result_sales=result_sales,
                result_revenue=result_revenue,
                sales_change_pct=sales_change_pct,
                revenue_change_pct=revenue_change_pct,
                profit_change_pct=profit_change_pct,
                verdict=verdict,
                status="completed",
                completed_at=datetime.utcnow(),
            )
        )

    async def get_by_id(self, experiment_id: int) -> Optional[Experiment]:
        """Get experiment by ID."""
        result = await self.session.execute(select(Experiment).where(Experiment.id == experiment_id))
        return result.scalar_one_or_none()
