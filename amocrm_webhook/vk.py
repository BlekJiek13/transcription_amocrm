import vk_api
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from datetime import datetime
import logging
import sys
import os
import requests
import json
from pydub import AudioSegment

# Добавляем корневую папку проекта в путь импорта (чтобы видеть config)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Теперь импортируем из config
try:
    from config import VK_TOKEN, ADMIN_ID_WR, TOKEN_TEST, ADMIN_ID_TEST, GROUP_ID_TEST
except ImportError:
    print("❌ Не удалось импортировать VK_TOKEN и ADMIN_VK_ID из config.py")
    print("Проверь путь к config.py или добавь настройки вручную ниже.")
    VK_TOKEN = None
    ADMIN_VK_ID = None
    TOKEN_TEST = None
    ADMIN_ID_TEST = None
    GROUP_ID_TEST = None

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    force=True
)

logger = logging.getLogger(__name__)

class VKSender:
    def __init__(self, token: str, admin_id: int):
        self.token = token
        self.admin_id = admin_id
        self.vk = None
        self._init_vk()

    def _init_vk(self):
        if not self.token:
            logger.error("Токен VK не задан")
            return
        try:
            vk_session = vk_api.VkApi(token=self.token)
            self.vk = vk_session.get_api()
            # Проверка токена
            self.vk.users.get(user_ids=1)
            logger.info("VK API успешно инициализирован и токен работает")
        except Exception as e:
            logger.error(f"Ошибка инициализации VK API: {e}")
            self.vk = None

    def send_message(self, text: str, user_id: int = None,  keyboard_json: str = "") -> bool:
        if self.vk is None:
            logger.error("VK API не инициализирован")
            return False

        if user_id is None:
            user_id = self.admin_id

        try:
            random_id = int(datetime.now().timestamp() * 1000000)

                # Приводим keyboard к строке JSON
            if isinstance(keyboard_json, dict):
                keyboard_str = json.dumps(keyboard_json, ensure_ascii=False)
            elif isinstance(keyboard_json, str) and keyboard_json:
                keyboard_str = keyboard_json
            else:
                keyboard_str = ""

            self.vk.messages.send(
                user_id=user_id,
                message=text.strip(),
                random_id=random_id,
                keyboard=keyboard_str
            )
            logger.info(f"Сообщение отправлено в VK пользователю {user_id}")
            return True

        except Exception as e:
            logger.error(f"Ошибка отправки сообщения в VK: {e}")
            return False
    

    def send_voice_message(self, file_path: str, message: str = "", user_id: int = None) -> bool:
        if user_id is None:
            user_id = self.admin_id

        try:
            upload_server = self.vk.docs.getMessagesUploadServer(
                type="audio_message",
                peer_id=user_id
            )

            with open(file_path, "rb") as file:
                response = requests.post(upload_server["upload_url"], files={"file": file})

            upload_result = response.json()

            saved = self.vk.docs.save(
                file=upload_result["file"],
                title=os.path.basename(file_path)
            )

            doc = saved["audio_message"]  # не "doc", а "audio_message"
            attachment = f"doc{doc['owner_id']}_{doc['id']}"

            self.vk.messages.send(
                user_id=user_id,
                message=message,
                attachment=attachment,
                random_id=int(datetime.now().timestamp() * 1000000)
            )
            return True

        except Exception as e:
            logger.error(f"Ошибка отправки голосового: {e}")
            return False
    

    def send_document(self, file_path: str, message: str = "", user_id: int = None) -> bool:
        if self.vk is None:
            logger.error("VK API не инициализирован")
            return False

        if user_id is None:
            user_id = self.admin_id

        try:
            # 1. Получаем upload server
            upload_server = self.vk.docs.getMessagesUploadServer(
                type="doc",
                peer_id=user_id
            )

            upload_url = upload_server["upload_url"]

            # 2. Загружаем файл
            with open(file_path, "rb") as file:
                response = requests.post(
                    upload_url,
                    files={"file": file}
                )

            upload_result = response.json()

            # 3. Сохраняем документ
            saved_doc = self.vk.docs.save(
                file=upload_result["file"],
                title=os.path.basename(file_path)
            )

            doc = saved_doc["doc"]

            attachment = f"doc{doc['owner_id']}_{doc['id']}"

            random_id = int(datetime.now().timestamp() * 1000000)

            # 4. Отправляем сообщение с файлом
            self.vk.messages.send(
                user_id=user_id,
                message=message,
                attachment=attachment,
                random_id=random_id
            )

            logger.info(f"Файл отправлен в VK: {file_path}")
            return True

        except Exception as e:
            logger.error(f"Ошибка отправки файла в VK: {e}")
            return False


# Создаём объект отправителя
vk_sender = VKSender(token=TOKEN_TEST, admin_id=ADMIN_ID_TEST)


def send_vk_message(text: str, keyboard=None) -> bool:
    keyboard_payload = keyboard if keyboard is not None else ""
    return vk_sender.send_message(text, keyboard_json=keyboard_payload)

def send_vk_voice(file_path: str, message: str = "") -> bool:
    """Конвертирует аудио в OGG и отправляет как голосовое сообщение."""
    try:
        ogg_path = convert_to_ogg(file_path)
        return vk_sender.send_voice_message(ogg_path, message)
    except Exception as e:
        logger.error(f"Ошибка подготовки голосового сообщения: {e}")
        return False
    
def send_vk_document(file_path: str, message: str = "") -> bool:
    return vk_sender.send_document(file_path, message)

def build_employee_keyboard(employees: list, call_id: int) -> str:
    keyboard = VkKeyboard(inline=True)

    for i, employee in enumerate(employees):
        keyboard.add_button(employee["fio"], color=VkKeyboardColor.PRIMARY, payload={"employee_id": employee["employee_id"], "call_id": call_id})
        if i < len(employees) - 1:
            keyboard.add_line()

    return keyboard.get_keyboard()

def convert_to_ogg(input_path: str, output_path: str = None) -> str:
    if output_path is None:
        output_path = input_path.rsplit(".", 1)[0] + ".ogg"
    
    AudioSegment.from_file(input_path).export(
        output_path, 
        format="ogg", 
        codec="libopus"
    )
    return output_path
# ====================== ТЕСТ ПРИ ЗАПУСКЕ ======================
# if __name__ == "__main__":
#     print("Запуск проверки vk.py...")
#     if VK_TOKEN and ADMIN_ID_WR:
#         success = send_vk_message("Тестовое сообщение из vk.py\nПроверка соединения с VK.")
#         if success:
#             print("✅ Тестовое сообщение отправлено успешно!")
#         else:
#             print("❌ Не удалось отправить тестовое сообщение.")
#     else:
#         print("❌ Токен или ADMIN_ID_WR не загружены.")