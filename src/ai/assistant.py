"""Claude AI assistant integration."""

import logging
from typing import Optional

from anthropic import AsyncAnthropic

from src.config import settings
from src.ai.prompts import build_system_prompt, BusinessContext

logger = logging.getLogger(__name__)


class ClaudeAssistant:
    """AI assistant powered by Claude."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude client."""
        self.client = AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"

    async def ask(
        self, user_message: str, business_context: BusinessContext, max_tokens: int = 1500
    ) -> str:
        """Ask Claude a question with business context.

        Args:
            user_message: The user's question
            business_context: Current business data context
            max_tokens: Maximum tokens in response

        Returns:
            Claude's response text
        """
        try:
            system_prompt = build_system_prompt(business_context)

            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )

            # Extract text from response
            if response.content and len(response.content) > 0:
                return response.content[0].text
            else:
                return "Извините, не удалось получить ответ."

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return f"Ошибка при обращении к AI: {str(e)}"

    async def close(self) -> None:
        """Close the client (cleanup)."""
        await self.client.close()
