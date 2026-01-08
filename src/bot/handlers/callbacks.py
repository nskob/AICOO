"""Telegram bot callback handlers for inline buttons."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from telegram import Update
from telegram.ext import ContextTypes

from src.analytics.pricing import PricingEngine
from src.database.engine import AsyncSessionLocal
from src.database.repositories.experiments import ExperimentRepository
from src.database.repositories.price_recommendations import PriceRecommendationRepository
from src.database.repositories.products import ProductRepository
from src.ozon.client import OzonClient
from src.utils.formatting import format_currency, format_date

logger = logging.getLogger(__name__)


async def handle_approve_price(
    update: Update, context: ContextTypes.DEFAULT_TYPE, recommendation_id: int
) -> None:
    """Handle price recommendation approval."""
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        try:
            rec_repo = PriceRecommendationRepository(session)
            products_repo = ProductRepository(session)
            exp_repo = ExperimentRepository(session)

            # Get recommendation
            recommendation = await rec_repo.get_by_id(recommendation_id)
            if not recommendation:
                await query.edit_message_text("❌ Рекомендация не найдена")
                return

            if recommendation.status != "pending":
                await query.edit_message_text(
                    f"ℹ️ Рекомендация уже обработана (статус: {recommendation.status})"
                )
                return

            # Get product
            product = await products_repo.get_by_product_id(recommendation.product_id)
            if not product:
                await query.edit_message_text("❌ Товар не найден")
                return

            # Update price via OZON
            ozon = OzonClient()
            success = await ozon.update_price(
                product_id=product.product_id,
                price=recommendation.recommended_price,
                old_price=product.price,
            )
            await ozon.close()

            if not success:
                await query.edit_message_text(
                    "❌ Ошибка при обновлении цены в OZON. Проверьте логи."
                )
                await rec_repo.update_status(recommendation_id, "failed")
                await session.commit()
                return

            # Update local product price
            await products_repo.update_price(
                product_id=product.product_id,
                price=recommendation.recommended_price,
                old_price=product.price,
            )

            # Create experiment
            review_date = date.today() + timedelta(days=7)
            await exp_repo.create(
                product_id=product.product_id,
                old_price=recommendation.current_price,
                new_price=recommendation.recommended_price,
                start_date=date.today(),
                review_date=review_date,
                baseline_sales=recommendation.baseline_sales_7d,
                baseline_revenue=recommendation.baseline_revenue_7d,
                recommendation_id=recommendation_id,
            )

            # Mark recommendation as applied
            await rec_repo.mark_applied(recommendation_id)
            await session.commit()

            # Update message
            success_msg = f"""✅ *Цена применена!*

Товар: {product.name}
Новая цена: {format_currency(recommendation.recommended_price)}
Старая цена: {format_currency(recommendation.current_price)}

Эксперимент запущен на 7 дней.
Проверка результатов: {format_date(review_date)}
"""
            await query.edit_message_text(success_msg, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error approving price: {e}")
            await query.edit_message_text("❌ Ошибка при применении цены")


async def handle_reject_price(
    update: Update, context: ContextTypes.DEFAULT_TYPE, recommendation_id: int
) -> None:
    """Handle price recommendation rejection."""
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        try:
            rec_repo = PriceRecommendationRepository(session)

            # Mark as rejected
            await rec_repo.update_status(recommendation_id, "rejected")
            await session.commit()

            await query.edit_message_text("❌ Рекомендация отклонена")

        except Exception as e:
            logger.error(f"Error rejecting price: {e}")
            await query.edit_message_text("❌ Ошибка при отклонении рекомендации")


async def handle_rollback_price(
    update: Update, context: ContextTypes.DEFAULT_TYPE, experiment_id: int
) -> None:
    """Handle price rollback after failed experiment."""
    query = update.callback_query
    await query.answer()

    async with AsyncSessionLocal() as session:
        try:
            exp_repo = ExperimentRepository(session)
            products_repo = ProductRepository(session)

            # Get experiment
            experiment = await exp_repo.get_by_id(experiment_id)
            if not experiment:
                await query.edit_message_text("❌ Эксперимент не найден")
                return

            # Rollback price via OZON
            ozon = OzonClient()
            success = await ozon.update_price(
                product_id=experiment.product_id,
                price=experiment.old_price,
            )
            await ozon.close()

            if not success:
                await query.edit_message_text("❌ Ошибка при откате цены в OZON")
                return

            # Update local product price
            await products_repo.update_price(
                product_id=experiment.product_id,
                price=experiment.old_price,
            )
            await session.commit()

            await query.edit_message_text(
                f"↩️ Цена возвращена к {format_currency(experiment.old_price)}"
            )

        except Exception as e:
            logger.error(f"Error rolling back price: {e}")
            await query.edit_message_text("❌ Ошибка при откате цены")


async def handle_keep_price(
    update: Update, context: ContextTypes.DEFAULT_TYPE, experiment_id: int
) -> None:
    """Handle decision to keep new price after experiment."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text("✓ Новая цена сохранена")


async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main callback query router."""
    query = update.callback_query
    data = query.data

    try:
        if data.startswith("approve_price:"):
            rec_id = int(data.split(":")[1])
            await handle_approve_price(update, context, rec_id)

        elif data.startswith("reject_price:"):
            rec_id = int(data.split(":")[1])
            await handle_reject_price(update, context, rec_id)

        elif data.startswith("rollback_price:"):
            exp_id = int(data.split(":")[1])
            await handle_rollback_price(update, context, exp_id)

        elif data.startswith("keep_price:"):
            exp_id = int(data.split(":")[1])
            await handle_keep_price(update, context, exp_id)

        else:
            await query.answer("Неизвестная команда")

    except Exception as e:
        logger.error(f"Error in callback handler: {e}")
        await query.answer("Произошла ошибка")
