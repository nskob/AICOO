"""Telegram message formatting utilities."""

from datetime import date
from decimal import Decimal
from typing import Optional


def format_currency(amount: Decimal) -> str:
    """Format decimal as currency (rubles)."""
    return f"{amount:,.0f} ₽".replace(",", " ")


def format_percent(value: float, signed: bool = True) -> str:
    """Format percentage with optional sign."""
    if signed and value > 0:
        return f"+{value:.1f}%"
    return f"{value:.1f}%"


def format_date(d: date) -> str:
    """Format date in Russian style."""
    return d.strftime("%d.%m.%Y")


def format_number(value: int) -> str:
    """Format integer with thousand separators."""
    return f"{value:,}".replace(",", " ")


def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text to max length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def format_urgency_emoji(urgency: str) -> str:
    """Get emoji for urgency level."""
    return {"critical": "🔴", "warning": "🟡", "normal": "🟢"}.get(urgency, "⚪")


def format_trend_emoji(change_pct: float) -> str:
    """Get emoji for trend direction."""
    if change_pct > 10:
        return "📈"
    elif change_pct > 0:
        return "↗️"
    elif change_pct < -10:
        return "📉"
    elif change_pct < 0:
        return "↘️"
    else:
        return "➡️"
