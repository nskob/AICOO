"""Tools for AI assistant to query Ozon data."""

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from openai import AsyncOpenAI

from src.config import settings
from src.ozon.client import OzonClient
from src.ozon.performance import PerformanceClient
from src.database.engine import AsyncSessionLocal
from src.database.repositories.ad_experiments import AdExperimentRepository

logger = logging.getLogger(__name__)

# Tool definitions (Anthropic format, kept for reference)
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
    {
        "name": "get_product_analytics",
        "description": "Получить детальную аналитику по КОНКРЕТНОМУ товару: продажи, просмотры, конверсию, остатки, сравнение с прошлым периодом. ВСЕГДА используй этот инструмент когда пользователь спрашивает о конкретном товаре, просит проанализировать товар, дать рекомендации по товару.",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "Название товара или его часть для поиска (например 'крем', 'yskin', 'увлажняющий')"
                },
                "days": {
                    "type": "integer",
                    "description": "За сколько дней анализировать (по умолчанию 14 — текущая неделя + прошлая для сравнения)",
                    "default": 14
                }
            },
            "required": ["search_query"]
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
    },
    # Content experiment tools
    {
        "name": "update_product_name",
        "description": "Изменить название товара на OZON. ВАЖНО: используй ТОЛЬКО после явного подтверждения пользователя ('да', 'ок', 'меняй', 'согласен'). Сначала предложи новое название и жди ответа!",
        "input_schema": {
            "type": "object",
            "properties": {
                "offer_id": {
                    "type": "string",
                    "description": "Артикул товара (offer_id)"
                },
                "new_name": {
                    "type": "string",
                    "description": "Новое название товара"
                }
            },
            "required": ["offer_id", "new_name"]
        }
    },
    {
        "name": "start_content_experiment",
        "description": "Запустить эксперимент по изменению названия или описания товара с отслеживанием результатов. Изменение применяется сразу, через N дней сравниваем метрики. ВАЖНО: используй только после подтверждения пользователя!",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "ID товара в OZON"
                },
                "offer_id": {
                    "type": "string",
                    "description": "Артикул товара (offer_id/SKU)"
                },
                "field_type": {
                    "type": "string",
                    "description": "Что меняем: name (название) или description (описание)",
                    "enum": ["name", "description"]
                },
                "new_value": {
                    "type": "string",
                    "description": "Новое значение (название или описание)"
                },
                "duration_days": {
                    "type": "integer",
                    "description": "Количество дней для эксперимента (по умолчанию 7)",
                    "default": 7
                }
            },
            "required": ["product_id", "offer_id", "field_type", "new_value"]
        }
    },
    {
        "name": "get_active_content_experiments",
        "description": "Получить список активных экспериментов с контентом (названия, описания). Показывает какие эксперименты сейчас идут и когда их нужно проверить.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "check_content_experiment",
        "description": "Проверить результаты эксперимента с контентом и получить рекомендацию. Сравнивает метрики до и после изменения.",
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
        "name": "complete_content_experiment",
        "description": "Завершить эксперимент с контентом с вердиктом. Если FAILED — можно откатить изменения.",
        "input_schema": {
            "type": "object",
            "properties": {
                "experiment_id": {
                    "type": "integer",
                    "description": "ID эксперимента"
                },
                "verdict": {
                    "type": "string",
                    "description": "Вердикт: SUCCESS (оставляем), FAILED (откатываем), NEUTRAL (оставляем как есть)",
                    "enum": ["SUCCESS", "FAILED", "NEUTRAL"]
                },
                "rollback": {
                    "type": "boolean",
                    "description": "Откатить изменения к старому значению (только для FAILED)",
                    "default": False
                }
            },
            "required": ["experiment_id", "verdict"]
        }
    },
    # Card Audit Tool
    {
        "name": "audit_product_card",
        "description": """Провести полный аудит карточки товара по 7 блокам:
1. Главное фото (CTR)
2. Дополнительные фото/видео
3. Цена и восприятие ценности
4. Название (SEO + CTR)
5. Характеристики (фильтры)
6. Описание (закрытие возражений)
7. Отзывы и Q&A

Каждый блок получает оценку 1-10 и конкретные рекомендации.
Actionable рекомендации можно сразу запустить как A/B эксперименты.

ИСПОЛЬЗУЙ когда пользователь просит:
- "проанализируй карточку"
- "аудит товара"
- "что улучшить в карточке"
- "оцени карточку"
- "почему не продаётся"
""",
        "input_schema": {
            "type": "object",
            "properties": {
                "search_query": {
                    "type": "string",
                    "description": "Название товара или его часть для поиска"
                },
                "blocks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Какие блоки оценить (по умолчанию все). Варианты: main_photo, secondary_photos, price_value, title, characteristics, description, reviews"
                }
            },
            "required": ["search_query"]
        }
    },
    {
        "name": "apply_card_recommendation",
        "description": """Применить рекомендацию из аудита карточки, запустив A/B эксперимент.
Используй ПОСЛЕ audit_product_card, когда пользователь хочет применить конкретную рекомендацию.

Поддерживаемые типы:
- title: изменение названия товара
- description: изменение описания
- price: изменение цены
""",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "ID товара"
                },
                "recommendation_type": {
                    "type": "string",
                    "enum": ["title", "description", "price"],
                    "description": "Тип рекомендации"
                },
                "new_value": {
                    "type": "string",
                    "description": "Новое значение (название, описание или цена)"
                },
                "duration_days": {
                    "type": "integer",
                    "description": "Длительность эксперимента в днях",
                    "default": 7
                }
            },
            "required": ["product_id", "recommendation_type", "new_value"]
        }
    }
]


def _convert_to_openai_format(tools: list) -> list:
    """Convert Anthropic tool format to OpenAI function calling format."""
    openai_tools = []
    for tool in tools:
        openai_tool = {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"]
            }
        }
        openai_tools.append(openai_tool)
    return openai_tools


