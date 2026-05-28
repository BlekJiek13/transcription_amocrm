# handlers/common_handlers.py
from aiogram import Router, F, types
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.utils.markdown import hbold

from keyboards.inline import get_main_settings_keyboard
from states.user_states import SettingsStates
from config import DEFAULT_LANGUAGE, DEFAULT_SUMMARY_STYLE, SUPPORTED_LANGUAGES, \
    SUMMARY_STYLES

router = Router()


def get_user_settings(user_id: int, dp_user_settings: dict):
    if user_id not in dp_user_settings:
        dp_user_settings[user_id] = {
            "language": DEFAULT_LANGUAGE,
            "summary_style": DEFAULT_SUMMARY_STYLE,
            "summary_style_name": SUMMARY_STYLES[DEFAULT_SUMMARY_STYLE]["name"]
        }
    elif 'summary_style_name' not in dp_user_settings[user_id]:
        current_style_key = dp_user_settings[user_id].get('summary_style', DEFAULT_SUMMARY_STYLE)
        dp_user_settings[user_id]['summary_style_name'] = \
        SUMMARY_STYLES.get(current_style_key, SUMMARY_STYLES[DEFAULT_SUMMARY_STYLE])["name"]
    return dp_user_settings[user_id]


@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext, user_settings: dict):
    await state.clear()
    current_user_settings = get_user_settings(message.from_user.id, user_settings)

    user_name = message.from_user.first_name or "пользователь"
    #_, device = whisper_model

    current_summary_style_name = current_user_settings.get('summary_style_name', SUMMARY_STYLES[DEFAULT_SUMMARY_STYLE]["name"])

    text = (
        f"👋 Привет, {hbold(user_name)}!\n\n"
        "Я твой ИИ-ассистент, который умеет:\n"
        "1️⃣ 🗣️ Принимать голосовые (.ogg) и аудио (.mp3, .wav, etc.) сообщения.\n"
        "2️⃣ ✍️ Транскрибировать их с помощью Whisper.\n"
        "3️⃣ 💡 Генерировать краткое резюме текста с помощью LLM.\n\n"
        f"🔹 Текущий язык транскрибации: {hbold(SUPPORTED_LANGUAGES.get(current_user_settings['language'], 'Авто'))}\n"
        f"🔹 Текущий стиль резюме: {hbold(current_summary_style_name)}\n"
        #f"🔬 Whisper работает на: {hbold(device.upper())}\n\n"
        "➡️ Отправь мне голосовое, аудио или текстовое сообщение для обработки.\n"
        "⚙️ Используй /settings для изменения настроек."
    )
    await message.answer(text)


@router.message(Command("help"))
async def cmd_help(message: types.Message, user_settings: dict):
    current_user_settings = get_user_settings(message.from_user.id, user_settings)
    current_lang_name = SUPPORTED_LANGUAGES.get(current_user_settings['language'], "Авто")

    current_style_key = current_user_settings.get('summary_style', DEFAULT_SUMMARY_STYLE)
    current_style_name = SUMMARY_STYLES.get(current_style_key, SUMMARY_STYLES[DEFAULT_SUMMARY_STYLE])["name"]

    text = (
        "ℹ️ <b>Справка по боту:</b>\n\n"
        "📝 <b>Основные функции:</b>\n"
        "- Транскрибация голосовых и аудио сообщений.\n"
        "- Суммаризация (краткое изложение) транскрибированного или введенного текста.\n\n"
        "🎤 <b>Как пользоваться:</b>\n"
        "1.  Отправьте голосовое сообщение (запись из Telegram) или аудиофайл.\n"
        "2.  Или просто отправьте текстовое сообщение, которое нужно суммировать.\n"
        "3.  Бот автоматически обработает ваш запрос и пришлет результат.\n\n"
        "⚙️ <b>Настройки (/settings):</b>\n"
        f"- <b>Язык транскрибации:</b> Сейчас \"{current_lang_name}\". Влияет на точность распознавания речи. 'Авто' обычно работает хорошо.\n"
        f"- <b>Стиль резюме:</b> Сейчас \"{current_style_name}\". Определяет, насколько подробным будет краткое изложение.\n\n"
        "❌ <b>Отмена:</b> Команда /cancel позволяет прервать некоторые текущие операции (например, выбор настроек)."
    )
    await message.answer(text)


@router.message(Command("settings"))
async def cmd_settings(message: types.Message, state: FSMContext):
    await state.set_state(SettingsStates.MAIN_SETTINGS_MENU)
    await message.answer("⚙️ <b>Настройки бота</b>\n\nВыберите, что вы хотите настроить:",
                         reply_markup=get_main_settings_keyboard())


@router.callback_query(F.data == "settings:close", SettingsStates.MAIN_SETTINGS_MENU)
async def cq_settings_close(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("👌 Настройки закрыты.")
    await callback.answer()


@router.message(Command("cancel"))
@router.callback_query(F.data == "cancel_state")
async def cmd_cancel(event: types.Message | types.CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        text = "🤷 Нет активных действий для отмены."
        if isinstance(event, types.Message):
            await event.answer(text)
        else:
            await event.answer(text, show_alert=True)
        return

    await state.clear()
    text = "✅ Действие отменено."
    if isinstance(event, types.Message):
        await event.answer(text)
    elif isinstance(event, types.CallbackQuery) and event.message:
        try:
            await event.message.edit_text(text)
        except Exception:
            await event.message.answer(text)
        await event.answer()


@router.message(F.text.startswith('/'))
async def unhandled_command_fallback(message: types.Message):
    await message.reply("😕 Неизвестная команда. Попробуйте /start или /help.")