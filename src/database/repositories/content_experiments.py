"""Repository for content A/B experiments (name, description changes)."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import ContentExperiment


class ContentExperimentRepository:
    """Repository for managing content experiments."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        product_id: int,
        offer_id: str,
        product_name: str,
        field_type: str,  # 'name' or 'description'
        old_value: str,
        new_value: str,
        start_date: date,
        review_date: date,
        duration_days: int = 7,
        baseline_views: Optional[int] = None,
        baseline_add_to_cart: Optional[int] = None,
        baseline_orders: Optional[int] = None,
        baseline_revenue: Optional[Decimal] = None,
        baseline_conversion: Optional[Decimal] = None,
    ) -> ContentExperiment:
        """Create a new content experiment."""
        experiment = ContentExperiment(
            product_id=product_id,
            offer_id=offer_id,
            product_name=product_name,
            field_type=field_type,
            old_value=old_value,
            new_value=new_value,
            start_date=start_date,
            review_date=review_date,
            duration_days=duration_days,
            baseline_views=baseline_views,
            baseline_add_to_cart=baseline_add_to_cart,
            baseline_orders=baseline_orders,
            baseline_revenue=baseline_revenue,
            baseline_conversion=baseline_conversion,
            status="active",
        )
        self.session.add(experiment)
        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def get_by_id(self, experiment_id: int) -> Optional[ContentExperiment]:
        """Get experiment by ID."""
        result = await self.session.execute(
            select(ContentExperiment).where(ContentExperiment.id == experiment_id)
        )
        return result.scalar_one_or_none()

    async def get_active_experiments(self) -> list[ContentExperiment]:
        """Get all active experiments."""
        result = await self.session.execute(
            select(ContentExperiment)
            .where(ContentExperiment.status == "active")
            .order_by(ContentExperiment.review_date)
        )
        return list(result.scalars().all())

    async def get_experiments_for_review(self, as_of_date: date) -> list[ContentExperiment]:
        """Get experiments that are ready for review."""
        result = await self.session.execute(
            select(ContentExperiment)
            .where(ContentExperiment.status == "active")
            .where(ContentExperiment.review_date <= as_of_date)
            .order_by(ContentExperiment.review_date)
        )
        return list(result.scalars().all())

    async def get_by_product(
        self, product_id: int, status: Optional[str] = None
    ) -> list[ContentExperiment]:
        """Get experiments for a product."""
        query = select(ContentExperiment).where(ContentExperiment.product_id == product_id)
        if status:
            query = query.where(ContentExperiment.status == status)
        query = query.order_by(ContentExperiment.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def has_active_experiment(self, product_id: int, field_type: str) -> bool:
        """Check if product already has an active experiment for this field."""
        result = await self.session.execute(
            select(ContentExperiment)
            .where(ContentExperiment.product_id == product_id)
            .where(ContentExperiment.field_type == field_type)
            .where(ContentExperiment.status == "active")
        )
        return result.scalar_one_or_none() is not None

    async def update_results(
        self,
        experiment_id: int,
        result_views: int,
        result_add_to_cart: int,
        result_orders: int,
        result_revenue: Decimal,
        result_conversion: Optional[Decimal] = None,
    ) -> Optional[ContentExperiment]:
        """Update experiment with results."""
        experiment = await self.get_by_id(experiment_id)
        if not experiment:
            return None

        experiment.result_views = result_views
        experiment.result_add_to_cart = result_add_to_cart
        experiment.result_orders = result_orders
        experiment.result_revenue = result_revenue
        experiment.result_conversion = result_conversion

        experiment.status = "reviewing"
        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def complete_experiment(
        self,
        experiment_id: int,
        verdict: str,
        recommendation: Optional[str] = None,
    ) -> Optional[ContentExperiment]:
        """Complete an experiment with a verdict."""
        experiment = await self.get_by_id(experiment_id)
        if not experiment:
            return None

        experiment.status = "completed"
        experiment.verdict = verdict
        experiment.recommendation = recommendation
        experiment.completed_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def rollback_experiment(
        self,
        experiment_id: int,
    ) -> Optional[ContentExperiment]:
        """Mark experiment as rolled back (content reverted to old value)."""
        experiment = await self.get_by_id(experiment_id)
        if not experiment:
            return None

        experiment.status = "rolled_back"
        experiment.verdict = "FAILED"
        experiment.completed_at = datetime.now()

        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def get_recent_experiments(self, limit: int = 10) -> list[ContentExperiment]:
        """Get recent experiments."""
        result = await self.session.execute(
            select(ContentExperiment)
            .order_by(ContentExperiment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
