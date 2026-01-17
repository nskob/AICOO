"""OZON Seller API client."""

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional

import httpx

from src.config import settings
from src.ozon.models import (
    OzonAnalyticsResponse,
    OzonPriceUpdate,
    OzonPriceUpdateResponse,
    OzonProductFull,
    OzonProductInfoResponse,
    OzonProductListResponse,
    OzonProductShort,
    OzonStockItem,
    OzonStocksResponse,
)

logger = logging.getLogger(__name__)


class OzonClient:
    """Client for interacting with OZON Seller API."""

    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self, client_id: Optional[str] = None, api_key: Optional[str] = None):
        """Initialize OZON API client."""
        self.client_id = client_id or settings.ozon_client_id
        self.api_key = api_key or settings.ozon_api_key
        self.client = httpx.AsyncClient(timeout=30.0)

    def _get_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_product_list(self) -> list[OzonProductShort]:
        """Get list of all products.

        Returns minimal product info (product_id, offer_id).
        """
        url = f"{self.BASE_URL}/v3/product/list"
        payload = {"filter": {"visibility": "ALL"}, "limit": 1000}

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            result = OzonProductListResponse(**data["result"])
            logger.info(f"Fetched {len(result.items)} products from OZON")
            return result.items
        except Exception as e:
            logger.error(f"Failed to fetch product list: {e}")
            raise

    async def get_product_info(self, product_ids: list[int]) -> list[OzonProductFull]:
        """Get detailed information for specific products.

        Args:
            product_ids: List of OZON product IDs

        Returns:
            List of detailed product information
        """
        url = f"{self.BASE_URL}/v3/product/info/list"
        payload = {"product_id": product_ids}

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            # v3 API returns items at root level, not under result
            items_data = data.get("items", data.get("result", {}).get("items", []))
            items = [OzonProductFull(**item) for item in items_data]
            logger.info(f"Fetched details for {len(items)} products")
            return items
        except Exception as e:
            logger.error(f"Failed to fetch product info: {e}")
            raise

    async def get_stocks(self, product_ids: Optional[list[int]] = None) -> list[OzonStockItem]:
        """Get warehouse stock information for products.

        Args:
            product_ids: Optional list of product IDs. If None, gets all products.

        Returns:
            List of stock information by warehouse
        """
        url = f"{self.BASE_URL}/v4/product/info/stocks"
        payload = {"filter": {"visibility": "ALL"}, "limit": 1000}
        if product_ids:
            payload["filter"]["product_id"] = product_ids

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            # v4 returns items at root level
            items_data = data.get("items", [])
            items = [OzonStockItem(**item) for item in items_data]
            logger.info(f"Fetched stocks for {len(items)} products")
            return items
        except Exception as e:
            logger.error(f"Failed to fetch stocks: {e}")
            raise

    async def get_analytics_data(
        self, date_from: date, date_to: date, metrics: list[str], dimension: list[str]
    ) -> dict[str, Any]:
        """Get analytics data (sales, revenue, etc.) for a date range.

        Args:
            date_from: Start date
            date_to: End date
            metrics: List of metrics (e.g., ["ordered_units", "revenue"])
            dimension: List of dimensions (e.g., ["sku", "day"])

        Returns:
            Raw analytics data
        """
        url = f"{self.BASE_URL}/v1/analytics/data"
        payload = {
            "date_from": date_from.isoformat(),
            "date_to": date_to.isoformat(),
            "metrics": metrics,
            "dimension": dimension,
            "filters": [],
            "limit": 1000,
            "offset": 0,
        }

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            logger.info(f"Fetched analytics from {date_from} to {date_to}")
            return data.get("result", {})
        except Exception as e:
            logger.error(f"Failed to fetch analytics: {e}")
            raise

    async def update_prices(self, price_updates: list[OzonPriceUpdate]) -> OzonPriceUpdateResponse:
        """Update product prices.

        CRITICAL: All price values must be strings, and auto-pricing must be disabled.

        Args:
            price_updates: List of price update objects

        Returns:
            Update response with results and errors
        """
        url = f"{self.BASE_URL}/v1/product/import/prices"
        payload = {"prices": [update.model_dump() for update in price_updates]}

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            result = OzonPriceUpdateResponse(**data)
            logger.info(f"Updated prices for {len(price_updates)} products")
            return result
        except Exception as e:
            logger.error(f"Failed to update prices: {e}")
            raise

    async def update_price(
        self,
        product_id: int,
        price: Decimal,
        old_price: Optional[Decimal] = None,
        min_price: Optional[Decimal] = None,
    ) -> bool:
        """Update price for a single product.

        Args:
            product_id: OZON product ID
            price: New price
            old_price: Optional old/crossed-out price
            min_price: Optional minimum price

        Returns:
            True if successful, False otherwise
        """
        update = OzonPriceUpdate(
            product_id=product_id,
            price=str(price),
            old_price=str(old_price) if old_price else "0",
            min_price=str(min_price) if min_price else None,
        )

        try:
            result = await self.update_prices([update])
            if result.errors:
                logger.error(f"Price update had errors: {result.errors}")
                return False
            return True
        except Exception as e:
            logger.error(f"Failed to update price for product {product_id}: {e}")
            return False

    async def get_product_attributes(self, product_id: int) -> dict[str, Any]:
        """Get product attributes including name and description.

        Args:
            product_id: OZON product ID

        Returns:
            Product attributes dict
        """
        url = f"{self.BASE_URL}/v4/product/info/attributes"
        payload = {
            "filter": {"product_id": [product_id]},
            "limit": 1
        }

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            items = data.get("result", [])
            if items:
                return items[0]
            return {}
        except Exception as e:
            logger.error(f"Failed to get product attributes for {product_id}: {e}")
            raise

    async def update_product_content(
        self,
        offer_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> bool:
        """Update product name and/or description.

        Uses /v3/product/import-by-sku endpoint.

        Args:
            offer_id: Seller's SKU (offer_id)
            name: New product name (optional)
            description: New product description (optional)

        Returns:
            True if update was accepted
        """
        if not name and not description:
            logger.warning("No changes provided for content update")
            return False

        url = f"{self.BASE_URL}/v3/product/import-by-sku"

        # Build item with only the fields we want to update
        item = {"offer_id": offer_id}
        if name:
            item["name"] = name
        if description:
            # Description is attribute_id 4191 in OZON
            item["attributes"] = [
                {
                    "id": 4191,  # Description attribute
                    "values": [{"value": description}]
                }
            ]

        payload = {"items": [item]}

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            result = data.get("result", {})

            # Check for task_id - means update was accepted
            task_id = result.get("task_id")
            if task_id:
                logger.info(f"Content update for {offer_id} accepted, task_id: {task_id}")
                return True

            # Check for errors
            errors = result.get("errors", [])
            if errors:
                logger.error(f"Content update errors: {errors}")
                return False

            return True

        except Exception as e:
            logger.error(f"Failed to update content for {offer_id}: {e}")
            raise

    async def get_product_rating(self, product_ids: list[int]) -> dict[int, dict]:
        """Get product ratings and review counts.

        Args:
            product_ids: List of OZON product IDs

        Returns:
            Dict mapping product_id to rating info
        """
        url = f"{self.BASE_URL}/v1/product/rating-by-sku"
        payload = {"skus": product_ids}

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()

            result = {}
            for item in data.get("products", []):
                sku = item.get("sku")
                if sku:
                    result[sku] = {
                        "rating": item.get("rating", 0),
                        "reviews_count": item.get("reviews_count", 0),
                        "questions_count": item.get("questions_count", 0),
                    }
            return result

        except Exception as e:
            logger.warning(f"Failed to get product ratings: {e}")
            return {}

    async def get_reviews_list(
        self, product_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get list of reviews for a product.

        Note: Requires Premium Plus subscription.

        Args:
            product_id: OZON product ID
            limit: Max reviews to fetch

        Returns:
            List of review objects
        """
        url = f"{self.BASE_URL}/v1/review/list"
        payload = {
            "filter": {"product_id": [product_id]},
            "sort": {"sort_by": "PUBLISHED_AT", "sort_direction": "DESC"},
            "limit": limit,
        }

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            return data.get("reviews", [])

        except Exception as e:
            logger.warning(f"Failed to get reviews (may require Premium): {e}")
            return []

    async def get_questions_list(
        self, product_id: int, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get list of customer questions for a product.

        Args:
            product_id: OZON product ID
            limit: Max questions to fetch

        Returns:
            List of question objects
        """
        url = f"{self.BASE_URL}/v1/product/question/list"
        payload = {
            "filter": {"product_id": product_id, "status": "NEW"},
            "limit": limit,
        }

        try:
            response = await self.client.post(url, json=payload, headers=self._get_headers())
            response.raise_for_status()
            data = response.json()
            return data.get("questions", [])

        except Exception as e:
            logger.warning(f"Failed to get questions: {e}")
            return []

    async def get_product_content_analytics(
        self, sku: int, date_from: date, date_to: date
    ) -> dict[str, Any]:
        """Get content-related analytics for a product.

        NOTE: View metrics (hits_view_pdp, hits_view_search, hits_tocart) are
        DEPRECATED by OZON API as of 2024. Only ordered_units and revenue work.

        Args:
            sku: OZON SKU (not product_id! Get it from product info)
            date_from: Start date
            date_to: End date

        Returns:
            Analytics data dict (views will be 0 - data not available)
        """
        # Views metrics are deprecated by OZON - return zeros
        # Only ordered_units and revenue work now, but we already get
        # those from local database sync
        return {
            "views_search": 0,
            "views_pdp": 0,
            "add_to_cart": 0,
            "cart_conversion": 0,
            "views_unavailable": True,  # Flag to show appropriate message
        }
