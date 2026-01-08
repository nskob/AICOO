"""Inline keyboard builders for Telegram bot."""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_price_recommendation_keyboard(recommendation_id: int) -> InlineKeyboardMarkup:
    """Build inline keyboard for price recommendation approval."""
    keyboard = [
        [
            InlineKeyboardButton("✅ Применить", callback_data=f"approve_price:{recommendation_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_price:{recommendation_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_experiment_review_keyboard(experiment_id: int) -> InlineKeyboardMarkup:
    """Build inline keyboard for experiment review."""
    keyboard = [
        [
            InlineKeyboardButton(
                "↩️ Вернуть цену", callback_data=f"rollback_price:{experiment_id}"
            ),
            InlineKeyboardButton("✓ Оставить", callback_data=f"keep_price:{experiment_id}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    """Build main menu keyboard."""
    keyboard = [
        [
            InlineKeyboardButton("📊 Отчёт", callback_data="report:daily"),
            InlineKeyboardButton("📦 Остатки", callback_data="report:inventory"),
        ],
        [
            InlineKeyboardButton("💰 Цены", callback_data="report:prices"),
            InlineKeyboardButton("🧪 Эксперименты", callback_data="report:experiments"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)
