"""Data synchronization between OZON API and local database."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.inventory import InventoryRepository
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository
from src.ozon.client import OzonClient

logger = logging.getLogger(__name__)


class OzonDataSync:
    """Handles synchronization of data from OZON API to database."""

    def __init__(self, ozon_client: OzonClient, session: AsyncSession):
        self.ozon = ozon_client
        self.session = session
        self.products_repo = ProductRepository(session)
        self.sales_repo = SalesRepository(session)
        self.inventory_repo = InventoryRepository(session)

    async def sync_products(self) -> int:
        """Sync product catalog from OZON.

        Returns:
            Number of products synchronized
        """
        logger.info("Starting product sync")

        try:
            # Get all product IDs
            product_list = await self.ozon.get_product_list()
            if not product_list:
                logger.warning("No products found in OZON")
                return 0

            # Get detailed info in batches of 100
            batch_size = 100
            total_synced = 0

            for i in range(0, len(product_list), batch_size):
                batch = product_list[i : i + batch_size]
                product_ids = [p.product_id for p in batch]

                # Get detailed product info
                products_info = await self.ozon.get_product_info(product_ids)

                # Upsert to database
                for product in products_info:
                    await self.products_repo.upsert(
                        product_id=product.product_id,
                        offer_id=product.offer_id,
                        name=product.name,
                        price=Decimal(product.price),
                        old_price=Decimal(product.old_price) if product.old_price != "0" else None,
                    )
                    total_synced += 1

                await self.session.commit()
                logger.info(f"Synced batch {i // batch_size + 1}: {len(products_info)} products")

            logger.info(f"Product sync completed: {total_synced} products")
            return total_synced

        except Exception as e:
            logger.error(f"Product sync failed: {e}")
            await self.session.rollback()
            raise

    async def sync_inventory(self, snapshot_date: date = None) -> int:
        """Sync inventory/stock data from OZON.

        Args:
            snapshot_date: Date for the snapshot (default: today)

        Returns:
            Number of inventory records synchronized
        """
        if snapshot_date is None:
            snapshot_date = date.today()

        logger.info(f"Starting inventory sync for {snapshot_date}")

        try:
            # Get stock data for all products
            stock_items = await self.ozon.get_stocks()
            total_synced = 0

            for item in stock_items:
                if not item.stocks:
                    continue

                # Create inventory record for each warehouse
                for stock in item.stocks:
                    warehouse_name = stock.warehouse_name or "Default"
                    await self.inventory_repo.upsert(
                        product_id=item.product_id,
                        warehouse_name=warehouse_name,
                        quantity=stock.present,
                        reserved=stock.reserved,
                        snapshot_date=snapshot_date,
                    )
                    total_synced += 1

            await self.session.commit()
            logger.info(f"Inventory sync completed: {total_synced} records")
            return total_synced

        except Exception as e:
            logger.error(f"Inventory sync failed: {e}")
            await self.session.rollback()
            raise

    async def sync_sales(self, days_back: int = 7) -> int:
        """Sync sales data from OZON analytics.

        Args:
            days_back: Number of days to sync backwards from today

        Returns:
            Number of sales records synchronized
        """
        logger.info(f"Starting sales sync for last {days_back} days")

        try:
            end_date = date.today() - timedelta(days=1)  # Yesterday
            start_date = end_date - timedelta(days=days_back - 1)

            # Get analytics data
            analytics = await self.ozon.get_analytics_data(
                date_from=start_date,
                date_to=end_date,
                metrics=["ordered_units", "revenue", "returns"],
                dimension=["sku", "day"],
            )

            data = analytics.get("data", [])
            total_synced = 0

            for row in data:
                dimensions = row.get("dimensions", [])
                metrics = row.get("metrics", [])

                if not dimensions or not metrics:
                    continue

                # Extract dimensions
                sku = None
                sale_date = None
                for dim in dimensions:
                    if dim.get("id") == "sku":
                        sku = dim.get("value")
                    elif dim.get("id") == "day":
                        sale_date = date.fromisoformat(dim.get("value"))

                if not sku or not sale_date:
                    continue

                # Get product by offer_id (sku)
                product = await self.products_repo.get_by_offer_id(sku)
                if not product:
                    logger.warning(f"Product not found for SKU: {sku}")
                    continue

                # Extract metrics
                ordered_units = int(metrics[0]) if len(metrics) > 0 else 0
                revenue = Decimal(str(metrics[1])) if len(metrics) > 1 else Decimal("0")
                returns = int(metrics[2]) if len(metrics) > 2 else 0

                # Upsert sales record
                await self.sales_repo.upsert(
                    product_id=product.product_id,
                    sale_date=sale_date,
                    quantity=ordered_units,
                    revenue=revenue,
                    returns_qty=returns,
                    returns_amount=Decimal("0"),  # OZON doesn't provide return amounts
                )
                total_synced += 1

            await self.session.commit()
            logger.info(f"Sales sync completed: {total_synced} records")
            return total_synced

        except Exception as e:
            logger.error(f"Sales sync failed: {e}")
            await self.session.rollback()
            raise

    async def sync_all(self, sales_days_back: int = 7) -> dict[str, int]:
        """Sync all data from OZON.

        Args:
            sales_days_back: Number of days of sales history to sync

        Returns:
            Dictionary with counts of synced records
        """
        logger.info("Starting full OZON data sync")

        results = {}

        # Sync products first (required for sales sync)
        results["products"] = await self.sync_products()

        # Sync inventory
        results["inventory"] = await self.sync_inventory()

        # Sync sales
        results["sales"] = await self.sync_sales(days_back=sales_days_back)

        logger.info(f"Full sync completed: {results}")
        return results
