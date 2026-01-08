"""Product repository for database operations."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models import Product


class ProductRepository:
    """Repository for product-related database operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_product_id(self, product_id: int) -> Optional[Product]:
        """Get product by OZON product ID."""
        result = await self.session.execute(
            select(Product).where(Product.product_id == product_id)
        )
        return result.scalar_one_or_none()

    async def get_by_offer_id(self, offer_id: str) -> Optional[Product]:
        """Get product by offer ID (seller SKU)."""
        result = await self.session.execute(select(Product).where(Product.offer_id == offer_id))
        return result.scalar_one_or_none()

    async def get_all_active(self) -> list[Product]:
        """Get all active products."""
        result = await self.session.execute(select(Product).where(Product.is_active == True))
        return list(result.scalars().all())

    async def get_all(self) -> list[Product]:
        """Get all products."""
        result = await self.session.execute(select(Product))
        return list(result.scalars().all())

    async def create(
        self,
        product_id: int,
        offer_id: str,
        name: str,
        price: Decimal,
        old_price: Optional[Decimal] = None,
        cost_price: Decimal = Decimal("0"),
        min_margin_pct: Decimal = Decimal("20"),
        category: Optional[str] = None,
    ) -> Product:
        """Create a new product."""
        product = Product(
            product_id=product_id,
            offer_id=offer_id,
            name=name,
            price=price,
            old_price=old_price,
            cost_price=cost_price,
            min_margin_pct=min_margin_pct,
            category=category,
        )
        self.session.add(product)
        await self.session.flush()
        return product

    async def update_price(
        self, product_id: int, price: Decimal, old_price: Optional[Decimal] = None
    ) -> None:
        """Update product price."""
        await self.session.execute(
            update(Product)
            .where(Product.product_id == product_id)
            .values(price=price, old_price=old_price, updated_at=datetime.utcnow())
        )

    async def upsert(
        self,
        product_id: int,
        offer_id: str,
        name: str,
        price: Decimal,
        old_price: Optional[Decimal] = None,
        category: Optional[str] = None,
    ) -> Product:
        """Create or update a product."""
        existing = await self.get_by_product_id(product_id)
        if existing:
            existing.offer_id = offer_id
            existing.name = name
            existing.price = price
            existing.old_price = old_price
            if category:
                existing.category = category
            existing.updated_at = datetime.utcnow()
            await self.session.flush()
            return existing
        else:
            return await self.create(
                product_id=product_id,
                offer_id=offer_id,
                name=name,
                price=price,
                old_price=old_price,
                category=category,
            )

    async def get_low_margin_products(self, threshold_pct: Optional[Decimal] = None) -> list[Product]:
        """Get products with margin below their minimum threshold."""
        products = await self.get_all_active()
        low_margin = []
        for p in products:
            if p.cost_price > 0:
                margin_pct = (p.price - p.cost_price) / p.price * 100
                min_threshold = threshold_pct if threshold_pct else p.min_margin_pct
                if margin_pct < min_threshold:
                    low_margin.append(p)
        return low_margin
