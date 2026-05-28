import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USE_AUTH_TOKEN_HUGGING_FACE = os.getenv("USE_AUTH_TOKEN_HUGGING_FACE")
TELEGRAM_CHAT_ID =  os.getenv("TELEGRAM_CHAT_ID")

# amoCRM настройки
AMO_DOMAIN = os.getenv("AMO_DOMAIN")
API_TOKEN_AMO = os.getenv("API_TOKEN_AMO")

# VK настройки
VK_TOKEN = os.getenv("VK_TOKEN")
ADMIN_ID_WR = os.getenv("ADMIN_ID_WR")

TOKEN_TEST = os.getenv("TOKEN_TEST")
ADMIN_ID_TEST = os.getenv("ADMIN_ID_TEST")
GROUP_ID_TEST = os.getenv("GROUP_ID_TEST")

#База данных 
DBNAME = os.getenv("DBNAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

## GigaChat
TOKEN_GIGACHAT = os.getenv("TOKEN_GIGACHAT")

# DEFAULT_LANGUAGE = "auto"
# DEFAULT_SUMMARY_STYLE = "default"

# SUPPORTED_LANGUAGES = {
#     "auto": "🌍 Автоматически",
#     "ru": "🇷🇺 Русский",
#     "en": "🇺🇸 English",
#     "de": "🇩🇪 Deutsch",
#     "fr": "🇫🇷 Français",
#     "es": "🇪🇸 Español",
# }

# SUMMARY_STYLES = {
#     "default": {"name": "📝 Стандартное", "prompt": "You are a helpful assistant. Summarize the user text concisely and informatively."},
#     "short": {"name": "🤏 Очень коротко (1-2 предложения)", "prompt": "You are a helpful assistant. Summarize the user text in one or two sentences."},
#     "bullet_points": {"name": "🔑 Ключевые пункты", "prompt": "You are a helpful assistant. Summarize the user text as a list of key bullet points."},
#     "detailed": {"name": "🧐 Подробное", "prompt": "You are a helpful assistant. Provide a detailed summary of the user text, covering all main aspects."}
# }

# WHISPER_MODEL_SIZE = "large"
# MAX_MESSAGE_LENGTH = 4096
# TRANSCRIPTION_DISPLAY_CHUNK_SIZE = 3800
# SUMMARY_DISPLAY_CHUNK_SIZE = 3800