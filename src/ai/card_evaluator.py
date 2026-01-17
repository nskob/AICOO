"""Product card evaluation system.

Evaluates OZON product cards across 7 blocks:
1. Main Photo (CTR)
2. Secondary Photos + Video
3. Price & Value Perception
4. Title (SEO + CTR)
5. Characteristics (filters)
6. Description (objection handling)
7. Reviews & Q&A (social proof)

Each block gets a score 1-10 and actionable recommendations.
"""

import logging
from dataclasses import dataclass
from typing import Optional
import json

logger = logging.getLogger(__name__)


@dataclass
class BlockEvaluation:
    """Evaluation result for a single block."""
    block_name: str
    block_id: str  # For referencing in actions
    score: int  # 1-10
    diagnosis: str  # What's wrong/right
    recommendations: list[dict]  # List of {action, description, actionable, action_type}
    metrics_affected: list[str]  # CTR, CR, etc.


@dataclass
class CardEvaluation:
    """Full card evaluation result."""
    product_id: int
    product_name: str
    overall_score: float
    blocks: list[BlockEvaluation]
    priority_actions: list[dict]  # Top 3 actionable improvements


# Evaluation prompts for each block
EVALUATION_PROMPTS = {
    "main_photo": """Ты — пользователь Ozon, который листает выдачу 2 секунды.
Посмотри только на главное фото (URL: {main_photo_url}), не открывая карточку.

Оцени по критериям:
1. Что это за продукт? (понятно за 1 сек?)
2. Для кого он? (очевидна ЦА?)
3. Чем он отличается от соседних? (есть УТП?)
4. Захотел бы ты кликнуть? (почему да/нет?)

Название товара для контекста: {product_name}
Цена: {price} ₽

Верни JSON:
{{
  "score": 1-10,
  "diagnosis": "краткий диагноз что не так или что хорошо",
  "problems": ["проблема 1", "проблема 2"],
  "recommendations": [
    {{"action": "конкретное действие", "priority": "high/medium/low"}}
  ]
}}""",

    "secondary_photos": """Представь, что пользователь не читает описание вообще.
Посмотри на все фото товара и ответь:

Фото товара: {photo_urls}
Название: {product_name}

Оцени:
1. Как пользоваться продуктом? (показано?)
2. Что он делает? (результат виден?)
3. Почему он лучше других? (преимущества визуализированы?)
4. Какие возражения закрывает? (страхи сняты?)

Верни JSON:
{{
  "score": 1-10,
  "diagnosis": "краткий диагноз",
  "missing_content": ["чего не хватает"],
  "recommendations": [
    {{"action": "добавить фото X", "type": "photo", "priority": "high/medium/low"}}
  ]
}}""",

    "price_value": """Забудь про себестоимость. Посмотри на карточку глазами покупателя.

Товар: {product_name}
Цена: {price} ₽
Старая цена: {old_price} ₽
Описание: {description_preview}

Ответь:
1. Почему этот продукт стоит именно столько? (цена обоснована?)
2. С чем покупатель сравнивает в голове? (конкуренты)
3. В каком сегменте товар: масс / middle / premium?
4. Цена логична или вызывает вопросы?

Верни JSON:
{{
  "score": 1-10,
  "perceived_segment": "mass/middle/premium",
  "diagnosis": "краткий диагноз",
  "price_anchors_missing": ["какие якоря добавить"],
  "recommendations": [
    {{"action": "действие", "type": "price/content", "priority": "high/medium/low"}}
  ]
}}""",

    "title": """Представь, что это единственный текст, который видит пользователь в выдаче.

Название: {title}

Оцени:
1. Понятно ли, что это? (категория ясна?)
2. Для кого? (ЦА понятна?)
3. Есть ли причина кликнуть? (УТП в названии?)
4. Есть ли перегруз мусорными словами? (спам ключей?)
5. SEO: ключевые слова в начале?

Верни JSON:
{{
  "score": 1-10,
  "diagnosis": "краткий диагноз",
  "seo_issues": ["проблемы с SEO"],
  "recommendations": [
    {{"action": "новый вариант названия или правка", "type": "title", "new_value": "предложенное название", "priority": "high/medium/low"}}
  ]
}}""",

    "characteristics": """Представь, что пользователь ищет через фильтры, а не поиск.

Характеристики товара:
{characteristics}

Оцени:
1. Все ли важные фильтры заполнены?
2. Есть ли пустые или «Не указано»?
3. Есть ли характеристики, которые работают против товара?
4. Конкретные значения или размытые?

Верни JSON:
{{
  "score": 1-10,
  "diagnosis": "краткий диагноз",
  "missing_fields": ["какие поля пустые"],
  "problematic_values": ["какие значения вредят"],
  "recommendations": [
    {{"action": "заполнить X значением Y", "type": "characteristic", "priority": "high/medium/low"}}
  ]
}}""",

    "description": """Представь, что пользователь почти готов купить, но сомневается.

Описание товара:
{description}

Оцени:
1. Какие страхи оно снимает?
2. Какие вопросы остаются без ответа?
3. Есть ли конкретика или только «маркетинг»?
4. Структура удобна для сканирования?

Верни JSON:
{{
  "score": 1-10,
  "diagnosis": "краткий диагноз",
  "unanswered_questions": ["вопросы без ответа"],
  "recommendations": [
    {{"action": "добавить в описание X", "type": "description", "priority": "high/medium/low"}}
  ]
}}""",

    "reviews": """Прочитай отзывы и вопросы покупателей.

Отзывы:
{reviews}

Вопросы:
{questions}

Рейтинг: {rating}/5 ({reviews_count} отзывов)

Оцени:
1. Какие повторяющиеся плюсы? (сильные стороны)
2. Какие повторяющиеся минусы? (слабые места)
3. Есть ли ответы бренда на негатив?
4. Какой общий sentiment?

Верни JSON:
{{
  "score": 1-10,
  "diagnosis": "краткий диагноз",
  "recurring_positives": ["повторяющиеся плюсы"],
  "recurring_negatives": ["повторяющиеся минусы"],
  "unanswered_concerns": ["необработанный негатив"],
  "recommendations": [
    {{"action": "ответить на негатив про X", "type": "review_response", "priority": "high/medium/low"}}
  ]
}}"""
}


