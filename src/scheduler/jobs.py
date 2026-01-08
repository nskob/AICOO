"""Scheduled jobs for automated tasks."""

import logging
from datetime import date, timedelta
from decimal import Decimal

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application

from src.analytics.inventory import InventoryAnalytics
from src.analytics.pricing import PricingEngine
from src.analytics.sales import SalesAnalytics
from src.bot.keyboards import get_price_recommendation_keyboard
from src.config import settings
from src.database.engine import AsyncSessionLocal
from src.database.repositories.experiments import ExperimentRepository
from src.database.repositories.price_recommendations import PriceRecommendationRepository
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository
from src.ozon.client import OzonClient
from src.ozon.sync import OzonDataSync
from src.utils.formatting import (
    format_currency,
    format_date,
    format_number,
    format_percent,
    format_urgency_emoji,
    truncate_text,
)

logger = logging.getLogger(__name__)


async def send_telegram_message(app: Application, text: str, parse_mode: str = "Markdown") -> None:
    """Send message to admin chat."""
    try:
        await app.bot.send_message(
            chat_id=settings.telegram_admin_chat_id,
            text=text,
            parse_mode=parse_mode,
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram message: {e}")


async def sync_ozon_data(app: Application) -> None:
    """Sync all data from OZON API."""
    logger.info("Starting OZON data sync job")

    async with AsyncSessionLocal() as session:
        try:
            ozon_client = OzonClient()
            sync = OzonDataSync(ozon_client, session)

            results = await sync.sync_all(sales_days_back=7)

            await ozon_client.close()

            message = f"""✅ *Синхронизация OZON завершена*

Обновлено:
• Товары: {results.get('products', 0)}
• Остатки: {results.get('inventory', 0)}
• Продажи: {results.get('sales', 0)}
"""
            await send_telegram_message(app, message)

            logger.info(f"OZON sync completed: {results}")

        except Exception as e:
            logger.error(f"OZON sync failed: {e}")
            await send_telegram_message(
                app, f"❌ Ошибка синхронизации с OZON:\n{str(e)}"
            )


async def send_daily_report(app: Application) -> None:
    """Send daily sales report."""
    logger.info("Generating daily sales report")

    async with AsyncSessionLocal() as session:
        try:
            sales_analytics = SalesAnalytics(session)
            sales_repo = SalesRepository(session)

            yesterday = date.today() - timedelta(days=1)
            last_7d_end = yesterday
            last_7d_start = last_7d_end - timedelta(days=6)
            prev_7d_end = last_7d_start - timedelta(days=1)
            prev_7d_start = prev_7d_end - timedelta(days=6)

            # Get summaries
            summary = await sales_analytics.get_daily_summary(yesterday)

            # Get weekly comparison
            last_7d_qty, last_7d_revenue = await sales_repo.get_total_for_date(last_7d_start)
            prev_7d_qty, prev_7d_revenue = await sales_repo.get_total_for_date(prev_7d_start)

            qty_trend = (
                ((last_7d_qty - prev_7d_qty) / prev_7d_qty * 100)
                if prev_7d_qty > 0
                else 0.0
            )
            revenue_trend = (
                ((float(last_7d_revenue) - float(prev_7d_revenue)) / float(prev_7d_revenue) * 100)
                if prev_7d_revenue > 0
                else 0.0
            )

            # Get top products
            top_products = await sales_analytics.get_top_products(
                last_7d_start, last_7d_end, limit=5
            )

            # Build report
            report = f"""📊 *Отчёт по продажам за {format_date(yesterday)}*

💰 *Итого:*
• Продано: {format_number(summary.total_qty)} шт
• Выручка: {format_currency(summary.total_revenue)}
• Средний чек: {format_currency(summary.avg_order_value)}

📈 *Сравнение с прошлой неделей:*
• Продажи: {format_percent(qty_trend)} ({format_number(last_7d_qty)} vs {format_number(prev_7d_qty)})
• Выручка: {format_percent(revenue_trend)}

🏆 *ТОП-5 товаров (за 7 дней):*
"""

            for i, product in enumerate(top_products, 1):
                report += f"{i}. {truncate_text(product.product_name, 35)} — {format_number(product.quantity)} шт ({format_currency(product.revenue)})\n"

            await send_telegram_message(app, report)

            logger.info("Daily report sent successfully")

        except Exception as e:
            logger.error(f"Failed to generate daily report: {e}")
            await send_telegram_message(app, f"❌ Ошибка генерации отчёта:\n{str(e)}")


async def run_price_analysis(app: Application) -> None:
    """Run price optimization analysis and send recommendations."""
    logger.info("Running price analysis job")

    async with AsyncSessionLocal() as session:
        try:
            pricing_engine = PricingEngine(session)
            rec_repo = PriceRecommendationRepository(session)
            products_repo = ProductRepository(session)

            # Generate recommendations
            recommendations = await pricing_engine.generate_all_recommendations()

            if not recommendations:
                logger.info("No price recommendations generated")
                return

            # Save and send each recommendation
            for rec in recommendations:
                # Generate unique change ID
                change_id = f"PR-{date.today().strftime('%Y%m%d')}-{rec.offer_id}"

                # Save to database
                db_rec = await rec_repo.create(
                    change_id=change_id,
                    product_id=rec.product_id,
                    current_price=rec.current_price,
                    recommended_price=rec.recommended_price,
                    change_pct=rec.change_pct,
                    direction=rec.direction,
                    factors={"factors": rec.factors},
                    score_up=rec.score_up,
                    score_down=rec.score_down,
                    baseline_sales_7d=rec.baseline_sales_7d,
                    baseline_revenue_7d=rec.baseline_revenue_7d,
                )
                await session.commit()

                # Build message
                direction_emoji = "📈" if rec.direction == "UP" else "📉"
                factors_text = "\n".join(f"• {f}" for f in rec.factors)

                message = f"""{direction_emoji} *Рекомендация по цене*

*Товар:* {truncate_text(rec.product_name, 40)}
*Текущая цена:* {format_currency(rec.current_price)}
*Рекомендация:* {format_currency(rec.recommended_price)} ({format_percent(float(rec.change_pct))})

*Причины:*
{factors_text}

*Базовые показатели (7 дней):*
• Продажи: {format_number(rec.baseline_sales_7d)} шт
• Выручка: {format_currency(rec.baseline_revenue_7d)}
"""

                # Send with inline keyboard
                keyboard = get_price_recommendation_keyboard(db_rec.id)
                try:
                    sent_message = await app.bot.send_message(
                        chat_id=settings.telegram_admin_chat_id,
                        text=message,
                        parse_mode="Markdown",
                        reply_markup=keyboard,
                    )

                    # Save message ID
                    await rec_repo.update_status(
                        db_rec.id, "pending", telegram_message_id=sent_message.message_id
                    )
                    await session.commit()

                except Exception as e:
                    logger.error(f"Failed to send price recommendation: {e}")

            logger.info(f"Price analysis completed: {len(recommendations)} recommendations sent")

        except Exception as e:
            logger.error(f"Price analysis failed: {e}")


async def review_experiments(app: Application) -> None:
    """Review completed price experiments and send results."""
    logger.info("Reviewing price experiments")

    async with AsyncSessionLocal() as session:
        try:
            exp_repo = ExperimentRepository(session)
            products_repo = ProductRepository(session)
            sales_repo = SalesRepository(session)

            today = date.today()
            experiments = await exp_repo.get_experiments_for_review(today)

            for exp in experiments:
                product = await products_repo.get_by_product_id(exp.product_id)
                if not product:
                    continue

                # Get results
                result_start = exp.start_date
                result_end = today - timedelta(days=1)
                result_sales, result_revenue = await sales_repo.get_total_sales_for_period(
                    exp.product_id, result_start, result_end
                )

                # Calculate changes
                baseline_sales = exp.baseline_sales or 0
                baseline_revenue = exp.baseline_revenue or Decimal("0")

                sales_change_pct = (
                    ((result_sales - baseline_sales) / baseline_sales * 100)
                    if baseline_sales > 0
                    else 0.0
                )
                revenue_change_pct = (
                    ((float(result_revenue) - float(baseline_revenue)) / float(baseline_revenue) * 100)
                    if baseline_revenue > 0
                    else 0.0
                )

                # Calculate profit change (simplified)
                profit_change_pct = revenue_change_pct  # Simplified

                # Determine verdict
                if profit_change_pct >= 10:
                    verdict = "SUCCESS"
                    verdict_emoji = "✅"
                elif profit_change_pct <= -10:
                    verdict = "FAILED"
                    verdict_emoji = "❌"
                else:
                    verdict = "NEUTRAL"
                    verdict_emoji = "➖"

                # Complete experiment
                await exp_repo.complete_experiment(
                    experiment_id=exp.id,
                    result_sales=result_sales,
                    result_revenue=result_revenue,
                    sales_change_pct=Decimal(str(sales_change_pct)),
                    revenue_change_pct=Decimal(str(revenue_change_pct)),
                    profit_change_pct=Decimal(str(profit_change_pct)),
                    verdict=verdict,
                )
                await session.commit()

                # Send report
                message = f"""{verdict_emoji} *Результаты эксперимента*

*Товар:* {truncate_text(product.name, 40)}
*Изменение цены:* {format_currency(exp.old_price)} → {format_currency(exp.new_price)}

*Результаты:*
• Продажи: {format_number(result_sales)} шт (было {format_number(baseline_sales)}, {format_percent(sales_change_pct)})
• Выручка: {format_currency(result_revenue)} (было {format_currency(baseline_revenue)}, {format_percent(revenue_change_pct)})

*Вердикт:* {verdict}
"""

                if verdict == "FAILED":
                    message += "\n💡 Рекомендуется вернуть прежнюю цену."

                await send_telegram_message(app, message)

            logger.info(f"Reviewed {len(experiments)} experiments")

        except Exception as e:
            logger.error(f"Experiment review failed: {e}")


async def send_stock_alerts(app: Application) -> None:
    """Send evening inventory status alerts."""
    logger.info("Generating stock alerts")

    async with AsyncSessionLocal() as session:
        try:
            inventory_analytics = InventoryAnalytics(session)

            # Get low stock products
            critical = await inventory_analytics.get_low_stock_products(urgency_filter="critical")
            warning = await inventory_analytics.get_low_stock_products(urgency_filter="warning")

            if not critical and not warning:
                logger.info("No stock alerts needed")
                return

            report = f"📦 *Статус остатков на {format_date(date.today())}*\n\n"

            if critical:
                report += "🔴 *КРИТИЧНО (< 7 дней):*\n"
                for forecast in critical[:5]:
                    report += f"• {truncate_text(forecast.product_name, 35)}\n"
                    report += f"  └ Осталось: {forecast.current_stock} шт (~{forecast.days_remaining:.0f} дней)\n"
                    report += f"  └ 💡 Заказать: {forecast.reorder_qty} шт\n\n"

            if warning:
                report += "🟡 *ВНИМАНИЕ (7-14 дней):*\n"
                for forecast in warning[:5]:
                    report += f"• {truncate_text(forecast.product_name, 35)}\n"
                    report += f"  └ Осталось: {forecast.current_stock} шт (~{forecast.days_remaining:.0f} дней)\n\n"

            await send_telegram_message(app, report)

            logger.info("Stock alerts sent successfully")

        except Exception as e:
            logger.error(f"Failed to send stock alerts: {e}")


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    """Set up and configure the job scheduler.

    Jobs:
    - 06:00: Sync OZON data
    - 09:00: Send daily report
    - 09:30: Run price analysis
    - 10:00: Review experiments
    - 18:00: Send stock alerts
    """
    scheduler = AsyncIOScheduler(timezone=settings.timezone)

    # Pass app to all jobs via kwargs
    scheduler.add_job(
        sync_ozon_data,
        "cron",
        hour=6,
        minute=0,
        kwargs={"app": app},
        id="sync_ozon_data",
    )

    scheduler.add_job(
        send_daily_report,
        "cron",
        hour=9,
        minute=0,
        kwargs={"app": app},
        id="send_daily_report",
    )

    scheduler.add_job(
        run_price_analysis,
        "cron",
        hour=9,
        minute=30,
        kwargs={"app": app},
        id="run_price_analysis",
    )

    scheduler.add_job(
        review_experiments,
        "cron",
        hour=10,
        minute=0,
        kwargs={"app": app},
        id="review_experiments",
    )

    scheduler.add_job(
        send_stock_alerts,
        "cron",
        hour=18,
        minute=0,
        kwargs={"app": app},
        id="send_stock_alerts",
    )

    logger.info("Scheduler configured with 5 jobs")

    return scheduler
