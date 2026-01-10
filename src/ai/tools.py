"""Tools for Claude AI assistant to query Ozon data."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from src.ozon.client import OzonClient
from src.ozon.performance import PerformanceClient
from src.database.engine import AsyncSessionLocal
from src.database.repositories.ad_experiments import AdExperimentRepository

logger = logging.getLogger(__name__)

# Tool definitions for Claude
TOOLS = [
    {
        "name": "get_sales_analytics",
        "description": "Получить данные о продажах с Ozon за указанный период. Используй этот инструмент когда пользователь спрашивает о продажах, выручке, количестве заказов за конкретные даты или периоды (например, 'продажи за январь 2025', 'сравни продажи в декабре и ноябре').",
        "input_schema": {
            "type": "object",
            "properties": {
                "date_from": {
                    "type": "string",
                    "description": "Начальная дата периода в формате YYYY-MM-DD (например, 2025-01-01)"
                },
                "date_to": {
                    "type": "string",
                    "description": "Конечная дата периода в формате YYYY-MM-DD (например, 2025-01-31)"
                }
            },
            "required": ["date_from", "date_to"]
        }
    },
    {
        "name": "get_current_stocks",
        "description": "Получить текущие остатки товаров на складах Ozon. Используй когда пользователь спрашивает о текущих остатках, запасах, наличии товаров.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_product_list",
        "description": "Получить список всех товаров продавца с ценами. Используй когда пользователь спрашивает о товарах, ценах, ассортименте.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    # Advertising tools (Performance API)
    {
        "name": "get_ad_campaigns",
        "description": "Получить список рекламных кампаний. Используй когда пользователь спрашивает о рекламе, кампаниях, продвижении товаров.",
        "input_schema": {
            "type": "object",
            "properties": {
                "state": {
                    "type": "string",
                    "description": "Фильтр по статусу: CAMPAIGN_STATE_RUNNING (активные), CAMPAIGN_STATE_INACTIVE (неактивные), CAMPAIGN_STATE_ARCHIVED (архивные). Если не указан - все кампании.",
                    "enum": ["CAMPAIGN_STATE_RUNNING", "CAMPAIGN_STATE_INACTIVE", "CAMPAIGN_STATE_ARCHIVED"]
                }
            },
            "required": []
        }
    },
    {
        "name": "get_campaign_stats",
        "description": "Получить статистику рекламной кампании за период: показы, клики, расходы, заказы. Используй когда нужна аналитика по рекламе.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "ID рекламной кампании"
                },
                "date_from": {
                    "type": "string",
                    "description": "Начальная дата в формате YYYY-MM-DD"
                },
                "date_to": {
                    "type": "string",
                    "description": "Конечная дата в формате YYYY-MM-DD"
                }
            },
            "required": ["campaign_id", "date_from", "date_to"]
        }
    },
    {
        "name": "activate_ad_campaign",
        "description": "Включить (активировать) рекламную кампанию. ВАЖНО: используй только после подтверждения пользователя!",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "ID рекламной кампании для активации"
                }
            },
            "required": ["campaign_id"]
        }
    },
    {
        "name": "deactivate_ad_campaign",
        "description": "Выключить (деактивировать) рекламную кампанию. ВАЖНО: используй только после подтверждения пользователя!",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "ID рекламной кампании для деактивации"
                }
            },
            "required": ["campaign_id"]
        }
    },
    {
        "name": "set_product_ad_bid",
        "description": "Установить ставку на товар в рекламной кампании. ВАЖНО: используй только после подтверждения пользователя!",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "ID рекламной кампании"
                },
                "product_id": {
                    "type": "integer",
                    "description": "ID товара (SKU)"
                },
                "bid": {
                    "type": "number",
                    "description": "Ставка в рублях (например, 15.5)"
                }
            },
            "required": ["campaign_id", "product_id", "bid"]
        }
    },
    {
        "name": "get_campaign_products",
        "description": "Получить список товаров в рекламной кампании с их ставками.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "ID рекламной кампании"
                }
            },
            "required": ["campaign_id"]
        }
    },
    # Ad experiment tools
    {
        "name": "start_ad_experiment",
        "description": "Запустить рекламный эксперимент с отслеживанием результатов. Используй после того как пользователь подтвердил запуск рекламы. Эксперимент будет отслеживаться указанное количество дней.",
        "input_schema": {
            "type": "object",
            "properties": {
                "campaign_id": {
                    "type": "string",
                    "description": "ID рекламной кампании"
                },
                "action": {
                    "type": "string",
                    "description": "Действие: activate (включить), deactivate (выключить), change_bid (изменить ставку)",
                    "enum": ["activate", "deactivate", "change_bid"]
                },
                "duration_days": {
                    "type": "integer",
                    "description": "Количество дней для эксперимента (по умолчанию 7)",
                    "default": 7
                },
                "new_bid": {
                    "type": "number",
                    "description": "Новая ставка в рублях (только для action=change_bid)"
                },
                "product_id": {
                    "type": "integer",
                    "description": "ID товара (если эксперимент для конкретного товара)"
                }
            },
            "required": ["campaign_id", "action"]
        }
    },
    {
        "name": "get_active_ad_experiments",
        "description": "Получить список активных рекламных экспериментов. Показывает какие эксперименты сейчас идут и когда их нужно проверить.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "check_ad_experiment",
        "description": "Проверить результаты рекламного эксперимента и получить рекомендацию. Используй когда пришло время оценить эксперимент.",
        "input_schema": {
            "type": "object",
            "properties": {
                "experiment_id": {
                    "type": "integer",
                    "description": "ID эксперимента для проверки"
                }
            },
            "required": ["experiment_id"]
        }
    },
    {
        "name": "complete_ad_experiment",
        "description": "Завершить эксперимент с вердиктом. Используй после того как пользователь принял решение по результатам эксперимента.",
        "input_schema": {
            "type": "object",
            "properties": {
                "experiment_id": {
                    "type": "integer",
                    "description": "ID эксперимента"
                },
                "verdict": {
                    "type": "string",
                    "description": "Вердикт: SUCCESS (успешно, оставляем), FAILED (неудачно, откатываем), NEUTRAL (нейтрально)",
                    "enum": ["SUCCESS", "FAILED", "NEUTRAL"]
                },
                "recommendation": {
                    "type": "string",
                    "description": "Рекомендация на будущее"
                }
            },
            "required": ["experiment_id", "verdict"]
        }
    }
]


async def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        String result to send back to Claude
    """
    logger.info(f"Executing tool: {tool_name} with input: {tool_input}")

    try:
        # Seller API tools
        if tool_name == "get_sales_analytics":
            return await _get_sales_analytics(tool_input)
        elif tool_name == "get_current_stocks":
            return await _get_current_stocks()
        elif tool_name == "get_product_list":
            return await _get_product_list()
        # Performance API tools (advertising)
        elif tool_name == "get_ad_campaigns":
            return await _get_ad_campaigns(tool_input)
        elif tool_name == "get_campaign_stats":
            return await _get_campaign_stats(tool_input)
        elif tool_name == "activate_ad_campaign":
            return await _activate_ad_campaign(tool_input)
        elif tool_name == "deactivate_ad_campaign":
            return await _deactivate_ad_campaign(tool_input)
        elif tool_name == "set_product_ad_bid":
            return await _set_product_ad_bid(tool_input)
        elif tool_name == "get_campaign_products":
            return await _get_campaign_products(tool_input)
        # Ad experiment tools
        elif tool_name == "start_ad_experiment":
            return await _start_ad_experiment(tool_input)
        elif tool_name == "get_active_ad_experiments":
            return await _get_active_ad_experiments()
        elif tool_name == "check_ad_experiment":
            return await _check_ad_experiment(tool_input)
        elif tool_name == "complete_ad_experiment":
            return await _complete_ad_experiment(tool_input)
        else:
            return f"Неизвестный инструмент: {tool_name}"
    except Exception as e:
        logger.error(f"Tool execution error: {e}")
        return f"Ошибка при выполнении запроса: {str(e)}"