BLOCK_INFO = {
    "main_photo": {
        "name": "Главное фото",
        "emoji": "📸",
        "metrics": ["CTR", "Видимость в поиске"],
        "actionable": False,  # Can't change via API
    },
    "secondary_photos": {
        "name": "Доп. фото и видео",
        "emoji": "🖼",
        "metrics": ["CR", "Время в карточке"],
        "actionable": False,
    },
    "price_value": {
        "name": "Цена и ценность",
        "emoji": "💰",
        "metrics": ["CR", "Отказы"],
        "actionable": True,  # Can change price
        "experiment_type": "price",
    },
    "title": {
        "name": "Название",
        "emoji": "📝",
        "metrics": ["SEO трафик", "CTR"],
        "actionable": True,  # Can change via content experiment
        "experiment_type": "content",
        "field_type": "name",
    },
    "characteristics": {
        "name": "Характеристики",
        "emoji": "📋",
        "metrics": ["Трафик из фильтров", "CR"],
        "actionable": False,  # Complex to change via API
    },
    "description": {
        "name": "Описание",
        "emoji": "📄",
        "metrics": ["CR", "Возвраты"],
        "actionable": True,
        "experiment_type": "content",
        "field_type": "description",
    },
    "reviews": {
        "name": "Отзывы и Q&A",
        "emoji": "⭐",
        "metrics": ["CR", "Доверие алгоритма"],
        "actionable": False,  # Can't automate review responses
    },
}


async def evaluate_card_block(
    block_id: str,
    product_data: dict,
    openai_client,
) -> BlockEvaluation:
    """Evaluate a single block of the product card."""

    block_info = BLOCK_INFO[block_id]
    prompt_template = EVALUATION_PROMPTS[block_id]

    # Format prompt with product data
    prompt = prompt_template.format(**product_data)

    try:
        response = await openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "Ты эксперт по оптимизации карточек товаров на маркетплейсах. "
                              "Давай конкретные, actionable рекомендации. Отвечай только JSON."
                },
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        result = json.loads(response.choices[0].message.content)

        # Build recommendations with actionable flag
        recommendations = []
        for rec in result.get("recommendations", []):
            recommendations.append({
                "action": rec.get("action", ""),
                "description": rec.get("description", rec.get("action", "")),
                "priority": rec.get("priority", "medium"),
                "actionable": block_info["actionable"],
                "action_type": rec.get("type", block_info.get("experiment_type")),
                "new_value": rec.get("new_value"),
            })

        return BlockEvaluation(
            block_name=block_info["name"],
            block_id=block_id,
            score=result.get("score", 5),
            diagnosis=result.get("diagnosis", ""),
            recommendations=recommendations,
            metrics_affected=block_info["metrics"],
        )

    except Exception as e:
        logger.error(f"Failed to evaluate block {block_id}: {e}")
        return BlockEvaluation(
            block_name=block_info["name"],
            block_id=block_id,
            score=5,
            diagnosis=f"Ошибка оценки: {str(e)}",
            recommendations=[],
            metrics_affected=block_info["metrics"],
        )


