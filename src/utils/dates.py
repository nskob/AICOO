"""Date utilities."""

from datetime import date, datetime, timedelta

import pytz

from src.config import settings


def get_timezone():
    """Get configured timezone."""
    return pytz.timezone(settings.timezone)


def now() -> datetime:
    """Get current datetime in configured timezone."""
    return datetime.now(get_timezone())


def today() -> date:
    """Get current date in configured timezone."""
    return now().date()


def yesterday() -> date:
    """Get yesterday's date."""
    return today() - timedelta(days=1)


def days_ago(days: int) -> date:
    """Get date N days ago."""
    return today() - timedelta(days=days)
