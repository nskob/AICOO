"""Inventory repository for database operations."""

from datetime import date
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Inventory


class InventoryRepository:
    """Repository for inventory-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def upsert(
        self,
        product_id: int,
        warehouse_name: str,
        quantity: int,
        reserved: int,
        snapshot_date: date,
    ) -> Inventory:
        """Create or update an inventory snapshot."""
        result = await self.session.execute(
            select(Inventory).where(
                Inventory.product_id == product_id,
                Inventory.warehouse_name == warehouse_name,
                Inventory.snapshot_date == snapshot_date,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.quantity = quantity
            existing.reserved = reserved
            await self.session.flush()
            return existing
        else:
            inventory = Inventory(
                product_id=product_id,
                warehouse_name=warehouse_name,
                quantity=quantity,
                reserved=reserved,
                snapshot_date=snapshot_date,
            )
            self.session.add(inventory)
            await self.session.flush()
            return inventory

    async def get_current_stock(self, product_id: int) -> int:
        """Get total current stock for a product across all warehouses."""
        latest_date = await self.session.execute(
            select(func.max(Inventory.snapshot_date)).where(Inventory.product_id == product_id)
        )
        latest = latest_date.scalar_one_or_none()

        if not latest:
            return 0

        result = await self.session.execute(
            select(func.sum(Inventory.quantity)).where(
                Inventory.product_id == product_id, Inventory.snapshot_date == latest
            )
        )
        total = result.scalar_one_or_none()
        return total or 0

    async def get_latest_snapshot(self, product_id: int) -> list[Inventory]:
        """Get the most recent inventory snapshot for a product."""
        latest_date = await self.session.execute(
            select(func.max(Inventory.snapshot_date)).where(Inventory.product_id == product_id)
        )
        latest = latest_date.scalar_one_or_none()

        if not latest:
            return []

        result = await self.session.execute(
            select(Inventory).where(
                Inventory.product_id == product_id, Inventory.snapshot_date == latest
            )
        )
        return list(result.scalars().all())

    async def get_all_current_stock(self) -> dict[int, int]:
        """Get current stock for all products.

        Returns dict of {product_id: total_quantity}.
        """
        # Get latest snapshot date
        latest_date_result = await self.session.execute(
            select(func.max(Inventory.snapshot_date))
        )
        latest = latest_date_result.scalar_one_or_none()

        if not latest:
            return {}

        # Get stock totals for latest snapshot
        result = await self.session.execute(
            select(Inventory.product_id, func.sum(Inventory.quantity).label("total"))
            .where(Inventory.snapshot_date == latest)
            .group_by(Inventory.product_id)
        )

        return {row.product_id: row.total for row in result.all()}
