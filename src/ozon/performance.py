"""OZON Performance API client for advertising management."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
import time

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class PerformanceClient:
    """Client for OZON Performance API (advertising) with OAuth2 auth."""

    BASE_URL = "https://api-performance.ozon.ru"

    # Class-level token cache
    _access_token: Optional[str] = None
    _token_expires_at: float = 0

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        """Initialize Performance API client."""
        self.client_id = client_id or settings.ozon_performance_client_id
        self.client_secret = client_secret or settings.ozon_performance_api_key
        self.client = httpx.AsyncClient(timeout=30.0)

        if not self.client_id or not self.client_secret:
            logger.warning("Performance API credentials not configured")

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token, using cache if valid."""
        # Check if cached token is still valid (with 60s buffer)
        if PerformanceClient._access_token and time.time() < PerformanceClient._token_expires_at - 60:
            return PerformanceClient._access_token

        # Request new token
        url = f"{self.BASE_URL}/api/client/token"
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            PerformanceClient._access_token = data["access_token"]
            PerformanceClient._token_expires_at = time.time() + data.get("expires_in", 1800)

            logger.info("Got new Performance API access token")
            return PerformanceClient._access_token

        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            raise

    async def _get_headers(self) -> dict[str, str]:
        """Get authentication headers with Bearer token."""
        token = await self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def is_configured(self) -> bool:
        """Check if Performance API is configured."""
        return bool(self.client_id and self.client_secret)

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()

    async def get_campaigns(
        self,
        campaign_ids: Optional[list[str]] = None,
        state: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get list of advertising campaigns.

        Args:
            campaign_ids: Optional list of specific campaign IDs
            state: Optional filter by state (CAMPAIGN_STATE_RUNNING, CAMPAIGN_STATE_INACTIVE, etc.)

        Returns:
            List of campaign objects
        """
        url = f"{self.BASE_URL}/api/client/campaign"

        params = {}
        if campaign_ids:
            params["campaignIds"] = ",".join(campaign_ids)
        if state:
            params["state"] = state

        try:
            response = await self.client.get(url, params=params, headers=await self._get_headers())
            response.raise_for_status()
            data = response.json()
            campaigns = data.get("list", [])
            logger.info(f"Fetched {len(campaigns)} campaigns")
            return campaigns
        except Exception as e:
            logger.error(f"Failed to fetch campaigns: {e}")
            raise

    async def get_campaign(self, campaign_id: str) -> Optional[dict[str, Any]]:
        """Get single campaign details.

        Args:
            campaign_id: Campaign ID

        Returns:
            Campaign object or None
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}"

        try:
            response = await self.client.get(url, headers=await self._get_headers())
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to fetch campaign {campaign_id}: {e}")
            raise

    async def activate_campaign(self, campaign_id: str) -> bool:
        """Activate (turn on) a campaign.

        Args:
            campaign_id: Campaign ID

        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}/activate"

        try:
            response = await self.client.post(url, headers=await self._get_headers())
            response.raise_for_status()
            logger.info(f"Campaign {campaign_id} activated")
            return True
        except Exception as e:
            logger.error(f"Failed to activate campaign {campaign_id}: {e}")
            raise

    async def deactivate_campaign(self, campaign_id: str) -> bool:
        """Deactivate (turn off) a campaign.

        Args:
            campaign_id: Campaign ID

        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}/deactivate"

        try:
            response = await self.client.post(url, headers=await self._get_headers())
            response.raise_for_status()
            logger.info(f"Campaign {campaign_id} deactivated")
            return True
        except Exception as e:
            logger.error(f"Failed to deactivate campaign {campaign_id}: {e}")
            raise

    async def get_campaign_statistics(
        self,
        campaign_ids: list[str],
        date_from: date,
        date_to: date,
    ) -> dict[str, Any]:
        """Request campaign statistics report.

        Args:
            campaign_ids: List of campaign IDs
            date_from: Start date
            date_to: End date

        Returns:
            Statistics data
        """
        # First, request the report
        url = f"{self.BASE_URL}/api/client/statistics"

        payload = {
            "campaigns": campaign_ids,
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
            "groupBy": "DATE",
        }

        try:
            response = await self.client.post(url, json=payload, headers=await self._get_headers())
            response.raise_for_status()
            data = response.json()

            # The API returns a UUID for async report generation
            report_uuid = data.get("UUID")
            if report_uuid:
                # Poll for report completion
                return await self._wait_for_report(report_uuid)
            else:
                return data

        except Exception as e:
            logger.error(f"Failed to get campaign statistics: {e}")
            raise

    async def _wait_for_report(self, report_uuid: str, max_attempts: int = 10) -> dict[str, Any]:
        """Wait for async report to complete.

        Args:
            report_uuid: Report UUID
            max_attempts: Maximum polling attempts

        Returns:
            Report data
        """
        import asyncio

        url = f"{self.BASE_URL}/api/client/statistics/{report_uuid}"

        for attempt in range(max_attempts):
            try:
                response = await self.client.get(url, headers=await self._get_headers())
                response.raise_for_status()
                data = response.json()

                state = data.get("state")
                if state == "OK":
                    return data
                elif state == "ERROR":
                    raise Exception(f"Report generation failed: {data}")

                # Still processing, wait and retry
                await asyncio.sleep(1)

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Report not ready yet
                    await asyncio.sleep(1)
                else:
                    raise

        raise Exception("Report generation timeout")

    async def get_products_in_campaign(self, campaign_id: str) -> list[dict[str, Any]]:
        """Get list of products in a campaign.

        Args:
            campaign_id: Campaign ID

        Returns:
            List of products with their bids
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}/products"

        try:
            response = await self.client.get(url, headers=await self._get_headers())
            response.raise_for_status()
            data = response.json()
            products = data.get("products", [])
            logger.info(f"Fetched {len(products)} products from campaign {campaign_id}")
            return products
        except Exception as e:
            logger.error(f"Failed to fetch products for campaign {campaign_id}: {e}")
            raise

    async def set_product_bid(
        self,
        campaign_id: str,
        product_id: int,
        bid: Decimal,
    ) -> bool:
        """Set bid for a product in a campaign.

        Args:
            campaign_id: Campaign ID
            product_id: Product ID (SKU)
            bid: Bid amount in rubles

        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}/products/bids"

        payload = {
            "bids": [
                {
                    "productId": product_id,
                    "bid": int(bid * 100_000_000),  # Convert to nanocurrency
                }
            ]
        }

        try:
            response = await self.client.post(url, json=payload, headers=await self._get_headers())
            response.raise_for_status()
            logger.info(f"Set bid {bid} for product {product_id} in campaign {campaign_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set bid: {e}")
            raise

    async def add_products_to_campaign(
        self,
        campaign_id: str,
        product_ids: list[int],
        bid: Decimal,
    ) -> bool:
        """Add products to a campaign with specified bid.

        Args:
            campaign_id: Campaign ID
            product_ids: List of product IDs to add
            bid: Initial bid amount

        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}/products"

        payload = {
            "products": [
                {"productId": pid, "bid": int(bid * 100_000_000)}
                for pid in product_ids
            ]
        }

        try:
            response = await self.client.post(url, json=payload, headers=await self._get_headers())
            response.raise_for_status()
            logger.info(f"Added {len(product_ids)} products to campaign {campaign_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add products to campaign: {e}")
            raise

    async def remove_products_from_campaign(
        self,
        campaign_id: str,
        product_ids: list[int],
    ) -> bool:
        """Remove products from a campaign.

        Args:
            campaign_id: Campaign ID
            product_ids: List of product IDs to remove

        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}/products/delete"

        payload = {"productIds": product_ids}

        try:
            response = await self.client.post(url, json=payload, headers=await self._get_headers())
            response.raise_for_status()
            logger.info(f"Removed {len(product_ids)} products from campaign {campaign_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to remove products from campaign: {e}")
            raise

    async def get_daily_budget(self, campaign_id: str) -> Optional[Decimal]:
        """Get daily budget for a campaign.

        Args:
            campaign_id: Campaign ID

        Returns:
            Daily budget in rubles or None
        """
        campaign = await self.get_campaign(campaign_id)
        if campaign:
            budget = campaign.get("dailyBudget")
            if budget:
                return Decimal(budget) / 100_000_000  # Convert from nanocurrency
        return None

    async def set_daily_budget(self, campaign_id: str, budget: Decimal) -> bool:
        """Set daily budget for a campaign.

        Args:
            campaign_id: Campaign ID
            budget: Daily budget in rubles

        Returns:
            True if successful
        """
        url = f"{self.BASE_URL}/api/client/campaign/{campaign_id}"

        payload = {
            "dailyBudget": int(budget * 100_000_000)  # Convert to nanocurrency
        }

        try:
            response = await self.client.put(url, json=payload, headers=await self._get_headers())
            response.raise_for_status()
            logger.info(f"Set daily budget {budget} for campaign {campaign_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to set daily budget: {e}")
            raise
