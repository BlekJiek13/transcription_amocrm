# main_bot.py
import asyncio
import os
import logging

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from aiogram import Bot, Dispatcher, types
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from dotenv import load_dotenv

from handlers import common_handlers, settings_handlers, voice_audio_handler, text_input_handler
from keyboards.command_menu import set_main_menu
from services.transcription import load_whisper_model
from config import TELEGRAM_BOT_TOKEN


async def main():
    load_dotenv()

    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp['user_settings'] = {}
    #dp['whisper_model'] = load_whisper_model()

    await set_main_menu(bot)

    dp.include_router(common_handlers.router)
    dp.include_router(settings_handlers.router)
    dp.include_router(voice_audio_handler.router)
    dp.include_router(text_input_handler.router)

    logging.basicConfig(level=logging.INFO)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
