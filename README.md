# OZON Business Intelligence System

A comprehensive business intelligence and automated pricing system for OZON marketplace sellers. Features sales monitoring, inventory management, AI-powered Q&A via Telegram, and automated price optimization.

## Features

- **📊 Sales Monitoring** — Daily reports with trends and anomaly detection
- **📦 Inventory Management** — Stock forecasting, reorder alerts, supply planning
- **🤖 AI Assistant** — Telegram chatbot powered by Claude that knows all business data
- **💰 Price Optimization** — Automated price recommendations with A/B experiments
- **📢 Advertising Management** — Control ad campaigns via Performance API with experiment tracking

## Technology Stack

- **Python 3.11+** — Core language
- **PostgreSQL** — Database for analytics
- **Telegram Bot API** — User interface
- **Claude API (Anthropic)** — AI assistant with tool calling
- **OZON Seller API** — Products, sales, inventory data
- **OZON Performance API** — Advertising campaigns management
- **SQLAlchemy 2.0** — Async ORM
- **APScheduler** — Task scheduling

## Installation

### Prerequisites

- Python 3.11 or higher
- PostgreSQL 14 or higher
- OZON Seller API credentials
- Telegram Bot Token
- Claude API key (Anthropic)

### Setup Steps

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd AICOO
   ```

2. **Create virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

5. **Set up database:**
   ```bash
   # Create PostgreSQL database
   createdb ozon_bi

   # Run migrations
   alembic upgrade head
   ```

6. **Run the application:**
   ```bash
   python -m src.main
   ```

## Configuration

Edit `.env` file with your credentials:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ozon_bi

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_ADMIN_CHAT_ID=your_chat_id_here

# OZON Seller API
OZON_CLIENT_ID=your_client_id
OZON_API_KEY=your_api_key

# OZON Performance API (advertising)
OZON_PERFORMANCE_CLIENT_ID=your_performance_client_id
OZON_PERFORMANCE_API_KEY=your_performance_secret

# Claude API
ANTHROPIC_API_KEY=sk-ant-your_key_here

# Optional
TIMEZONE=Europe/Moscow
LOG_LEVEL=INFO
```

### Getting Credentials

