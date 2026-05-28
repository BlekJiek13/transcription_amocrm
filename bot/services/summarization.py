import g4f
from config import SUMMARY_STYLES


async def generate_summary(text: str, style_key: str) -> str:
    style_info = SUMMARY_STYLES.get(style_key, SUMMARY_STYLES["default"])
    system_prompt = style_info["prompt"]

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]
    try:
        response = await g4f.ChatCompletion.create_async(
            model=g4f.models.gpt_4o_mini,
            messages=messages,
            stream=False
        )
        if response and isinstance(response, str) and response.strip():
            return response.strip()
        else:
            return "⚠️ Ошибка: пустой или некорректный ответ от LLM."
    except Exception as e:
        return f"⚠️ Не удалось получить ответ от LLM: {str(e)}"

