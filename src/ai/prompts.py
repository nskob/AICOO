"""System prompts and context builders for AI assistant."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Optional

from src.utils.formatting import format_currency, format_number


@dataclass
class BusinessContext:
    """Business data context for AI assistant."""

    today: date
    products_count: int
    products_summary: str
    sales_summary: str
    inventory_summary: str
    experiments_summary: str


def build_products_summary(products: list) -> str:
    """Build summary text for products."""
    if not products:
        return "Нет товаров"

    lines = []
    for p in products[:10]:  # First 10 products
        margin = (
            ((p.price - p.cost_price) / p.price * 100) if p.cost_price > 0 and p.price > 0 else 0
        )
        lines.append(
            f"• {p.name} ({p.offer_id}): {format_currency(p.price)} "
            f"(маржа: {margin:.1f}%)"
        )

    if len(products) > 10:
        lines.append(f"... и ещё {len(products) - 10} товаров")

    return "\n".join(lines)


def build_sales_summary(sales_data: dict) -> str:
    """Build summary text for recent sales."""
    if not sales_data:
        return "Нет данных о продажах"

    lines = [
        f"Всего продано (7 дней): {format_number(sales_data.get('total_qty', 0))} шт",
        f"Выручка: {format_currency(sales_data.get('total_revenue', Decimal('0')))}",
        f"Средний чек: {format_currency(sales_data.get('avg_order_value', Decimal('0')))}",
    ]

    if "top_products" in sales_data:
        lines.append("\nТоп-3 товара:")
        for i, product in enumerate(sales_data["top_products"][:3], 1):
            lines.append(
                f"{i}. {product['name']}: {format_number(product['qty'])} шт "
                f"({format_currency(product['revenue'])})"
            )

    return "\n".join(lines)


def build_inventory_summary(inventory_data: dict) -> str:
    """Build summary text for inventory status."""
    if not inventory_data:
        return "Нет данных об остатках"

    lines = [
        f"Всего товаров: {inventory_data.get('total_products', 0)}",
        f"Критичный запас: {inventory_data.get('critical_count', 0)} товаров",
        f"Требуют внимания: {inventory_data.get('warning_count', 0)} товаров",
        f"Средний запас: {inventory_data.get('avg_days_inventory', 0):.0f} дней",
    ]

    return "\n".join(lines)


def build_experiments_summary(experiments: list) -> str:
    """Build summary text for active experiments."""
    if not experiments:
        return "Нет активных экспериментов"

    lines = [f"Активных экспериментов: {len(experiments)}"]

    for exp in experiments[:5]:  # First 5
        lines.append(
            f"• Товар #{exp.product_id}: {format_currency(exp.old_price)} → "
            f"{format_currency(exp.new_price)} (до {exp.review_date})"
        )

    if len(experiments) > 5:
        lines.append(f"... и ещё {len(experiments) - 5}")

    return "\n".join(lines)


def build_system_prompt(context: BusinessContext) -> str:
    """Build complete system prompt with business context."""
    return f"""Ты AI-ассистент для управления бизнесом на маркетплейсе OZON.
Твоя задача — помогать владельцу анализировать данные, отвечать на вопросы и давать рекомендации.

ТЕКУЩАЯ ДАТА: {context.today.strftime('%d.%m.%Y')}

ТЕКУЩИЕ ДАННЫЕ:

📦 ТОВАРЫ ({context.products_count} шт):
{context.products_summary}

📈 ПРОДАЖИ (последние 7 дней):
{context.sales_summary}

📊 ОСТАТКИ:
{context.inventory_summary}

🧪 АКТИВНЫЕ ЭКСПЕРИМЕНТЫ:
{context.experiments_summary}

ИНСТРУМЕНТЫ:
У тебя есть доступ к инструментам для работы с Ozon API:

📊 Аналитика и товары:
- get_sales_analytics: запросить продажи за любой период
- get_current_stocks: получить текущие остатки на складах
- get_product_list: получить список товаров с ценами

📢 Управление рекламой (Performance API):
- get_ad_campaigns: список рекламных кампаний
- get_campaign_stats: статистика кампании (показы, клики, расходы, заказы)
- get_campaign_products: товары в кампании с их ставками
- activate_ad_campaign: ВКЛЮЧИТЬ кампанию
- deactivate_ad_campaign: ВЫКЛЮЧИТЬ кампанию
- set_product_ad_bid: изменить ставку на товар

КОГДА ИСПОЛЬЗОВАТЬ ИНСТРУМЕНТЫ:
- Продажи за конкретные даты/периоды — get_sales_analytics
- Сравнение периодов — сделай ДВА вызова get_sales_analytics
- Вопросы о рекламе, кампаниях, продвижении — get_ad_campaigns
- Статистика рекламы — get_campaign_stats

ВАЖНЫЕ ПРАВИЛА:
1. Ozon API без Premium даёт аналитику только за последние 3 месяца
2. Перед включением/выключением рекламы или изменением ставок — ОБЯЗАТЕЛЬНО спроси подтверждение у пользователя!
3. Данные выше (ТЕКУЩИЕ ДАННЫЕ) — кэш за 7 дней, для точных данных используй инструменты

ИНСТРУКЦИИ:
- Отвечай конкретно, с цифрами из предоставленных данных
- Используй Markdown для форматирования (жирный, курсив, списки)
- Если нужны расчёты — делай их самостоятельно
- Предлагай actionable рекомендации на основе данных
- Будь кратким, но информативным (2-5 предложений обычно достаточно)
- Отвечай на русском языке
- Используй эмодзи для наглядности (но умеренно)
- Если данных недостаточно для ответа, честно скажи об этом

Примеры хороших ответов:
- "За последние 7 дней лидер продаж — Товар X с 34 единицами. Остаток 45 шт (~9 дней). Рекомендую следить за запасами."
- "Нашёл 3 товара с маржой ниже 15%: [список]. Рекомендую повысить цены или найти других поставщиков."
- "Нужно срочно заказать 2 товара (запас < 7 дней): Товар A — 150 шт, Товар B — 80 шт."
"""