**Telegram Bot:**
1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Send `/newbot` and follow instructions
3. Copy the bot token
4. To get your chat ID, message [@userinfobot](https://t.me/userinfobot)

**OZON Seller API:**
1. Go to OZON Seller Dashboard
2. Navigate to Settings → API Keys
3. Generate new API key
4. Copy Client-Id and Api-Key

**OZON Performance API (advertising):**
1. Go to [performance.ozon.ru](https://performance.ozon.ru)
2. Navigate to Settings → API Access
3. Create new application (get Client ID)
4. Generate Client Secret
5. Uses OAuth2 authentication (handled automatically)

**Claude API:**
1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. Copy the key starting with `sk-ant-`

## Usage

### Telegram Commands

- `/start` — Welcome message and quick guide
- `/help` — List of available commands
- `/report` — Daily sales report
- `/inventory` — Stock status and reorder recommendations
- `/experiments` — Active price experiments

### AI Assistant

Simply send any question to the bot:

- "Какой товар лучше всего продаётся?"
- "Покажи товары с маржой ниже 15%"
- "Что нужно заказать у поставщика?"
- "Есть ли товары без продаж за месяц?"
- "Покажи рекламные кампании"
- "Запусти рекламу для крема"
- "Какие эксперименты сейчас активны?"

The AI can query OZON API directly using tool calling for real-time data.

### Automated Jobs

The system runs these jobs automatically:

| Time  | Job                    | Description                           |
|-------|------------------------|---------------------------------------|
| 06:00 | OZON Data Sync         | Sync products, inventory, sales       |
| 09:00 | Daily Report           | Morning sales summary                 |
| 09:30 | Price Analysis         | Generate price recommendations        |
| 10:00 | Review Price Experiments | Check completed price A/B tests     |
| 10:30 | Review Ad Experiments  | Check ad experiments due for review   |
| 18:00 | Stock Alerts           | Evening inventory warnings            |

### Price Optimization Workflow

1. **Analysis** — System analyzes products daily considering:
   - Inventory levels (overstock/shortage)
   - Sales trends (growth/decline)
   - Profit margins
   - Historical performance

2. **Recommendation** — Sends Telegram message with:
   - Current vs recommended price
   - Reasoning (factors)
   - Baseline metrics
   - Approve/Reject buttons

3. **Approval** — User clicks "Применить" to:
   - Update price in OZON
   - Create 7-day A/B experiment
   - Track baseline metrics

4. **Review** — After 7 days:
   - Compare results vs baseline
   - Calculate verdict (SUCCESS/FAILED/NEUTRAL)
   - Send results to Telegram
   - Option to rollback if failed

### Advertising Experiments Workflow

1. **Propose** — Ask the AI to run ads:
   - "Запусти рекламу для крема"
   - AI proposes campaign settings (which campaign, action, duration)

2. **Confirm** — User approves the experiment:
   - AI captures baseline metrics (views, clicks, spend, orders)
   - Executes the action (activate/deactivate/change bid)
   - Creates experiment record for tracking

3. **Monitor** — Experiment runs for N days:
   - Baseline period metrics stored
   - Real-time data available via Performance API

4. **Review** — At review date:
   - Scheduler sends reminder
   - Ask AI: "проверить эксперимент {id}"
   - AI compares: views, clicks, CTR, CPC, orders
   - Provides recommendation: SUCCESS/FAILED/NEUTRAL

5. **Complete** — User decides:
   - "завершить эксперимент {id} как SUCCESS"
   - If FAILED: AI recommends rollback action

## Database Schema

### Core Tables

- **products** — Product catalog with pricing and cost
- **sales** — Daily sales aggregates
- **inventory** — Stock snapshots by warehouse
- **price_history** — All price changes
- **price_recommendations** — Price optimization suggestions
- **experiments** — A/B price tests
- **ad_experiments** — Advertising experiments tracking
- **logs** — System audit trail

See the specification document for detailed schema.

## Development

### Running Migrations

Create new migration:
```bash
alembic revision --autogenerate -m "description"
```

Apply migrations:
```bash
alembic upgrade head
```

Rollback:
```bash
alembic downgrade -1
```

### Code Quality

Format code:
```bash
black src/
```

Lint:
```bash
ruff check src/
```

Type check:
```bash
mypy src/
```

### Testing

Run tests:
```bash
pytest tests/
```

## Deployment

### Production Setup (systemd)

1. **Create service file:**
   ```bash
   sudo cp ozon-bi.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

2. **Enable and start:**
   ```bash
   sudo systemctl enable ozon-bi
   sudo systemctl start ozon-bi
   ```

3. **Check status:**
   ```bash
   sudo systemctl status ozon-bi
   ```

4. **View logs:**
   ```bash
   sudo journalctl -u ozon-bi -f
   ```

### Docker Deployment (Optional)

```bash
docker-compose up -d
```

## Troubleshooting

### Bot not responding

1. Check if application is running: `systemctl status ozon-bi`
2. Check logs: `journalctl -u ozon-bi -f`
3. Verify Telegram token in `.env`
4. Test bot token: `curl https://api.telegram.org/bot<TOKEN>/getMe`

### Database connection errors

1. Verify PostgreSQL is running: `systemctl status postgresql`
2. Check DATABASE_URL in `.env`
3. Test connection: `psql <DATABASE_URL>`

### OZON API errors

1. Verify API credentials in OZON Seller dashboard
2. Check API rate limits
3. Review logs for specific error messages

### Price updates not working

1. Ensure `auto_action_enabled` and `price_strategy_enabled` are disabled in OZON
2. Check product has no active promotions
3. Verify minimum price constraints

## Project Structure

```
ozon-bi/
├── src/
│   ├── main.py                 # Entry point
│   ├── config.py               # Configuration
│   ├── database/               # Database models & repositories
│   │   ├── models.py           # SQLAlchemy models
│   │   └── repositories/       # Data access layer
│   ├── ozon/                   # OZON API clients
│   │   ├── client.py           # Seller API client
│   │   ├── performance.py      # Performance API (ads)
│   │   └── sync.py             # Data synchronization
│   ├── bot/                    # Telegram bot
│   ├── ai/                     # Claude integration
│   │   ├── assistant.py        # AI assistant with tool calling
│   │   ├── tools.py            # Tool definitions & execution
│   │   └── prompts.py          # System prompts
│   ├── analytics/              # Business analytics
│   ├── scheduler/              # Automated jobs
│   └── utils/                  # Utilities
├── alembic/                    # Database migrations
├── tests/                      # Tests
├── requirements.txt            # Dependencies
├── pyproject.toml             # Project metadata
├── .env.example               # Example environment
└── README.md                  # This file
```

## Security Notes

- Never commit `.env` file
- Rotate API keys regularly
- Use read-only database user for analytics
- Enable 2FA on all service accounts
- Monitor logs for suspicious activity

## Support

For issues and questions:
1. Check logs: `tail -f ozon-bi.log`
2. Review OZON API documentation
3. Check Telegram bot status
4. Verify all credentials are correct

## License

[Your License Here]

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

**Built with ❤️ for OZON sellers**