# OpenAI format tools
TOOLS_OPENAI = _convert_to_openai_format(TOOLS)


async def execute_tool(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Execute a tool and return the result as a string.

    Args:
        tool_name: Name of the tool to execute
        tool_input: Input parameters for the tool

    Returns:
        String result to send back to AI
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
        elif tool_name == "get_product_analytics":
            return await _get_product_analytics(tool_input)
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
        # Quick content update tools
        elif tool_name == "update_product_name":
            return await _update_product_name(tool_input)
        # Content experiment tools
        elif tool_name == "start_content_experiment":
            return await _start_content_experiment(tool_input)
        elif tool_name == "get_active_content_experiments":
            return await _get_active_content_experiments()
        elif tool_name == "check_content_experiment":
            return await _check_content_experiment(tool_input)
        elif tool_name == "complete_content_experiment":
            return await _complete_content_experiment(tool_input)
        # Card audit tools
        elif tool_name == "audit_product_card":
            return await _audit_product_card(tool_input)
        elif tool_name == "apply_card_recommendation":
            return await _apply_card_recommendation(tool_input)
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


async def _get_product_analytics(params: dict) -> str:
    """Get detailed analytics for a specific product using local DB data."""
    search_query = params.get("search_query", "").lower()
    days = params.get("days", 14)

    if not search_query:
        return "Укажи название товара или его часть для поиска"

    async with AsyncSessionLocal() as session:
        from src.database.repositories.products import ProductRepository
        from src.database.repositories.sales import SalesRepository
        from src.database.repositories.inventory import InventoryRepository

        products_repo = ProductRepository(session)
        sales_repo = SalesRepository(session)

        # 1. Find product in local DB
        all_products = await products_repo.get_all_active()

        matched_product = None
        for p in all_products:
            if search_query in p.name.lower() or search_query in (p.offer_id or "").lower():
                matched_product = p
                break

        if not matched_product:
            return f"Товар '{search_query}' не найден в базе. Попробуй другое название или дождись синхронизации данных."

        product_id = matched_product.product_id
        offer_id = matched_product.offer_id
        product_name = matched_product.name

        # 2. Get price and cost from DB
        price = float(matched_product.price) if matched_product.price else 0
        cost_price = float(matched_product.cost_price) if matched_product.cost_price else 0
        margin_pct = (price - cost_price) / price * 100 if price > 0 and cost_price > 0 else 0

        # 3. Get sales from local DB
        today = date.today()
        half_days = days // 2

        current_start = today - timedelta(days=half_days)
        current_end = today - timedelta(days=1)
        prev_start = today - timedelta(days=days)
        prev_end = current_start - timedelta(days=1)

        # Current period sales from DB
        curr_sales, curr_revenue = await sales_repo.get_total_sales_for_period(
            product_id, current_start, current_end
        )
        curr_revenue = float(curr_revenue)

        # Previous period sales from DB
        prev_sales, prev_revenue = await sales_repo.get_total_sales_for_period(
            product_id, prev_start, prev_end
        )
        prev_revenue = float(prev_revenue)

        # Calculate trends
        sales_trend = ((curr_sales - prev_sales) / prev_sales * 100) if prev_sales > 0 else (100 if curr_sales > 0 else 0)
        revenue_trend = ((curr_revenue - prev_revenue) / prev_revenue * 100) if prev_revenue > 0 else 0

        # Daily average
        daily_sales = curr_sales / half_days if half_days > 0 else 0

        # 4. Get stocks, ratings, reviews from API (fresh data)
        client = OzonClient()
        try:
            # Stocks
            stocks = await client.get_stocks([product_id])
            total_stock = 0
            stock_details = []
            for item in stocks:
                for stock in item.stocks or []:
                    present = stock.present or 0
                    reserved = stock.reserved or 0
                    total_stock += present
                    wh_name = stock.warehouse_name or stock.type or "FBO"
                    stock_details.append(f"{wh_name}: {present} шт (резерв: {reserved})")

            # Rating and reviews count
            rating_info = await client.get_product_rating([product_id])
            product_rating = rating_info.get(product_id, {})
            rating = product_rating.get("rating", 0)
            reviews_count = product_rating.get("reviews_count", 0)
            questions_count = product_rating.get("questions_count", 0)

            # Try to get actual reviews (may require Premium)
            reviews = await client.get_reviews_list(product_id, limit=5)

            # Get unanswered questions
            questions = await client.get_questions_list(product_id, limit=5)

            # Get SKU for analytics (different from product_id!)
            product_info = await client.get_product_info([product_id])
            sku = None
            if product_info:
                # SKU is in the raw response, need to fetch it
                url = f"{client.BASE_URL}/v3/product/info/list"
                payload = {"product_id": [product_id]}
                resp = await client.client.post(url, json=payload, headers=client._get_headers())
                if resp.status_code == 200:
                    items = resp.json().get("items", [])
                    if items:
                        sku = items[0].get("sku")

            # Get views and conversion analytics (requires SKU, not product_id)
            content_analytics = {"views_pdp": 0, "views_search": 0, "add_to_cart": 0, "cart_conversion": 0}
            prev_content_analytics = {"views_pdp": 0, "views_search": 0, "add_to_cart": 0, "cart_conversion": 0}

            if sku:
                content_analytics = await client.get_product_content_analytics(
                    sku, current_start, current_end
                )
                prev_content_analytics = await client.get_product_content_analytics(
                    sku, prev_start, prev_end
                )

        finally:
            await client.close()

        # Days of inventory
        days_of_stock = total_stock / daily_sales if daily_sales > 0 else 999

        # 5. Build detailed report
        result = f"📦 ДЕТАЛЬНЫЙ АНАЛИЗ ТОВАРА\n\n"
        result += f"**{product_name[:60]}**\n"
        result += f"Артикул: {offer_id}\n\n"

        result += f"💰 ЦЕНА И МАРЖА:\n"
        result += f"• Текущая цена: {price:,.0f} ₽\n"
        if cost_price > 0:
            result += f"• Себестоимость: {cost_price:,.0f} ₽\n"
            result += f"• Маржа: {margin_pct:.1f}% ({price - cost_price:,.0f} ₽ с единицы)\n"
            result += f"• Прибыль за {half_days} дней: {(price - cost_price) * curr_sales:,.0f} ₽\n"
        result += "\n"

        result += f"📈 ПРОДАЖИ (последние {half_days} дней vs предыдущие {half_days}):\n"
        trend_emoji = "📈" if sales_trend > 5 else "📉" if sales_trend < -5 else "➡️"
        result += f"• Заказов: {curr_sales} шт {trend_emoji} ({sales_trend:+.1f}% vs {prev_sales} шт)\n"
        result += f"• Выручка: {curr_revenue:,.0f} ₽ ({revenue_trend:+.1f}% vs {prev_revenue:,.0f} ₽)\n"
        result += f"• Средний темп: {daily_sales:.1f} шт/день\n"
        if curr_sales > 0:
            result += f"• Средний чек: {curr_revenue / curr_sales:,.0f} ₽\n"
        result += "\n"

        result += f"📦 ОСТАТКИ:\n"
        result += f"• Всего на складах: {total_stock} шт\n"
        if days_of_stock < 999 and daily_sales > 0:
            urgency = "🔴 КРИТИЧНО" if days_of_stock < 7 else "🟡 ВНИМАНИЕ" if days_of_stock < 14 else "🟢 ОК"
            result += f"• Хватит на: ~{days_of_stock:.0f} дней {urgency}\n"
        for sd in stock_details[:3]:
            result += f"  └ {sd}\n"
        result += "\n"

        # Views and conversion section
        views_pdp = content_analytics.get("views_pdp", 0)
        views_search = content_analytics.get("views_search", 0)
        add_to_cart = content_analytics.get("add_to_cart", 0)
        cart_conv = content_analytics.get("cart_conversion", 0)

        prev_views_pdp = prev_content_analytics.get("views_pdp", 0)
        prev_add_to_cart = prev_content_analytics.get("add_to_cart", 0)

        views_trend = ((views_pdp - prev_views_pdp) / prev_views_pdp * 100) if prev_views_pdp > 0 else 0
        cart_trend = ((add_to_cart - prev_add_to_cart) / prev_add_to_cart * 100) if prev_add_to_cart > 0 else 0

        # Calculate CTR (views to cart)
        ctr = (add_to_cart / views_pdp * 100) if views_pdp > 0 else 0
        # Calculate conversion (cart to order)
        order_conv = (curr_sales / add_to_cart * 100) if add_to_cart > 0 else 0

        # Note: OZON deprecated view metrics in their API
        views_unavailable = content_analytics.get("views_unavailable", False)
        if views_unavailable:
            result += f"👁 ПРОСМОТРЫ:\n"
            result += f"• ⚠️ OZON убрал метрики просмотров из API (deprecated)\n"
            result += f"• Данные о просмотрах, CTR и конверсии недоступны\n"
            result += f"• Используй личный кабинет OZON для просмотра этих метрик\n"
        elif views_pdp > 0 or views_search > 0:
            result += f"👁 ПРОСМОТРЫ И КОНВЕРСИЯ (последние {half_days} дней):\n"
            views_emoji = "📈" if views_trend > 5 else "📉" if views_trend < -5 else "➡️"
            result += f"• Просмотры карточки: {views_pdp:,} {views_emoji} ({views_trend:+.1f}%)\n"
            result += f"• Показы в поиске: {views_search:,}\n"
            result += f"• Добавлено в корзину: {add_to_cart:,} ({cart_trend:+.1f}%)\n"
            result += f"• CTR (карточка→корзина): {ctr:.2f}%\n"
            result += f"• Конверсия (корзина→заказ): {order_conv:.1f}%\n"
        result += "\n"

        # Rating, reviews, questions section
        result += f"⭐ РЕЙТИНГ И ОТЗЫВЫ:\n"
        if rating > 0:
            rating_emoji = "🌟" if rating >= 4.5 else "⭐" if rating >= 4.0 else "⚠️"
            result += f"• Рейтинг: {rating:.1f}/5 {rating_emoji}\n"
        else:
            result += f"• Рейтинг: нет данных\n"
        result += f"• Отзывов: {reviews_count}\n"
        result += f"• Вопросов: {questions_count}"
        if questions_count > 0:
            result += " ⚠️ (есть неотвеченные!)"
        result += "\n"

        # Show recent reviews summary if available
        if reviews:
            result += f"\n📝 Последние отзывы:\n"
            for rev in reviews[:3]:
                rev_rating = rev.get("rating", 0)
                rev_text = rev.get("text", "")[:80]
                stars = "⭐" * rev_rating
                result += f"  {stars} {rev_text}...\n"

        # Show unanswered questions
        if questions:
            result += f"\n❓ Неотвеченные вопросы:\n"
            for q in questions[:3]:
                q_text = q.get("text", "")[:60]
                result += f"  • {q_text}...\n"
        result += "\n"

        # Analyze product name/title
        result += f"✍️ АНАЛИЗ КОНТЕНТА:\n"
        result += f"📌 Текущее название:\n«{product_name}»\n\n"

        name_length = len(product_name)
        name_words = len(product_name.split())

        # Check name quality
        name_issues = []
        name_suggestions = []

        if name_length < 40:
            name_issues.append("слишком короткое (<40 символов)")
            name_suggestions.append("добавить ключевые характеристики")
        elif name_length > 150:
            name_issues.append("слишком длинное (>150 символов)")
            name_suggestions.append("сократить до 80-120 символов")

        if name_words < 5:
            name_issues.append("мало слов")
            name_suggestions.append("добавить: тип продукта, для кого, ключевое свойство")

        # Check for important keywords for cosmetics
        cosmetic_keywords = {
            "объём/вес": ["мл", "ml", "г", "гр"],
            "для кого": ["мужской", "женский", "унисекс", "для мужчин", "для женщин"],
            "тип кожи": ["для сухой", "для жирной", "для комбинированной", "для всех типов"],
            "эффект": ["увлажняющий", "антивозрастной", "питательный", "матирующий", "лифтинг"],
            "бренд": ["yskin", "y skin"],
        }

        missing_categories = []
        for category, keywords in cosmetic_keywords.items():
            if not any(kw.lower() in product_name.lower() for kw in keywords):
                missing_categories.append(category)

        result += f"• Длина: {name_length} символов, {name_words} слов\n"
        if name_issues:
            result += f"• ⚠️ Проблемы: {', '.join(name_issues)}\n"
        else:
            result += f"• ✅ Длина в норме\n"

        if missing_categories:
            result += f"• ❌ Не указано: {', '.join(missing_categories)}\n"

        # Store for AI to generate specific suggestions
        result += f"\n🔧 ДАННЫЕ ДЛЯ ОПТИМИЗАЦИИ:\n"
        result += f"• offer_id: {offer_id}\n"
        result += f"• product_id: {product_id}\n"
        result += f"• Отсутствуют: {', '.join(missing_categories) if missing_categories else 'всё ок'}\n"
        result += "\n"

        # 6. Generate SPECIFIC recommendations based on data
        result += f"💡 КОНКРЕТНЫЕ РЕКОМЕНДАЦИИ:\n"

        recommendations = []

        # Stock recommendations with specific numbers
        if days_of_stock < 7 and daily_sales > 0:
            reorder_qty = int(daily_sales * 30)
            recommendations.append(f"🔴 СРОЧНО: закажи {reorder_qty} шт (остатки кончатся через {days_of_stock:.0f} дней)")
        elif days_of_stock < 14 and daily_sales > 0:
            reorder_qty = int(daily_sales * 21)
            recommendations.append(f"🟡 Пора заказать: {reorder_qty} шт для запаса на 3 недели")
        elif days_of_stock > 60 and daily_sales > 0:
            overstock_days = days_of_stock - 30
            recommendations.append(f"📦 Избыток запасов (~{overstock_days:.0f} лишних дней). Рассмотри снижение цены для ускорения продаж")

        # Sales trend recommendations
        if sales_trend < -30 and prev_sales > 3:
            recommendations.append(f"📉 Продажи упали на {abs(sales_trend):.0f}%! Причины: проверь позицию в поиске, цены конкурентов, отзывы")
        elif sales_trend < -10 and prev_sales > 3:
            recommendations.append(f"📉 Небольшой спад -{abs(sales_trend):.0f}%. Мониторь ситуацию")
        elif sales_trend > 30 and curr_sales > 3:
            recommendations.append(f"📈 Отличный рост +{sales_trend:.0f}%! Увеличь закупку на {int(daily_sales * 1.3 * 30)} шт")
        elif sales_trend > 10 and curr_sales > 3:
            recommendations.append(f"📈 Хороший рост +{sales_trend:.0f}%. Продолжай в том же духе")

        # Price recommendations based on margin and sales
        if margin_pct > 60 and curr_sales < 5:
            new_price = int(price * 0.9)
            recommendations.append(f"💰 Высокая маржа ({margin_pct:.0f}%) при низких продажах. Попробуй снизить цену до {new_price:,} ₽")
        elif margin_pct > 50 and sales_trend < 0:
            new_price = int(price * 0.95)
            recommendations.append(f"🧪 Маржа позволяет ({margin_pct:.0f}%). Запусти эксперимент: цена {new_price:,} ₽ на 7 дней")
        elif margin_pct < 20 and margin_pct > 0:
            new_price = int(price * 1.1)
            recommendations.append(f"💸 Низкая маржа ({margin_pct:.0f}%). Рассмотри повышение до {new_price:,} ₽ или снижение себестоимости")

        # Low sales recommendations
        if curr_sales == 0 and prev_sales == 0:
            recommendations.append("⚠️ Нет продаж 2 недели! Срочно: проверь карточку, запусти рекламу, снизь цену")
        elif curr_sales < 3 and total_stock > 50:
            recommendations.append("📢 Мало продаж при хорошем запасе. Запусти рекламную кампанию")

        # Advertising recommendation
        if curr_sales > 0 and curr_sales < 10 and margin_pct > 30:
            ad_budget = int(price * 0.1 * 7)  # 10% от цены на неделю
            recommendations.append(f"📢 Рекомендую рекламу: бюджет ~{ad_budget:,} ₽/неделю для роста продаж")

        # Rating and reviews recommendations
        if rating > 0 and rating < 4.0:
            recommendations.append(f"⚠️ Низкий рейтинг ({rating:.1f}). Проработай негативные отзывы, улучши качество")
        elif rating == 0 and reviews_count == 0:
            recommendations.append("📝 Нет отзывов! Попроси первых покупателей оставить отзыв (скидка за отзыв)")

        if reviews_count < 5 and curr_sales > 10:
            recommendations.append(f"📝 Мало отзывов ({reviews_count}). Стимулируй покупателей: вложи карточку с просьбой")

        if questions_count > 0:
            recommendations.append(f"❓ Есть {questions_count} неотвеченных вопросов! Ответь — это повышает конверсию")

        # Content recommendations
        if name_issues:
            if "короткое" in str(name_issues):
                recommendations.append("✍️ Название короткое. Добавь ключевые слова: тип кожи, эффект, объём")
            if "мало ключевых слов" in str(name_issues):
                recommendations.append("✍️ Добавь в название: целевую аудиторию, ключевые свойства, объём")

        if len(missing_categories) >= 3:
            recommendations.append(f"🔍 Не хватает в названии: {', '.join(missing_categories[:3])}")

        if not recommendations:
            if curr_sales > 5 and sales_trend >= -5:
                recommendations.append("✅ Товар продаётся стабильно. Мониторь остатки и конкурентов")
            else:
                recommendations.append("📊 Недостаточно данных для рекомендаций. Дождись больше продаж")

        for i, rec in enumerate(recommendations, 1):
            result += f"{i}. {rec}\n"

        return result


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

        # Check for special campaign types (SEARCH_PROMO, BRAND_SHELF, etc.)
        if len(products) == 1 and "type" in products[0]:
            campaign_type = products[0].get("type")
            note = products[0].get("note", "")
            return f"📢 Кампания {campaign_id} ({campaign_type})\n\n{note}\n\nДля этого типа кампании товары управляются на уровне категории или всего магазина."

        result = f"📦 ТОВАРЫ В КАМПАНИИ {campaign_id} ({len(products)} шт):\n\n"

        for p in products:
            # Handle different response formats
            product_id = p.get("id", p.get("productId", p.get("sku", "Unknown")))
            bid = p.get("bid", 0)

            # Convert from nanocurrency if needed
            if isinstance(bid, (int, float)) and bid > 1000000:
                bid = bid / 100_000_000

            status = p.get("status", p.get("state", ""))
            if status:
                status_emoji = "🟢" if "ACTIVE" in status.upper() else "🔴"
                result += f"{status_emoji} Товар {product_id}\n"
            else:
                result += f"• Товар {product_id}\n"

            if bid:
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


# ============== QUICK CONTENT UPDATE TOOLS ==============

async def _update_product_name(params: dict) -> str:
    """Update product name directly (without experiment tracking)."""
    offer_id = params.get("offer_id")
    new_name = params.get("new_name")

    if not offer_id or not new_name:
        return "Укажи offer_id и new_name"

    client = OzonClient()
    try:
        success = await client.update_product_content(offer_id, name=new_name)

        if success:
            return (
                f"✅ Название товара изменено!\n\n"
                f"📦 Артикул: {offer_id}\n"
                f"📝 Новое название:\n«{new_name}»\n\n"
                f"⏳ Изменение появится на OZON в течение 15-30 минут после модерации."
            )
        else:
            return f"❌ Не удалось изменить название. Проверь offer_id: {offer_id}"

    except Exception as e:
        return f"❌ Ошибка при изменении названия: {str(e)}"
    finally:
        await client.close()


# ============== CONTENT EXPERIMENT TOOLS ==============

from src.database.repositories.content_experiments import ContentExperimentRepository


async def _start_content_experiment(params: dict) -> str:
    """Start a content A/B experiment (name or description change)."""
    product_id = params.get("product_id")
    offer_id = params.get("offer_id")
    field_type = params.get("field_type")
    new_value = params.get("new_value")
    duration_days = params.get("duration_days", 7)

    if not all([product_id, offer_id, field_type, new_value]):
        return "Укажи product_id, offer_id, field_type и new_value"

    if field_type not in ["name", "description"]:
        return "field_type должен быть 'name' или 'description'"

    client = OzonClient()
    try:
        # Check if there's already an active experiment for this product/field
        async with AsyncSessionLocal() as session:
            repo = ContentExperimentRepository(session)
            if await repo.has_active_experiment(product_id, field_type):
                return f"❌ У товара {product_id} уже есть активный эксперимент с {field_type}"

        # Get current product info
        products = await client.get_product_info([product_id])
        if not products:
            return f"Товар {product_id} не найден"

        product = products[0]
        product_name = product.name

        # Get current value based on field type
        if field_type == "name":
            old_value = product.name
        else:
            # For description, we need to fetch attributes
            # For now, we'll store a placeholder
            old_value = "(текущее описание)"

        # Get baseline metrics (last 7 days)
        today = date.today()
        baseline_start = today - timedelta(days=7)
        baseline_end = today - timedelta(days=1)

        baseline = await client.get_product_content_analytics(product_id, baseline_start, baseline_end)

        # Apply the change
        if field_type == "name":
            success = await client.update_product_content(offer_id, name=new_value)
        else:
            success = await client.update_product_content(offer_id, description=new_value)

        if not success:
            return "❌ Не удалось применить изменение в OZON"

        # Create experiment record
        start_date = today
        review_date = today + timedelta(days=duration_days)

        async with AsyncSessionLocal() as session:
            repo = ContentExperimentRepository(session)
            experiment = await repo.create(
                product_id=product_id,
                offer_id=offer_id,
                product_name=product_name,
                field_type=field_type,
                old_value=old_value,
                new_value=new_value,
                start_date=start_date,
                review_date=review_date,
                duration_days=duration_days,
                baseline_views=baseline.get("views_pdp", 0),
                baseline_add_to_cart=baseline.get("add_to_cart", 0),
                baseline_orders=baseline.get("orders", 0),
                baseline_revenue=Decimal(str(baseline.get("revenue", 0))),
                baseline_conversion=Decimal(str(baseline.get("cart_conversion", 0))),
            )

        field_name = "Название" if field_type == "name" else "Описание"
        result = f"🧪 ЭКСПЕРИМЕНТ ЗАПУЩЕН!\n\n"
        result += f"📦 Товар: {product_name[:50]}...\n" if len(product_name) > 50 else f"📦 Товар: {product_name}\n"
        result += f"✏️ Изменение: {field_name}\n"
        result += f"📅 Период: {duration_days} дней\n"
        result += f"🔍 Проверка: {review_date.strftime('%d.%m.%Y')}\n"
        result += f"🆔 ID эксперимента: {experiment.id}\n\n"

        if baseline.get("orders", 0) > 0:
            result += f"📊 Базовые показатели (7 дней до):\n"
            result += f"   Просмотры: {baseline.get('views_pdp', 0):,}\n"
            result += f"   В корзину: {baseline.get('add_to_cart', 0):,}\n"
            result += f"   Заказы: {baseline.get('orders', 0)}\n"
            result += f"   Выручка: {baseline.get('revenue', 0):,.0f}₽\n"

        result += f"\nЯ напомню о проверке результатов {review_date.strftime('%d.%m.%Y')}!"
        return result

    finally:
        await client.close()


async def _get_active_content_experiments() -> str:
    """Get list of active content experiments."""
    async with AsyncSessionLocal() as session:
        repo = ContentExperimentRepository(session)
        experiments = await repo.get_active_experiments()

        if not experiments:
            return "🧪 Нет активных экспериментов с контентом"

        result = f"🧪 АКТИВНЫЕ ЭКСПЕРИМЕНТЫ С КОНТЕНТОМ ({len(experiments)} шт):\n\n"

        today = date.today()
        for exp in experiments:
            days_left = (exp.review_date - today).days
            status_emoji = "🟡" if days_left > 0 else "🔴"
            field_name = "Название" if exp.field_type == "name" else "Описание"

            short_name = exp.product_name[:35] + "..." if len(exp.product_name) > 35 else exp.product_name
            result += f"{status_emoji} **{short_name}**\n"
            result += f"   ID: {exp.id} | Артикул: {exp.offer_id}\n"
            result += f"   Изменение: {field_name}\n"
            result += f"   Начало: {exp.start_date.strftime('%d.%m')}\n"

            if days_left > 0:
                result += f"   Проверка через: {days_left} дн. ({exp.review_date.strftime('%d.%m')})\n"
            else:
                result += f"   ⚠️ ПОРА ПРОВЕРИТЬ! (просрочен на {-days_left} дн.)\n"

            result += "\n"

        return result


async def _check_content_experiment(params: dict) -> str:
    """Check content experiment results and get recommendation."""
    experiment_id = params.get("experiment_id")
    if not experiment_id:
        return "Укажи experiment_id"

    async with AsyncSessionLocal() as session:
        repo = ContentExperimentRepository(session)
        experiment = await repo.get_by_id(experiment_id)

        if not experiment:
            return f"Эксперимент {experiment_id} не найден"

        # Get current stats from OZON
        client = OzonClient()
        try:
            result_stats = await client.get_product_content_analytics(
                experiment.product_id,
                experiment.start_date,
                date.today() - timedelta(days=1)
            )

            # Update experiment with results
            await repo.update_results(
                experiment_id=experiment_id,
                result_views=result_stats.get("views_pdp", 0),
                result_add_to_cart=result_stats.get("add_to_cart", 0),
                result_orders=result_stats.get("orders", 0),
                result_revenue=Decimal(str(result_stats.get("revenue", 0))),
                result_conversion=Decimal(str(result_stats.get("cart_conversion", 0))),
            )

            # Refresh experiment data
            experiment = await repo.get_by_id(experiment_id)

        finally:
            await client.close()

        # Build report
        field_name = "Название" if experiment.field_type == "name" else "Описание"
        short_name = experiment.product_name[:40] + "..." if len(experiment.product_name) > 40 else experiment.product_name

        result = f"📊 РЕЗУЛЬТАТЫ ЭКСПЕРИМЕНТА #{experiment_id}\n\n"
        result += f"📦 Товар: {short_name}\n"
        result += f"✏️ Изменение: {field_name}\n"
        result += f"📅 Период: {experiment.start_date.strftime('%d.%m')} - {date.today().strftime('%d.%m')}\n\n"

        # Views
        before_views = experiment.baseline_views or 0
        after_views = experiment.result_views or 0
        views_change = ((after_views - before_views) / before_views * 100) if before_views > 0 else 0

        # Add to cart
        before_cart = experiment.baseline_add_to_cart or 0
        after_cart = experiment.result_add_to_cart or 0
        cart_change = ((after_cart - before_cart) / before_cart * 100) if before_cart > 0 else 0

        # Orders
        before_orders = experiment.baseline_orders or 0
        after_orders = experiment.result_orders or 0
        orders_change = ((after_orders - before_orders) / before_orders * 100) if before_orders > 0 else 0

        # Revenue
        before_revenue = float(experiment.baseline_revenue or 0)
        after_revenue = float(experiment.result_revenue or 0)
        revenue_change = ((after_revenue - before_revenue) / before_revenue * 100) if before_revenue > 0 else 0

        result += f"📈 СРАВНЕНИЕ (до → после):\n"
        result += f"   Просмотры: {before_views:,} → {after_views:,} ({views_change:+.1f}%)\n"
        result += f"   В корзину: {before_cart:,} → {after_cart:,} ({cart_change:+.1f}%)\n"
        result += f"   Заказы: {before_orders} → {after_orders} ({orders_change:+.1f}%)\n"
        result += f"   Выручка: {before_revenue:,.0f}₽ → {after_revenue:,.0f}₽ ({revenue_change:+.1f}%)\n"

        # Conversion rate
        before_conv = (before_cart / before_views * 100) if before_views > 0 else 0
        after_conv = (after_cart / after_views * 100) if after_views > 0 else 0
        result += f"   Конверсия в корзину: {before_conv:.2f}% → {after_conv:.2f}%\n"

        result += f"\n💡 РЕКОМЕНДАЦИЯ:\n"

        # Generate recommendation
        if after_orders > before_orders and after_conv >= before_conv:
            result += "✅ **УСПЕХ** — заказы и конверсия выросли. Рекомендую оставить новый контент.\n"
            suggested_verdict = "SUCCESS"
        elif after_orders < before_orders * 0.8:
            result += "❌ **НЕУДАЧА** — заказы упали. Рекомендую откатить к старому контенту.\n"
            suggested_verdict = "FAILED"
        elif after_conv < before_conv * 0.9 and after_orders <= before_orders:
            result += "⚠️ **НЕЭФФЕКТИВНО** — конверсия упала без роста заказов.\n"
            suggested_verdict = "FAILED"
        else:
            result += "🤷 **НЕЙТРАЛЬНО** — значимых изменений нет. Можно оставить.\n"
            suggested_verdict = "NEUTRAL"

        result += f"\nЗавершить? Скажи: завершить контент-эксперимент {experiment_id} как {suggested_verdict}"
        if suggested_verdict == "FAILED":
            result += " с откатом"

        return result


async def _complete_content_experiment(params: dict) -> str:
    """Complete a content experiment with a verdict."""
    experiment_id = params.get("experiment_id")
    verdict = params.get("verdict")
    rollback = params.get("rollback", False)

    if not experiment_id or not verdict:
        return "Укажи experiment_id и verdict"

    if verdict not in ["SUCCESS", "FAILED", "NEUTRAL"]:
        return "verdict должен быть SUCCESS, FAILED или NEUTRAL"

    async with AsyncSessionLocal() as session:
        repo = ContentExperimentRepository(session)
        experiment = await repo.get_by_id(experiment_id)

        if not experiment:
            return f"Эксперимент {experiment_id} не найден"

        # If rollback requested and verdict is FAILED, revert the change
        if rollback and verdict == "FAILED":
            client = OzonClient()
            try:
                if experiment.field_type == "name":
                    success = await client.update_product_content(
                        experiment.offer_id, name=experiment.old_value
                    )
                else:
                    success = await client.update_product_content(
                        experiment.offer_id, description=experiment.old_value
                    )

                if success:
                    await repo.rollback_experiment(experiment_id)
                    field_name = "Название" if experiment.field_type == "name" else "Описание"
                    return (
                        f"🔄 Эксперимент #{experiment_id} откачен!\n\n"
                        f"📦 Товар: {experiment.product_name[:40]}...\n"
                        f"✏️ {field_name} возвращено к исходному значению\n"
                        f"🎯 Вердикт: FAILED (откачено)"
                    )
                else:
                    return "❌ Не удалось откатить изменения в OZON"
            finally:
                await client.close()

        # Complete without rollback
        experiment = await repo.complete_experiment(
            experiment_id=experiment_id,
            verdict=verdict,
        )

        if not experiment:
            return f"Эксперимент {experiment_id} не найден"

        verdict_emoji = {"SUCCESS": "✅", "FAILED": "❌", "NEUTRAL": "🤷"}.get(verdict, "")
        field_name = "Название" if experiment.field_type == "name" else "Описание"

        result = f"{verdict_emoji} Эксперимент #{experiment_id} завершён!\n\n"
        result += f"📦 Товар: {experiment.product_name[:40]}...\n"
        result += f"✏️ Изменение: {field_name}\n"
        result += f"🎯 Вердикт: **{verdict}**\n"

        if verdict == "SUCCESS":
            result += "\n✨ Новый контент оставлен"
        elif verdict == "FAILED" and not rollback:
            result += f"\n⚠️ Рекомендую откатить: завершить контент-эксперимент {experiment_id} как FAILED с откатом"

        return result


# ============== CARD AUDIT TOOLS ==============

from src.ai.card_evaluator import (
    BlockEvaluation,
    CardEvaluation,
    BLOCK_INFO,
    evaluate_card_block,
    format_evaluation_report,
    extract_priority_actions,
)


async def _audit_product_card(params: dict) -> str:
    """Perform a full audit of a product card across all 7 blocks."""
    search_query = params.get("search_query", "").lower()
    blocks_to_evaluate = params.get("blocks")

    if not search_query:
        return "Укажи название товара или его часть для поиска"

    # Default: evaluate all blocks
    all_blocks = ["main_photo", "secondary_photos", "price_value", "title",
                  "characteristics", "description", "reviews"]

    if blocks_to_evaluate:
        # Validate requested blocks
        invalid = [b for b in blocks_to_evaluate if b not in all_blocks]
        if invalid:
            return f"Неизвестные блоки: {invalid}. Доступные: {all_blocks}"
        blocks_to_evaluate = blocks_to_evaluate
    else:
        blocks_to_evaluate = all_blocks

    # 1. Find product in local DB
    async with AsyncSessionLocal() as session:
        from src.database.repositories.products import ProductRepository
        from src.database.repositories.sales import SalesRepository

        products_repo = ProductRepository(session)
        all_products = await products_repo.get_all_active()

        matched_product = None
        for p in all_products:
            if search_query in p.name.lower() or search_query in (p.offer_id or "").lower():
                matched_product = p
                break

        if not matched_product:
            return f"Товар '{search_query}' не найден в базе. Попробуй другое название."

    product_id = matched_product.product_id
    offer_id = matched_product.offer_id
    product_name = matched_product.name
    price = float(matched_product.price) if matched_product.price else 0

    # 2. Fetch additional data from OZON API
    client = OzonClient()
    try:
        # Get detailed product info
        products_info = await client.get_product_info([product_id])
        if not products_info:
            return f"Не удалось получить информацию о товаре {product_id}"

        product_info = products_info[0]

        # Get product attributes (for description)
        attributes = await client.get_product_attributes(product_id)

        # Extract description from attributes
        description = ""
        characteristics = []
        for attr in attributes.get("attributes", []):
            attr_id = attr.get("attribute_id")
            values = attr.get("values", [])
            if attr_id == 4191:  # Description attribute
                description = values[0].get("value", "") if values else ""
            else:
                # Collect other characteristics
                attr_name = attr.get("name", "")
                attr_value = values[0].get("value", "") if values else ""
                if attr_name and attr_value:
                    characteristics.append(f"{attr_name}: {attr_value}")

        # Get images
        images = product_info.images if hasattr(product_info, 'images') else []
        main_photo_url = images[0] if images else "нет фото"
        secondary_photos = images[1:] if len(images) > 1 else []

        # Get rating and reviews
        rating_info = await client.get_product_rating([product_id])
        rating_data = rating_info.get(product_id, {})
        rating = rating_data.get("rating", 0)
        reviews_count = rating_data.get("reviews_count", 0)
        questions_count = rating_data.get("questions_count", 0)

        # Try to get actual reviews
        reviews = await client.get_reviews_list(product_id, limit=10)
        questions = await client.get_questions_list(product_id, limit=5)

        # Format reviews for prompt
        reviews_text = ""
        if reviews:
            for rev in reviews[:5]:
                stars = rev.get("rating", 0)
                text = rev.get("text", "")[:200]
                reviews_text += f"⭐{stars}/5: {text}\n"
        else:
            reviews_text = "Отзывов пока нет"

        # Format questions for prompt
        questions_text = ""
        if questions:
            for q in questions[:3]:
                questions_text += f"• {q.get('text', '')[:100]}\n"
        else:
            questions_text = "Вопросов нет"

        # Old price
        old_price = product_info.old_price if hasattr(product_info, 'old_price') else "0"

    finally:
        await client.close()

    # 3. Prepare product data for evaluation
    product_data = {
        "product_id": product_id,
        "offer_id": offer_id,
        "product_name": product_name,
        "title": product_name,
        "price": price,
        "old_price": old_price,
        "main_photo_url": main_photo_url,
        "photo_urls": ", ".join(secondary_photos[:5]) if secondary_photos else "нет дополнительных фото",
        "description": description[:2000] if description else "Описание не заполнено",
        "description_preview": description[:500] if description else "Описание не заполнено",
        "characteristics": "\n".join(characteristics[:20]) if characteristics else "Характеристики не заполнены",
        "reviews": reviews_text,
        "questions": questions_text,
        "rating": rating,
        "reviews_count": reviews_count,
    }

    # 4. Evaluate each block using GPT-4o
    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)

    block_evaluations = []
    for block_id in blocks_to_evaluate:
        try:
            evaluation = await evaluate_card_block(block_id, product_data, openai_client)
            block_evaluations.append(evaluation)
        except Exception as e:
            logger.error(f"Failed to evaluate block {block_id}: {e}")
            block_evaluations.append(BlockEvaluation(
                block_name=BLOCK_INFO[block_id]["name"],
                block_id=block_id,
                score=5,
                diagnosis=f"Ошибка оценки: {str(e)}",
                recommendations=[],
                metrics_affected=BLOCK_INFO[block_id]["metrics"],
            ))

    # 5. Calculate overall score
    overall_score = sum(b.score for b in block_evaluations) / len(block_evaluations) if block_evaluations else 0

    # 6. Extract priority actions
    priority_actions = extract_priority_actions(block_evaluations, product_data)

    # 7. Create full evaluation
    card_evaluation = CardEvaluation(
        product_id=product_id,
        product_name=product_name,
        overall_score=overall_score,
        blocks=block_evaluations,
        priority_actions=priority_actions,
    )

    # 8. Format and return report
    report = format_evaluation_report(card_evaluation)

    # Add context for AI to suggest experiments
    if priority_actions:
        report += "\n📝 **ДАННЫЕ ДЛЯ ЭКСПЕРИМЕНТОВ:**\n"
        report += f"product_id: {product_id}\n"
        report += f"offer_id: {offer_id}\n"

    return report


