"""Telegram bot command handlers."""

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
from src.analytics.inventory import InventoryAnalytics
from src.analytics.sales import SalesAnalytics
from src.database.engine import AsyncSessionLocal
from src.database.repositories.experiments import ExperimentRepository
from src.database.repositories.products import ProductRepository
from src.database.repositories.sales import SalesRepository
from src.utils.formatting import (
    format_currency,
    format_date,
    format_number,
    format_percent,
    format_trend_emoji,
    format_urgency_emoji,
    truncate_text,
)

logger = logging.getLogger(__name__)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    welcome_text = """👋 Добро пожаловать в OZON BI систему!

Я помогу вам управлять бизнесом на OZON:

📊 *Команды:*
/report — Отчёт по продажам за вчера
/inventory — Статус остатков
/help — Справка по командам

💬 *AI-ассистент:*
Просто напишите вопрос, и я отвечу на основе ваших данных.

Примеры:
• Какой товар лучше всего продаётся?
• Покажи товары с маржой ниже 15%
• Что нужно заказать у поставщика?
"""
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = """📖 *Справка по командам*

*Основные команды:*
/start — Приветствие и краткая справка
/help — Эта справка
/report — Отчёт по продажам за вчера
/inventory — Статус остатков и рекомендации по заказу
/experiments — Активные ценовые эксперименты

*AI-ассистент:*
Вы можете задавать вопросы обычным языком, например:
• Какие товары нужно срочно заказать?
• Покажи топ-5 товаров по выручке
• Какая средняя маржа по всем товарам?
• Есть ли товары без продаж за месяц?

Система автоматически:
• Синхронизирует данные с OZON каждый день в 6:00
• Отправляет утренний отчёт в 9:00
• Анализирует цены и предлагает изменения в 9:30
• Проверяет эксперименты в 10:00
• Отправляет статус остатков вечером в 18:00
"""
    await update.message.reply_text(help_text, parse_mode="Markdown")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /report command - daily sales report."""
    async with AsyncSessionLocal() as session:
        try:
            sales_analytics = SalesAnalytics(session)
            products_repo = ProductRepository(session)
            sales_repo = SalesRepository(session)

            yesterday = date.today() - timedelta(days=1)
            last_7d_end = yesterday
            last_7d_start = last_7d_end - timedelta(days=6)
            prev_7d_end = last_7d_start - timedelta(days=1)
            prev_7d_start = prev_7d_end - timedelta(days=6)

            # Get daily summary
            summary = await sales_analytics.get_daily_summary(yesterday)

            # Get weekly totals
            last_7d_qty, last_7d_revenue = await sales_repo.get_total_for_date(last_7d_start)
            # Simplified: just get yesterday for comparison
            # In production, should calculate full week totals

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
• Товаров продано: {summary.products_sold}

🏆 *ТОП-5 товаров (за 7 дней):*
"""

            for i, product in enumerate(top_products, 1):
                report += f"{i}. {truncate_text(product.product_name, 40)} — {format_number(product.quantity)} шт ({format_currency(product.revenue)})\n"

            await update.message.reply_text(report, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error generating report: {e}")
            await update.message.reply_text(
                "❌ Ошибка при формировании отчёта. Проверьте логи."
            )


async def inventory_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /inventory command - stock status and alerts."""
    async with AsyncSessionLocal() as session:
        try:
            inventory_analytics = InventoryAnalytics(session)
            today_date = date.today()

            # Get low stock products
            critical = await inventory_analytics.get_low_stock_products(urgency_filter="critical")
            warning = await inventory_analytics.get_low_stock_products(urgency_filter="warning")

            # Get summary
            summary = await inventory_analytics.get_inventory_summary()

            report = f"""📦 *Статус остатков на {format_date(today_date)}*

"""

            if critical:
                report += "🔴 *КРИТИЧНО (< 7 дней запаса):*\n"
                for forecast in critical[:5]:
                    report += f"• {truncate_text(forecast.product_name, 35)}: {forecast.current_stock} шт\n"
                    report += f"  └ Продажи: ~{forecast.avg_daily_sales:.1f}/день → хватит на {forecast.days_remaining:.0f} дней\n"
                    report += f"  └ 💡 Заказать: {forecast.reorder_qty} шт\n\n"

            if warning:
                report += "🟡 *ВНИМАНИЕ (7-14 дней):*\n"
                for forecast in warning[:5]:
                    report += f"• {truncate_text(forecast.product_name, 35)}: {forecast.current_stock} шт\n"
                    report += f"  └ Продажи: ~{forecast.avg_daily_sales:.1f}/день → хватит на {forecast.days_remaining:.0f} дней\n\n"

            if not critical and not warning:
                report += "🟢 Все товары в норме\n\n"

            report += f"""📊 *Общая статистика:*
• Всего товаров: {summary['total_products']}
• Критичный запас: {summary['critical_count']}
• Требуют внимания: {summary['warning_count']}
• Средний запас: ~{summary['avg_days_inventory']:.0f} дней
"""

            await update.message.reply_text(report, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error generating inventory report: {e}")
            await update.message.reply_text(
                "❌ Ошибка при формировании отчёта по остаткам."
            )


async def experiments_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /experiments command - show active price experiments."""
    async with AsyncSessionLocal() as session:
        try:
            experiments_repo = ExperimentRepository(session)
            products_repo = ProductRepository(session)

            active = await experiments_repo.get_active_experiments()

            if not active:
                await update.message.reply_text("🧪 Нет активных ценовых экспериментов")
                return

            report = f"🧪 *Активные эксперименты ({len(active)}):*\n\n"

            for exp in active:
                product = await products_repo.get_by_product_id(exp.product_id)
                if not product:
                    continue

                days_left = (exp.review_date - date.today()).days
                change_pct = (
                    (exp.new_price - exp.old_price) / exp.old_price * 100
                )

                report += f"• *{truncate_text(product.name, 35)}*\n"
                report += f"  Цена: {format_currency(exp.old_price)} → {format_currency(exp.new_price)} ({format_percent(float(change_pct))})\n"
                report += f"  Осталось дней: {days_left}\n"
                report += f"  Проверка: {format_date(exp.review_date)}\n\n"

            await update.message.reply_text(report, parse_mode="Markdown")

        except Exception as e:
            logger.error(f"Error getting experiments: {e}")
            await update.message.reply_text(
                "❌ Ошибка при получении списка экспериментов."
            )