async def _get_sales_analytics(params: dict) -> str:
    """Get sales analytics from Ozon API."""
    date_from_str = params.get("date_from")
    date_to_str = params.get("date_to")

    try:
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    except (ValueError, TypeError) as e:
        return f"Некорректный формат даты. Используй YYYY-MM-DD. Ошибка: {e}"

    # Validate date range
    if date_from > date_to:
        return "Начальная дата должна быть раньше конечной"

    if date_to > date.today():
        date_to = date.today()

    client = OzonClient()
    try:
        try:
            analytics = await client.get_analytics_data(
                date_from=date_from,
                date_to=date_to,
                metrics=["ordered_units", "revenue"],
                dimension=["sku", "day"],
            )
        except Exception as api_error:
            error_msg = str(api_error)
            if "400" in error_msg:
                return (
                    f"Нет данных за период {date_from_str} - {date_to_str}. "
                    f"Ограничение Ozon API: без Premium подписки аналитика доступна только за последние 3 месяца. "
                    f"Попробуй запросить данные за более поздний период."
                )
            raise

        data = analytics.get("data", [])
        totals = analytics.get("totals", [0, 0])

        if not data:
            return f"Нет данных о продажах за период {date_from_str} - {date_to_str}"

        # Aggregate by product
        product_sales = {}
        daily_totals = {}

        for row in data:
            dimensions = row.get("dimensions", [])
            metrics = row.get("metrics", [])

            if len(dimensions) >= 2 and len(metrics) >= 2:
                product_name = dimensions[0].get("name", "Неизвестный товар")
                sale_date = dimensions[1].get("id", "")
                qty = int(metrics[0]) if metrics[0] else 0
                revenue = float(metrics[1]) if metrics[1] else 0

                # Aggregate by product
                if product_name not in product_sales:
                    product_sales[product_name] = {"qty": 0, "revenue": 0}
                product_sales[product_name]["qty"] += qty
                product_sales[product_name]["revenue"] += revenue

                # Aggregate by day
                if sale_date not in daily_totals:
                    daily_totals[sale_date] = {"qty": 0, "revenue": 0}
                daily_totals[sale_date]["qty"] += qty
                daily_totals[sale_date]["revenue"] += revenue

        # Build response
        total_qty = totals[0] if len(totals) > 0 else 0
        total_revenue = totals[1] if len(totals) > 1 else 0

        result = f"📊 ПРОДАЖИ ЗА ПЕРИОД {date_from_str} - {date_to_str}:\n\n"
        result += f"Всего продано: {total_qty} шт\n"
        result += f"Общая выручка: {total_revenue:,.0f} ₽\n"
        result += f"Дней в периоде: {(date_to - date_from).days + 1}\n"

        if total_qty > 0:
            result += f"Средний чек: {total_revenue / total_qty:,.0f} ₽\n"

        # Top products
        sorted_products = sorted(
            product_sales.items(),
            key=lambda x: x[1]["revenue"],
            reverse=True
        )

        if sorted_products:
            result += f"\n📦 ПРОДАЖИ ПО ТОВАРАМ:\n"
            for name, stats in sorted_products[:10]:
                short_name = name[:50] + "..." if len(name) > 50 else name
                result += f"• {short_name}: {stats['qty']} шт, {stats['revenue']:,.0f} ₽\n"

        # Daily breakdown (last 7 days only to keep response short)
        sorted_days = sorted(daily_totals.items(), reverse=True)[:7]
        if sorted_days:
            result += f"\n📅 ПО ДНЯМ (последние 7):\n"
            for day, stats in sorted_days:
                result += f"• {day}: {stats['qty']} шт, {stats['revenue']:,.0f} ₽\n"

        return result

    finally:
        await client.close()


