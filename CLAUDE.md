# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

OZON Business Intelligence — система аналитики и автоматизации для продавцов OZON marketplace. Telegram-бот с AI-ассистентом (GPT-4o), автоматическими отчётами и A/B-тестированием цен/рекламы/контента.

## Directory Structure

```
/opt/ozon-bi/          ← PRODUCTION (сервис запускается отсюда)
/home/deploy/AICOO/    ← Git-репозиторий (для разработки)
```

**ВАЖНО:** Сервис работает из `/opt/ozon-bi`. Изменения в `/home/deploy/AICOO` не применяются автоматически.

## Commands

```bash
# Управление сервисом
sudo systemctl status ozon-bi      # Статус
sudo systemctl restart ozon-bi     # Перезапуск
sudo journalctl -u ozon-bi -f      # Логи в реальном времени

# Миграции БД (из /opt/ozon-bi)
cd /opt/ozon-bi
source venv/bin/activate
alembic upgrade head               # Применить миграции
alembic revision --autogenerate -m "desc"  # Создать миграцию

# Запуск вручную (для отладки)
cd /opt/ozon-bi && source venv/bin/activate
python -m src.main

# Код
black src/                         # Форматирование
ruff check src/                    # Линтер
mypy src/                          # Типы
pytest tests/                      # Тесты
```

## Architecture

### Core Flow

1. **Telegram Bot** (`src/bot/`) — пользовательский интерфейс
2. **AI Assistant** (`src/ai/`) — GPT-4o с tool calling для запросов к OZON API
3. **Scheduler** (`src/scheduler/jobs.py`) — 7 автоматических задач
4. **OZON APIs** (`src/ozon/`) — Seller API + Performance API (реклама)

### Scheduled Jobs (Europe/Moscow)

| Время | Job | Описание |
|-------|-----|----------|
| 06:00 | `sync_ozon_data` | Синхронизация товаров/остатков/продаж |
| 09:00 | `send_daily_report` | Ежедневный отчёт по продажам |
| 09:30 | `run_price_analysis` | Рекомендации по ценам |
| 10:00 | `review_experiments` | Проверка ценовых экспериментов |
| 10:30 | `review_ad_experiments` | Проверка рекламных экспериментов |
| 11:00 | `review_content_experiments` | Проверка контент-экспериментов |
| 18:00 | `send_stock_alerts` | Алерты по остаткам |

### Key Components

- **`src/ai/tools.py`** — определения инструментов для GPT (get_sales_analytics, get_ad_campaigns, etc.). Формат Anthropic → конвертируется в OpenAI через `TOOLS_OPENAI`

- **`src/ai/assistant.py`** — `OpenAIAssistant` с циклом tool calling (до 5 итераций)

- **`src/ozon/client.py`** — Seller API (товары, цены, остатки, аналитика)
- **`src/ozon/performance.py`** — Performance API (рекламные кампании)

- **`src/database/repositories/`** — Repository pattern для всех моделей

### Database Models (`src/database/models.py`)

| Таблица | Назначение |
|---------|------------|
| `products` | Каталог товаров |
| `sales` | Ежедневные продажи |
| `inventory` | Остатки по складам |
| `price_recommendations` | Рекомендации по ценам |
| `experiments` | Ценовые A/B-эксперименты |
| `ad_experiments` | Рекламные эксперименты |
| `content_experiments` | Эксперименты с контентом (название/описание) |
| `price_history`, `logs` | Аудит |

## Configuration

Файл `/opt/ozon-bi/.env`:

```env
DATABASE_URL=postgresql+asyncpg://...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_ADMIN_CHAT_ID=-5165753336    # Группа для отчётов
OZON_CLIENT_ID=...
OZON_API_KEY=...
OZON_PERFORMANCE_CLIENT_ID=...        # Для рекламы
OZON_PERFORMANCE_API_KEY=...
OPENAI_API_KEY=...
TIMEZONE=Europe/Moscow
```

## Important Patterns

- **Async everywhere**: SQLAlchemy async, httpx, telegram bot
- **Session management**: `async with AsyncSessionLocal() as session:`
- **OZON prices**: Все цены передаются как **строки** в API
- **Tool calling**: GPT может вызывать до 5 инструментов за один запрос
- **Все сообщения** (отчёты, алерты) отправляются в `settings.telegram_admin_chat_id`

## Deployment

```bash
# После изменений в /opt/ozon-bi
sudo systemctl restart ozon-bi

# Если ошибка "start-limit-hit" (слишком много рестартов)
sudo systemctl reset-failed ozon-bi
sudo systemctl start ozon-bi
```

## Debugging

```bash
# Логи
journalctl -u ozon-bi -n 100 --no-pager
tail -f /opt/ozon-bi/ozon-bi.log

# Проверка PostgreSQL
sudo -u postgres psql ozon_bi

# Тест Telegram бота
curl "https://api.telegram.org/bot<TOKEN>/getMe"
```
