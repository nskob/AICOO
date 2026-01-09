"""Pydantic models for OZON Seller API responses."""

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from pydantic import BaseModel, Field


class OzonProductShort(BaseModel):
    """Minimal product info from product list endpoint."""

    product_id: int
    offer_id: str


class OzonPrice(BaseModel):
    """Product pricing information."""

    price: str
    old_price: str = "0"
    premium_price: Optional[str] = None
    min_price: Optional[str] = None


class OzonStock(BaseModel):
    """Stock information for a product."""

    present: int
    reserved: int
    warehouse_name: Optional[str] = None
    type: Optional[str] = None  # v4 API uses type (fbo/fbs) instead of warehouse_name


class OzonProductFull(BaseModel):
    """Detailed product information."""

    product_id: int = Field(alias="id")
    offer_id: str
    name: str
    price: str
    old_price: str = "0"
    currency_code: str = "RUB"
    stocks: Optional[Any] = None  # v3 API returns nested structure

    class Config:
        populate_by_name = True


class OzonProductListResponse(BaseModel):
    """Response from /v2/product/list."""

    items: list[OzonProductShort]


class OzonProductInfoResponse(BaseModel):
    """Response from /v2/product/info/list."""

    items: list[OzonProductFull]


class OzonStockItem(BaseModel):
    """Stock item from stocks endpoint."""

    product_id: int
    offer_id: str
    stocks: list[OzonStock]


class OzonStocksResponse(BaseModel):
    """Response from /v1/product/info/stocks."""

    items: list[OzonStockItem]


class OzonAnalyticsData(BaseModel):
    """Analytics data point."""

    dimensions: list[dict[str, Any]]
    metrics: list[float]


class OzonAnalyticsResponse(BaseModel):
    """Response from /v1/analytics/data."""

    result: dict[str, Any]


class OzonPriceUpdate(BaseModel):
    """Price update request item."""

    product_id: int
    price: str
    old_price: str = "0"
    min_price: Optional[str] = None
    auto_action_enabled: str = "DISABLED"
    price_strategy_enabled: str = "DISABLED"


class OzonPriceUpdateResponse(BaseModel):
    """Response from price update endpoint."""

    result: list[dict[str, Any]]
    errors: Optional[list[dict[str, Any]]] = None