async def _get_current_stocks() -> str:
    """Get current stock levels from Ozon API."""
    client = OzonClient()
    try:
        stocks = await client.get_stocks()

        if not stocks:
            return "Нет данных об остатках"

        result = "📦 ТЕКУЩИЕ ОСТАТКИ НА СКЛАДАХ:\n\n"

        total_items = 0
        for item in stocks:
            if not item.stocks:
                continue

            for stock in item.stocks:
                warehouse = stock.warehouse_name or stock.type or "FBO"
                present = stock.present
                reserved = stock.reserved
                available = present - reserved

                total_items += present

                result += f"• Товар {item.offer_id} ({warehouse}):\n"
                result += f"  На складе: {present} шт, Резерв: {reserved} шт, Доступно: {available} шт\n"

        result += f"\nВсего на складах: {total_items} шт"

        return result

    finally:
        await client.close()


async def _get_product_list() -> str:
    """Get product list with prices from Ozon API."""
    client = OzonClient()
    try:
        products = await client.get_product_list()

        if not products:
            return "Нет товаров"

        # Get detailed info
        product_ids = [p.product_id for p in products]
        details = await client.get_product_info(product_ids)

        result = f"📋 СПИСОК ТОВАРОВ ({len(details)} шт):\n\n"

        for p in details:
            short_name = p.name[:50] + "..." if len(p.name) > 50 else p.name
            result += f"• {short_name}\n"
            result += f"  Артикул: {p.offer_id}\n"
            result += f"  Цена: {p.price} ₽"
            if p.old_price and p.old_price != "0":
                result += f" (старая: {p.old_price} ₽)"
            result += "\n\n"

        return result

    finally:
        await client.close()


