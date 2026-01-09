"""Claude AI assistant integration."""

import logging
from typing import Optional

from anthropic import AsyncAnthropic

from src.config import settings
from src.ai.prompts import build_system_prompt, BusinessContext
from src.ai.tools import TOOLS, execute_tool

logger = logging.getLogger(__name__)


class ClaudeAssistant:
    """AI assistant powered by Claude with tool calling support."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize Claude client."""
        self.client = AsyncAnthropic(api_key=api_key or settings.anthropic_api_key)
        self.model = "claude-sonnet-4-20250514"
        self.max_tool_iterations = 5  # Prevent infinite loops

    async def ask(
        self, user_message: str, business_context: BusinessContext, max_tokens: int = 2000
    ) -> str:
        """Ask Claude a question with business context and tool support.

        Args:
            user_message: The user's question
            business_context: Current business data context
            max_tokens: Maximum tokens in response

        Returns:
            Claude's response text
        """
        try:
            system_prompt = build_system_prompt(business_context)

            messages = [{"role": "user", "content": user_message}]

            # Iterate until we get a final response (not a tool call)
            for iteration in range(self.max_tool_iterations):
                response = await self.client.messages.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=messages,
                    tools=TOOLS,
                )

                logger.info(f"Claude response stop_reason: {response.stop_reason}")

                # Check if Claude wants to use a tool
                if response.stop_reason == "tool_use":
                    # Find tool use blocks and execute them
                    tool_results = []
                    assistant_content = []

                    for block in response.content:
                        if block.type == "tool_use":
                            logger.info(f"Tool call: {block.name} with {block.input}")

                            # Execute the tool
                            result = await execute_tool(block.name, block.input)

                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            })
                            assistant_content.append(block)
                        elif block.type == "text":
                            assistant_content.append(block)

                    # Add assistant's response with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": [
                            {"type": b.type, "id": b.id, "name": b.name, "input": b.input}
                            if b.type == "tool_use"
                            else {"type": "text", "text": b.text}
                            for b in assistant_content
                        ],
                    })

                    # Add tool results
                    messages.append({
                        "role": "user",
                        "content": tool_results,
                    })

                    logger.info(f"Executed {len(tool_results)} tool(s), continuing...")

                else:
                    # Final response - extract text
                    text_parts = []
                    for block in response.content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)

                    if text_parts:
                        return "\n".join(text_parts)
                    else:
                        return "Извините, не удалось получить ответ."

            # Max iterations reached
            logger.warning("Max tool iterations reached")
            return "Извините, обработка заняла слишком много времени. Попробуйте упростить вопрос."

        except Exception as e:
            logger.error(f"Claude API error: {e}")
            return f"Ошибка при обращении к AI: {str(e)}"

    async def close(self) -> None:
        """Close the client (cleanup)."""
        await self.client.close()
