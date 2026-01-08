"""Telegram bot message handlers (AI-powered)."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes

from src.ai.assistant import ClaudeAssistant
from src.ai.prompts import (
    BusinessContext,
    build_experiments_summary,
    build_inventory_summary,
    build_products_summary,
    build_sales_summary,
)
from src.database.engine import AsyncSessionLocal
from src.database.repositories.experiments import ExperimentRepository
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository
from src.utils.formatting import format_currency, format_number

logger = logging.getLogger(__name__)


async def build_business_context_data(session) -> BusinessContext:
    """Build business context from current data."""
    products_repo = ProductRepository(session)
    sales_repo = SalesRepository(session)
    experiments_repo = ExperimentRepository(session)

    # Get products
    products = await products_repo.get_all_active()

    # Get sales summary (last 7 days)
    today_date = date.today()
    last_7d_end = today_date - timedelta(days=1)
    last_7d_start = last_7d_end - timedelta(days=6)

    total_qty, total_revenue = await sales_repo.get_total_for_date(last_7d_start)
    avg_order_value = total_revenue / total_qty if total_qty > 0 else Decimal("0")

    top_products_data = await sales_repo.get_top_products(last_7d_start, last_7d_end, limit=3)
    top_products = []
    for product_id, qty, revenue in top_products_data:
        product = await products_repo.get_by_product_id(product_id)
        if product:
            top_products.append(
                {"name": product.name, "qty": qty, "revenue": revenue}
            )

    sales_data = {
        "total_qty": total_qty,
        "total_revenue": total_revenue,
        "avg_order_value": avg_order_value,
        "top_products": top_products,
    }

    # Get inventory summary
    # Simplified - in production would calculate from InventoryAnalytics
    inventory_data = {
        "total_products": len(products),
        "critical_count": 0,
        "warning_count": 0,
        "avg_days_inventory": 20,
    }

    # Get experiments
    experiments = await experiments_repo.get_active_experiments()

    return BusinessContext(
        today=today_date,
        products_count=len(products),
        products_summary=build_products_summary(products),
        sales_summary=build_sales_summary(sales_data),
        inventory_summary=build_inventory_summary(inventory_data),
        experiments_summary=build_experiments_summary(experiments),
    )


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free-form messages using AI assistant."""
    user_message = update.message.text

    # Ignore commands
    if user_message.startswith("/"):
        return

    async with AsyncSessionLocal() as session:
        try:
            # Build business context
            business_context = await build_business_context_data(session)

            # Ask Claude
            assistant = ClaudeAssistant()
            response = await assistant.ask(user_message, business_context)
            await assistant.close()

            # Send response
            await update.message.reply_text(response, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error in AI message handler: {e}")
            await update.message.reply_text(
                "❌ Извините, произошла ошибка при обработке вашего запроса."
            )