def format_evaluation_report(evaluation: CardEvaluation) -> str:
    """Format evaluation as readable report."""

    report = f"🔍 **АУДИТ КАРТОЧКИ**\n\n"
    report += f"**{evaluation.product_name[:50]}**\n"
    report += f"📊 Общий балл: **{evaluation.overall_score:.1f}/10**\n\n"

    # Sort blocks by score (worst first)
    sorted_blocks = sorted(evaluation.blocks, key=lambda b: b.score)

    report += "━━━━━━━━━━━━━━━━━━━━━\n"

    for block in sorted_blocks:
        info = BLOCK_INFO[block.block_id]
        score_emoji = "🔴" if block.score < 5 else "🟡" if block.score < 7 else "🟢"
        actionable_tag = "⚡" if info["actionable"] else ""

        report += f"\n{info['emoji']} **{block.block_name}** {actionable_tag}\n"
        report += f"   {score_emoji} Оценка: {block.score}/10\n"
        report += f"   💬 {block.diagnosis}\n"

        if block.recommendations:
            report += f"   📌 Рекомендации:\n"
            for i, rec in enumerate(block.recommendations[:2], 1):
                priority_icon = "🔥" if rec["priority"] == "high" else "▫️"
                action_icon = "⚡" if rec["actionable"] else ""
                report += f"      {i}. {priority_icon} {rec['action']} {action_icon}\n"

        report += "\n"

    # Priority actions section
    if evaluation.priority_actions:
        report += "━━━━━━━━━━━━━━━━━━━━━\n"
        report += "🎯 **ТОП-3 ДЕЙСТВИЯ** (можно запустить экспериментом):\n\n"

        for i, action in enumerate(evaluation.priority_actions[:3], 1):
            report += f"{i}. **{action['block']}**: {action['action']}\n"
            if action.get('new_value'):
                report += f"   → Новое значение: _{action['new_value'][:50]}..._\n"
            report += f"   💡 Скажи: \"запусти эксперимент {action['experiment_hint']}\"\n\n"

    report += "━━━━━━━━━━━━━━━━━━━━━\n"
    report += "⚡ = можно запустить A/B эксперимент\n"
    report += "🔴 < 5 | 🟡 5-7 | 🟢 > 7\n"

    return report


def extract_priority_actions(blocks: list[BlockEvaluation], product_data: dict) -> list[dict]:
    """Extract top actionable recommendations."""

    actions = []

    for block in blocks:
        info = BLOCK_INFO[block.block_id]
        if not info["actionable"]:
            continue

        for rec in block.recommendations:
            if rec["priority"] == "high" and rec.get("actionable"):
                action = {
                    "block": block.block_name,
                    "block_id": block.block_id,
                    "action": rec["action"],
                    "action_type": info.get("experiment_type"),
                    "new_value": rec.get("new_value"),
                    "product_id": product_data.get("product_id"),
                    "offer_id": product_data.get("offer_id"),
                }

                # Generate experiment hint
                if info.get("experiment_type") == "content":
                    field = info.get("field_type", "name")
                    action["experiment_hint"] = f"с {field} для {product_data.get('product_name', 'товара')[:20]}"
                elif info.get("experiment_type") == "price":
                    action["experiment_hint"] = f"с ценой для {product_data.get('product_name', 'товара')[:20]}"

                actions.append(action)

    # Sort by score (worst blocks first)
    block_scores = {b.block_id: b.score for b in blocks}
    actions.sort(key=lambda a: block_scores.get(a["block_id"], 10))

    return actions[:3]