# ============== ADVERTISING TOOLS (Performance API) ==============

def _check_performance_api() -> tuple[bool, str]:
    """Check if Performance API is configured."""
    client = PerformanceClient()
    if not client.is_configured():
        return False, (
            "⚠️ Performance API не настроен. "
            "Добавь OZON_PERFORMANCE_CLIENT_ID и OZON_PERFORMANCE_API_KEY в .env файл."
        )
    return True, ""


async def _get_ad_campaigns(params: dict) -> str:
    """Get list of advertising campaigns."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    state = params.get("state")

    client = PerformanceClient()
    try:
        campaigns = await client.get_campaigns(state=state)

        if not campaigns:
            return "📢 Рекламных кампаний не найдено"

        result = f"📢 РЕКЛАМНЫЕ КАМПАНИИ ({len(campaigns)} шт):\n\n"

        for c in campaigns:
            status_emoji = "🟢" if c.get("state") == "CAMPAIGN_STATE_RUNNING" else "🔴"
            campaign_type = c.get("advObjectType", "Unknown")

            result += f"{status_emoji} **{c.get('title', 'Без названия')}**\n"
            result += f"   ID: `{c.get('id')}`\n"
            result += f"   Тип: {campaign_type}\n"
            result += f"   Статус: {c.get('state', 'Unknown')}\n"

            daily_budget = c.get("dailyBudget")
            if daily_budget:
                budget_rub = int(daily_budget) / 100_000_000
                result += f"   Дневной бюджет: {budget_rub:,.0f} ₽\n"

            date_from = c.get("fromDate", "")
            date_to = c.get("toDate", "")
            if date_from or date_to:
                result += f"   Период: {date_from} - {date_to}\n"

            result += "\n"

        return result

    finally:
        await client.close()


async def _get_campaign_stats(params: dict) -> str:
    """Get campaign statistics for a period."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    campaign_id = params.get("campaign_id")
    date_from_str = params.get("date_from")
    date_to_str = params.get("date_to")

    if not campaign_id:
        return "Укажи ID кампании (campaign_id)"

    try:
        date_from = datetime.strptime(date_from_str, "%Y-%m-%d").date()
        date_to = datetime.strptime(date_to_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return "Некорректный формат даты. Используй YYYY-MM-DD"

    client = PerformanceClient()
    try:
        stats = await client.get_campaign_statistics([campaign_id], date_from, date_to)

        if not stats:
            return f"Нет статистики по кампании {campaign_id} за указанный период"

        result = f"📊 СТАТИСТИКА КАМПАНИИ {campaign_id}\n"
        result += f"Период: {date_from_str} - {date_to_str}\n\n"

        # Parse statistics data
        rows = stats.get("rows", stats.get("data", []))
        if isinstance(stats, dict) and "report" in stats:
            rows = stats.get("report", {}).get("rows", [])

        total_views = 0
        total_clicks = 0
        total_spend = 0
        total_orders = 0

        for row in rows:
            if isinstance(row, dict):
                total_views += row.get("views", row.get("shows", 0))
                total_clicks += row.get("clicks", 0)
                total_spend += row.get("moneySpent", row.get("spend", 0))
                total_orders += row.get("orders", 0)

        # Convert from nanocurrency if needed
        if total_spend > 1000000:
            total_spend = total_spend / 100_000_000

        result += f"👁 Показы: {total_views:,}\n"
        result += f"👆 Клики: {total_clicks:,}\n"
        result += f"💰 Расход: {total_spend:,.2f} ₽\n"
        result += f"🛒 Заказы: {total_orders:,}\n"

        if total_clicks > 0:
            ctr = (total_clicks / total_views * 100) if total_views > 0 else 0
            cpc = total_spend / total_clicks
            result += f"\n📈 CTR: {ctr:.2f}%\n"
            result += f"💵 CPC: {cpc:.2f} ₽\n"

        if total_orders > 0 and total_spend > 0:
            cpo = total_spend / total_orders
            result += f"🎯 CPO: {cpo:.2f} ₽\n"

        return result

    finally:
        await client.close()


async def _activate_ad_campaign(params: dict) -> str:
    """Activate an advertising campaign."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return "Укажи ID кампании (campaign_id)"

    client = PerformanceClient()
    try:
        await client.activate_campaign(campaign_id)
        return f"✅ Кампания {campaign_id} успешно ВКЛЮЧЕНА"
    except Exception as e:
        return f"❌ Ошибка при активации кампании: {str(e)}"
    finally:
        await client.close()


async def _deactivate_ad_campaign(params: dict) -> str:
    """Deactivate an advertising campaign."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return "Укажи ID кампании (campaign_id)"

    client = PerformanceClient()
    try:
        await client.deactivate_campaign(campaign_id)
        return f"✅ Кампания {campaign_id} успешно ВЫКЛЮЧЕНА"
    except Exception as e:
        return f"❌ Ошибка при деактивации кампании: {str(e)}"
    finally:
        await client.close()


async def _set_product_ad_bid(params: dict) -> str:
    """Set bid for a product in a campaign."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    campaign_id = params.get("campaign_id")
    product_id = params.get("product_id")
    bid = params.get("bid")

    if not campaign_id or not product_id or bid is None:
        return "Укажи campaign_id, product_id и bid"

    client = PerformanceClient()
    try:
        await client.set_product_bid(campaign_id, int(product_id), Decimal(str(bid)))
        return f"✅ Ставка {bid} ₽ установлена для товара {product_id} в кампании {campaign_id}"
    except Exception as e:
        return f"❌ Ошибка при установке ставки: {str(e)}"
    finally:
        await client.close()


async def _get_campaign_products(params: dict) -> str:
    """Get products in a campaign with their bids."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return "Укажи ID кампании (campaign_id)"

    client = PerformanceClient()
    try:
        products = await client.get_products_in_campaign(campaign_id)

        if not products:
            return f"В кампании {campaign_id} нет товаров"

        result = f"📦 ТОВАРЫ В КАМПАНИИ {campaign_id} ({len(products)} шт):\n\n"

        for p in products:
            product_id = p.get("productId", p.get("sku", "Unknown"))
            bid = p.get("bid", 0)

            # Convert from nanocurrency if needed
            if bid > 1000000:
                bid = bid / 100_000_000

            status = p.get("status", p.get("state", ""))
            status_emoji = "🟢" if "ACTIVE" in status.upper() else "🔴"

            result += f"{status_emoji} Товар {product_id}\n"
            result += f"   Ставка: {bid:.2f} ₽\n"
            if status:
                result += f"   Статус: {status}\n"
            result += "\n"

        return result

    finally:
        await client.close()


# ============== AD EXPERIMENT TOOLS ==============

from datetime import timedelta


async def _start_ad_experiment(params: dict) -> str:
    """Start a new advertising experiment."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    campaign_id = params.get("campaign_id")
    action = params.get("action")
    duration_days = params.get("duration_days", 7)
    new_bid = params.get("new_bid")
    product_id = params.get("product_id")

    if not campaign_id or not action:
        return "Укажи campaign_id и action"

    client = PerformanceClient()
    try:
        # Get campaign info
        campaigns = await client.get_campaigns()
        campaign = None
        for c in campaigns:
            if str(c.get("id")) == str(campaign_id):
                campaign = c
                break

        if not campaign:
            return f"Кампания {campaign_id} не найдена"

        campaign_name = campaign.get("title", "Без названия")
        campaign_type = campaign.get("advObjectType", "Unknown")

        # Get baseline metrics (last 7 days)
        today = date.today()
        baseline_start = today - timedelta(days=7)
        baseline_end = today - timedelta(days=1)

        baseline_stats = {"views": 0, "clicks": 0, "spend": 0, "orders": 0, "revenue": 0}
        try:
            stats = await client.get_campaign_statistics([campaign_id], baseline_start, baseline_end)
            rows = stats.get("rows", stats.get("data", []))
            for row in rows:
                if isinstance(row, dict):
                    baseline_stats["views"] += row.get("views", row.get("shows", 0))
                    baseline_stats["clicks"] += row.get("clicks", 0)
                    spend = row.get("moneySpent", row.get("spend", 0))
                    if spend > 1000000:
                        spend = spend / 100_000_000
                    baseline_stats["spend"] += spend
                    baseline_stats["orders"] += row.get("orders", 0)
        except Exception as e:
            logger.warning(f"Could not get baseline stats: {e}")

        # Execute the action
        old_bid = None
        if action == "activate":
            await client.activate_campaign(campaign_id)
        elif action == "deactivate":
            await client.deactivate_campaign(campaign_id)
        elif action == "change_bid" and new_bid and product_id:
            # Get old bid first
            try:
                products = await client.get_products_in_campaign(campaign_id)
                for p in products:
                    if p.get("productId") == product_id:
                        old_bid = p.get("bid", 0)
                        if old_bid > 1000000:
                            old_bid = old_bid / 100_000_000
                        break
            except:
                pass
            await client.set_product_bid(campaign_id, product_id, Decimal(str(new_bid)))

        # Create experiment record
        start_date = today
        review_date = today + timedelta(days=duration_days)

        async with AsyncSessionLocal() as session:
            repo = AdExperimentRepository(session)
            experiment = await repo.create(
                campaign_id=str(campaign_id),
                campaign_name=campaign_name,
                campaign_type=campaign_type,
                action=action,
                start_date=start_date,
                review_date=review_date,
                duration_days=duration_days,
                product_id=product_id,
                old_bid=Decimal(str(old_bid)) if old_bid else None,
                new_bid=Decimal(str(new_bid)) if new_bid else None,
                baseline_views=baseline_stats["views"],
                baseline_clicks=baseline_stats["clicks"],
                baseline_spend=Decimal(str(baseline_stats["spend"])),
                baseline_orders=baseline_stats["orders"],
                baseline_revenue=Decimal(str(baseline_stats.get("revenue", 0))),
            )

        action_text = {
            "activate": "ВКЛЮЧЕНА",
            "deactivate": "ВЫКЛЮЧЕНА",
            "change_bid": f"изменена ставка на {new_bid}₽"
        }.get(action, action)

        result = f"🧪 ЭКСПЕРИМЕНТ ЗАПУЩЕН!\n\n"
        result += f"📢 Кампания: {campaign_name}\n"
        result += f"🎯 Действие: {action_text}\n"
        result += f"📅 Период: {duration_days} дней\n"
        result += f"🔍 Проверка: {review_date.strftime('%d.%m.%Y')}\n"
        result += f"🆔 ID эксперимента: {experiment.id}\n\n"

        if baseline_stats["clicks"] > 0:
            result += f"📊 Базовые показатели (7 дней до):\n"
            result += f"   Показы: {baseline_stats['views']:,}\n"
            result += f"   Клики: {baseline_stats['clicks']:,}\n"
            result += f"   Расход: {baseline_stats['spend']:,.2f}₽\n"

        result += f"\nЯ напомню о проверке результатов {review_date.strftime('%d.%m.%Y')}!"

        return result

    finally:
        await client.close()


async def _get_active_ad_experiments() -> str:
    """Get list of active ad experiments."""
    async with AsyncSessionLocal() as session:
        repo = AdExperimentRepository(session)
        experiments = await repo.get_active_experiments()

        if not experiments:
            return "🧪 Нет активных рекламных экспериментов"

        result = f"🧪 АКТИВНЫЕ ЭКСПЕРИМЕНТЫ ({len(experiments)} шт):\n\n"

        today = date.today()
        for exp in experiments:
            days_left = (exp.review_date - today).days
            status_emoji = "🟡" if days_left > 0 else "🔴"

            result += f"{status_emoji} **{exp.campaign_name}**\n"
            result += f"   ID: {exp.id} | Кампания: {exp.campaign_id}\n"
            result += f"   Действие: {exp.action}\n"
            result += f"   Начало: {exp.start_date.strftime('%d.%m')}\n"

            if days_left > 0:
                result += f"   Проверка через: {days_left} дн. ({exp.review_date.strftime('%d.%m')})\n"
            else:
                result += f"   ⚠️ ПОРА ПРОВЕРИТЬ! (просрочен на {-days_left} дн.)\n"

            result += "\n"

        return result


async def _check_ad_experiment(params: dict) -> str:
    """Check ad experiment results and get recommendation."""
    ok, error = _check_performance_api()
    if not ok:
        return error

    experiment_id = params.get("experiment_id")
    if not experiment_id:
        return "Укажи experiment_id"

    async with AsyncSessionLocal() as session:
        repo = AdExperimentRepository(session)
        experiment = await repo.get_by_id(experiment_id)

        if not experiment:
            return f"Эксперимент {experiment_id} не найден"

        # Get current stats from Performance API
        client = PerformanceClient()
        try:
            stats = await client.get_campaign_statistics(
                [experiment.campaign_id],
                experiment.start_date,
                date.today() - timedelta(days=1)
            )

            result_stats = {"views": 0, "clicks": 0, "spend": 0, "orders": 0}
            rows = stats.get("rows", stats.get("data", []))
            for row in rows:
                if isinstance(row, dict):
                    result_stats["views"] += row.get("views", row.get("shows", 0))
                    result_stats["clicks"] += row.get("clicks", 0)
                    spend = row.get("moneySpent", row.get("spend", 0))
                    if spend > 1000000:
                        spend = spend / 100_000_000
                    result_stats["spend"] += spend
                    result_stats["orders"] += row.get("orders", 0)

            # Update experiment with results
            await repo.update_results(
                experiment_id=experiment_id,
                result_views=result_stats["views"],
                result_clicks=result_stats["clicks"],
                result_spend=Decimal(str(result_stats["spend"])),
                result_orders=result_stats["orders"],
                result_revenue=Decimal("0"),
            )

            # Refresh experiment data
            experiment = await repo.get_by_id(experiment_id)

        finally:
            await client.close()

        # Build report
        result = f"📊 РЕЗУЛЬТАТЫ ЭКСПЕРИМЕНТА #{experiment_id}\n\n"
        result += f"📢 Кампания: {experiment.campaign_name}\n"
        result += f"🎯 Действие: {experiment.action}\n"
        result += f"📅 Период: {experiment.start_date.strftime('%d.%m')} - {date.today().strftime('%d.%m')}\n\n"

        # Views
        before_views = experiment.baseline_views or 0
        after_views = experiment.result_views or 0
        views_change = ((after_views - before_views) / before_views * 100) if before_views > 0 else 0

        # Clicks
        before_clicks = experiment.baseline_clicks or 0
        after_clicks = experiment.result_clicks or 0
        clicks_change = ((after_clicks - before_clicks) / before_clicks * 100) if before_clicks > 0 else 0

        # Spend
        before_spend = float(experiment.baseline_spend or 0)
        after_spend = float(experiment.result_spend or 0)
        spend_change = ((after_spend - before_spend) / before_spend * 100) if before_spend > 0 else 0

        # Orders
        before_orders = experiment.baseline_orders or 0
        after_orders = experiment.result_orders or 0
        orders_change = ((after_orders - before_orders) / before_orders * 100) if before_orders > 0 else 0

        result += f"📈 СРАВНЕНИЕ (до → после):\n"
        result += f"   Показы: {before_views:,} → {after_views:,} ({views_change:+.1f}%)\n"
        result += f"   Клики: {before_clicks:,} → {after_clicks:,} ({clicks_change:+.1f}%)\n"
        result += f"   Расход: {before_spend:,.0f}₽ → {after_spend:,.0f}₽ ({spend_change:+.1f}%)\n"
        result += f"   Заказы: {before_orders} → {after_orders} ({orders_change:+.1f}%)\n"

        # CTR & CPC
        before_ctr = (before_clicks / before_views * 100) if before_views > 0 else 0
        after_ctr = (after_clicks / after_views * 100) if after_views > 0 else 0
        before_cpc = before_spend / before_clicks if before_clicks > 0 else 0
        after_cpc = after_spend / after_clicks if after_clicks > 0 else 0

        result += f"   CTR: {before_ctr:.2f}% → {after_ctr:.2f}%\n"
        result += f"   CPC: {before_cpc:.2f}₽ → {after_cpc:.2f}₽\n"

        result += f"\n💡 РЕКОМЕНДАЦИЯ:\n"

        # Generate recommendation
        if after_orders > before_orders and after_cpc <= before_cpc * 1.2:
            result += "✅ **УСПЕХ** — заказы выросли. Рекомендую оставить.\n"
            suggested_verdict = "SUCCESS"
        elif after_orders < before_orders * 0.8:
            result += "❌ **НЕУДАЧА** — заказы упали. Рекомендую откатить.\n"
            suggested_verdict = "FAILED"
        elif after_cpc > before_cpc * 1.5 and after_orders <= before_orders:
            result += "⚠️ **НЕЭФФЕКТИВНО** — CPC вырос без роста заказов.\n"
            suggested_verdict = "FAILED"
        else:
            result += "🤷 **НЕЙТРАЛЬНО** — значимых изменений нет.\n"
            suggested_verdict = "NEUTRAL"

        result += f"\nЗавершить? Скажи: завершить эксперимент {experiment_id} как {suggested_verdict}"

        return result


async def _complete_ad_experiment(params: dict) -> str:
    """Complete an ad experiment with a verdict."""
    experiment_id = params.get("experiment_id")
    verdict = params.get("verdict")
    recommendation = params.get("recommendation")

    if not experiment_id or not verdict:
        return "Укажи experiment_id и verdict"

    if verdict not in ["SUCCESS", "FAILED", "NEUTRAL"]:
        return "verdict должен быть SUCCESS, FAILED или NEUTRAL"

    async with AsyncSessionLocal() as session:
        repo = AdExperimentRepository(session)
        experiment = await repo.complete_experiment(
            experiment_id=experiment_id,
            verdict=verdict,
            recommendation=recommendation
        )

        if not experiment:
            return f"Эксперимент {experiment_id} не найден"

        verdict_emoji = {"SUCCESS": "✅", "FAILED": "❌", "NEUTRAL": "🤷"}.get(verdict, "")

        result = f"{verdict_emoji} Эксперимент #{experiment_id} завершён!\n\n"
        result += f"📢 Кампания: {experiment.campaign_name}\n"
        result += f"🎯 Вердикт: **{verdict}**\n"

        if recommendation:
            result += f"📝 Заметка: {recommendation}\n"

        if verdict == "FAILED" and experiment.action == "activate":
            result += f"\n⚠️ Рекомендую выключить кампанию {experiment.campaign_id}"
        elif verdict == "FAILED" and experiment.action == "change_bid" and experiment.old_bid:
            result += f"\n⚠️ Рекомендую вернуть ставку на {experiment.old_bid}₽"

        return result


# ============== OPENAI TOOLS FORMAT ==============

def _convert_to_openai_format(tools: list[dict]) -> list[dict]:
    """Convert Anthropic tool format to OpenAI function calling format.

    Anthropic format:
        {"name": ..., "description": ..., "input_schema": {...}}

    OpenAI format:
        {"type": "function", "function": {"name": ..., "description": ..., "parameters": {...}}}
    """
    openai_tools = []
    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }
        openai_tools.append(openai_tool)
    return openai_tools


# OpenAI-formatted tools for use with GPT models
TOOLS_OPENAI = _convert_to_openai_format(TOOLS)