async def _apply_card_recommendation(params: dict) -> str:
    """Apply a recommendation from card audit by starting an experiment."""
    product_id = params.get("product_id")
    recommendation_type = params.get("recommendation_type")
    new_value = params.get("new_value")
    duration_days = params.get("duration_days", 7)

    if not all([product_id, recommendation_type, new_value]):
        return "Укажи product_id, recommendation_type и new_value"

    if recommendation_type not in ["title", "description", "price"]:
        return "recommendation_type должен быть 'title', 'description' или 'price'"

    # Get product info to get offer_id
    client = OzonClient()
    try:
        products = await client.get_product_info([product_id])
        if not products:
            return f"Товар {product_id} не найден"

        product = products[0]
        offer_id = product.offer_id
        product_name = product.name
    finally:
        await client.close()

    # Route to appropriate experiment type
    if recommendation_type in ["title", "description"]:
        # Content experiment
        field_type = "name" if recommendation_type == "title" else "description"

        return await _start_content_experiment({
            "product_id": product_id,
            "offer_id": offer_id,
            "field_type": field_type,
            "new_value": new_value,
            "duration_days": duration_days,
        })

    elif recommendation_type == "price":
        # Price experiment
        from src.database.repositories.experiments import ExperimentRepository

        try:
            new_price = Decimal(str(new_value).replace(",", ".").replace(" ", "").replace("₽", ""))
        except:
            return f"Некорректная цена: {new_value}"

        # Get current price
        async with AsyncSessionLocal() as session:
            from src.database.repositories.products import ProductRepository
            products_repo = ProductRepository(session)
            product_db = await products_repo.get_by_product_id(product_id)

            if not product_db:
                return f"Товар {product_id} не найден в базе"

            old_price = product_db.price

            # Create price experiment
            exp_repo = ExperimentRepository(session)
            experiment = await exp_repo.create(
                product_id=product_id,
                original_price=old_price,
                test_price=new_price,
                duration_days=duration_days,
            )

        # Apply new price via OZON API
        client = OzonClient()
        try:
            success = await client.update_price(product_id, new_price)

            if not success:
                return "❌ Не удалось изменить цену в OZON"

            result = f"🧪 ЦЕНОВОЙ ЭКСПЕРИМЕНТ ЗАПУЩЕН!\n\n"
            result += f"📦 Товар: {product_name[:50]}...\n"
            result += f"💰 Цена: {old_price}₽ → {new_price}₽\n"
            result += f"📅 Период: {duration_days} дней\n"
            result += f"🆔 ID эксперимента: {experiment.id}\n\n"
            result += f"Я напомню о проверке результатов через {duration_days} дней!"

            return result

        finally:
            await client.close()

    return "Неизвестный тип рекомендации"
