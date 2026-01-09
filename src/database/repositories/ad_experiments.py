"""Repository for advertising experiments."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import AdExperiment


class AdExperimentRepository:
    """Repository for managing ad experiments."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        campaign_id: str,
        campaign_name: str,
        campaign_type: str,
        action: str,
        start_date: date,
        review_date: date,
        duration_days: int = 7,
        product_id: Optional[int] = None,
        old_bid: Optional[Decimal] = None,
        new_bid: Optional[Decimal] = None,
        daily_budget: Optional[Decimal] = None,
        baseline_views: Optional[int] = None,
        baseline_clicks: Optional[int] = None,
        baseline_spend: Optional[Decimal] = None,
        baseline_orders: Optional[int] = None,
        baseline_revenue: Optional[Decimal] = None,
    ) -> AdExperiment:
        """Create a new ad experiment."""
        experiment = AdExperiment(
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            campaign_type=campaign_type,
            action=action,
            start_date=start_date,
            review_date=review_date,
            duration_days=duration_days,
            product_id=product_id,
            old_bid=old_bid,
            new_bid=new_bid,
            daily_budget=daily_budget,
            baseline_views=baseline_views,
            baseline_clicks=baseline_clicks,
            baseline_spend=baseline_spend,
            baseline_orders=baseline_orders,
            baseline_revenue=baseline_revenue,
            status="active",
        )
        self.session.add(experiment)
        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def get_by_id(self, experiment_id: int) -> Optional[AdExperiment]:
        """Get experiment by ID."""
        result = await self.session.execute(
            select(AdExperiment).where(AdExperiment.id == experiment_id)
        )
        return result.scalar_one_or_none()

    async def get_active_experiments(self) -> list[AdExperiment]:
        """Get all active experiments."""
        result = await self.session.execute(
            select(AdExperiment)
            .where(AdExperiment.status == "active")
            .order_by(AdExperiment.review_date)
        )
        return list(result.scalars().all())

    async def get_experiments_for_review(self, as_of_date: date) -> list[AdExperiment]:
        """Get experiments that are ready for review."""
        result = await self.session.execute(
            select(AdExperiment)
            .where(AdExperiment.status == "active")
            .where(AdExperiment.review_date <= as_of_date)
            .order_by(AdExperiment.review_date)
        )
        return list(result.scalars().all())

    async def get_by_campaign(
        self, campaign_id: str, status: Optional[str] = None
    ) -> list[AdExperiment]:
        """Get experiments for a campaign."""
        query = select(AdExperiment).where(AdExperiment.campaign_id == campaign_id)
        if status:
            query = query.where(AdExperiment.status == status)
        query = query.order_by(AdExperiment.created_at.desc())

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def update_results(
        self,
        experiment_id: int,
        result_views: int,
        result_clicks: int,
        result_spend: Decimal,
        result_orders: int,
        result_revenue: Decimal,
    ) -> Optional[AdExperiment]:
        """Update experiment with results."""
        experiment = await self.get_by_id(experiment_id)
        if not experiment:
            return None

        experiment.result_views = result_views
        experiment.result_clicks = result_clicks
        experiment.result_spend = result_spend
        experiment.result_orders = result_orders
        experiment.result_revenue = result_revenue

        # Calculate changes
        if experiment.baseline_clicks and experiment.baseline_views:
            old_ctr = experiment.baseline_clicks / experiment.baseline_views * 100
            new_ctr = result_clicks / result_views * 100 if result_views > 0 else 0
            experiment.ctr_change_pct = Decimal(str(new_ctr - old_ctr))

        if experiment.baseline_spend and experiment.baseline_clicks:
            old_cpc = float(experiment.baseline_spend) / experiment.baseline_clicks
            new_cpc = float(result_spend) / result_clicks if result_clicks > 0 else 0
            if old_cpc > 0:
                experiment.cpc_change_pct = Decimal(str((new_cpc - old_cpc) / old_cpc * 100))

        # Calculate ROAS
        if experiment.baseline_spend and experiment.baseline_revenue:
            experiment.roas_before = experiment.baseline_revenue / experiment.baseline_spend
        if result_spend and result_revenue:
            experiment.roas_after = result_revenue / result_spend

        experiment.status = "reviewing"
        await self.session.commit()
        await self.session.refresh(experiment)
        return experiment

    async def complete_experiment(
        self,
        experiment_id: int,
        verdict: str,
        recommendation: Optional[str] = None,
    ) -> Optional[AdExperiment]:
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

    async def get_recent_experiments(self, limit: int = 10) -> list[AdExperiment]:
        """Get recent experiments."""
        result = await self.session.execute(
            select(AdExperiment)
            .order_by(AdExperiment.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
