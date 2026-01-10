"""OpenAI GPT assistant integration."""

import json
import logging
from typing import Optional

from openai import AsyncOpenAI

from src.config import settings
from src.ai.prompts import build_system_prompt, BusinessContext
from src.ai.tools import TOOLS_OPENAI, execute_tool

logger = logging.getLogger(__name__)


class OpenAIAssistant:
    """AI assistant powered by OpenAI GPT with tool calling support."""

    def __init__(self, api_key: Optional[str] = None):
        """Initialize OpenAI client."""
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self.model = "gpt-4o"
        self.max_tool_iterations = 5  # Prevent infinite loops

    async def ask(
        self, user_message: str, business_context: BusinessContext, max_tokens: int = 2000
    ) -> str:
        """Ask GPT a question with business context and tool support.

        Args:
            user_message: The user's question
            business_context: Current business data context
            max_tokens: Maximum tokens in response

        Returns:
            GPT's response text
        """
        try:
            system_prompt = build_system_prompt(business_context)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ]

            # Iterate until we get a final response (not a tool call)
            for iteration in range(self.max_tool_iterations):
                response = await self.client.chat.completions.create(
                    model=self.model,
                    max_tokens=max_tokens,
                    messages=messages,
                    tools=TOOLS_OPENAI,
                    tool_choice="auto",
                )

                choice = response.choices[0]
                message = choice.message

                logger.info(f"OpenAI response finish_reason: {choice.finish_reason}")

                # Check if GPT wants to use tools
                if choice.finish_reason == "tool_calls" and message.tool_calls:
                    # Add assistant message with tool calls
                    messages.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [
                            {
                                "id": tc.id,
                                "type": "function",
                                "function": {
                                    "name": tc.function.name,
                                    "arguments": tc.function.arguments,
                                },
                            }
                            for tc in message.tool_calls
                        ],
                    })

                    # Execute each tool and add results
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_input = json.loads(tool_call.function.arguments)
                        except json.JSONDecodeError:
                            tool_input = {}

                        logger.info(f"Tool call: {tool_name} with {tool_input}")

                        # Execute the tool
                        result = await execute_tool(tool_name, tool_input)

                        # Add tool result
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": result,
                        })

                    logger.info(f"Executed {len(message.tool_calls)} tool(s), continuing...")

                else:
                    # Final response - return text
                    if message.content:
                        return message.content
                    else:
                        return "Извините, не удалось получить ответ."

            # Max iterations reached
            logger.warning("Max tool iterations reached")
            return "Извините, обработка заняла слишком много времени. Попробуйте упростить вопрос."

        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return f"Ошибка при обращении к AI: {str(e)}"

    async def close(self) -> None:
        """Close the client (cleanup)."""
        await self.client.close()


# Alias for backward compatibility
ClaudeAssistant = OpenAIAssistant
