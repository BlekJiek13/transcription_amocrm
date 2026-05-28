import json
import os
import re
import requests
from datetime import datetime
from threading import Lock

from bot.services.processing import transcribe_with_diarization
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_gigachat.chat_models import GigaChat

from connect import insert_call, insert_audio_file, insert_analysis_result, insert_transcription, get_employees, load_words_from_db, save_mentions
from amocrm_webhook.amo_api import get_lead_info_rest, post_note_lead_rest, is_lead_note
from amocrm_webhook.vk import send_vk_document, send_vk_message, build_employee_keyboard, send_vk_voice
from config import TOKEN_GIGACHAT, USE_AUTH_TOKEN_HUGGING_FACE, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from word_analyzer import analyze_phrases



AUDIO_FOLDER = os.path.join(os.path.dirname(__file__), "audio_files")
os.makedirs(AUDIO_FOLDER, exist_ok=True)

processing_lock = Lock()
MAX_MSG_LEN = 4000



def send_telegram_message(text, parse_mode="MarkdownV2"):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode
    }

    response = requests.post(url, data=payload)

    if not response.ok:
        print("Ошибка при отправке в Telegram:", response.text)


def escape_markdown(text: str) -> str:
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)


def get_audio_metadata(file_path: str):
    try:
        import torchaudio

        info = torchaudio.info(file_path)
        sample_rate = info.sample_rate
        num_frames = info.num_frames
        duration = None
        if sample_rate and num_frames is not None:
            duration = float(num_frames) / sample_rate
        return duration, sample_rate
    except Exception as e:
        print("Ошибка чтения метаданных аудио:", e)
        return None, None


def gigachat_analys(text: str):
    giga = GigaChat(
        credentials=TOKEN_GIGACHAT,
        model="GigaChat-2",
        verify_ssl_certs=False
    )

    messages = [
        SystemMessage(
            content=(
                "Ты — аналитическая модель арены виртуальной реальности Другие Миры (Another World). "
                "Тебе передаётся транскрипция телефонного диалога между сотрудником и клиентом. "
                "Твоя задача:\n"
                "1) Определи, какие реплики принадлежат сотруднику. \n"
                "2) Сформируй краткую выжимку содержания разговора (summary).\n"
                "3) Определи один тег категории диалога из списка: "
                "['Бронь игры', 'Уточнение', 'Консультация по ДР', 'Консультация по услугам', "
                "'Вопрос по ценам', 'Жалоба', 'Перенос брони', 'Отмена брони', "
                "'Подтверждение визита', 'Другое'].\n"
                "4) Если категория = \"Консультация по ДР\", выполни детальную проверку соблюдения сотрудником скрипта.\n"
                "Проверь, встречаются ли в репликах сотрудника следующие блоки:1)Приветствие,2)Выяснение потребности клиента,3)Рассказ про игры на арене,4)Информация про цены и свободные места,5)Описание полного процесса мероприятия от начала до конца (как проходит весь праздник),6)Описание процесса бронирования,7)Описание процедуры подтверждения брони,8)Информация о заполнении согласий на каждого игрока,9) Предложение продублировать информацию клиенту"
                "Для каждого из пунктов в script_details укажи true, если сотрудник озвучил этот блок, и false — если не озвучил.\n"
                "5) Оцени качество работы сотрудника по следующим отдельным критериям (каждый по шкале от 1 до 10):\n\n"
                "- greeting_politeness: оценка приветствия и вежливости;"
                "- need_identification: насколько сотрудник выявляет потребность клиента;"
                "- proactivity: активность и инициативность сотрудника;"
                "- tone_friendliness: тон общения и дружелюбие;"
                "Выводи их в JSON в поле \"criteria\".\n\n"
                "Выводи строго JSON:\n"
                "{\n"
                "  \"summary\": \"...\",\n"
                "  \"category\": \"...\",\n"
                "  \"criteria\": {\"greeting_politeness\": ..., \"need_identification\": ..., \"proactivity\": ..., \"\tone_friendliness\": ...},\n"
                "  \"speaker_map\": {\"SPEAKER_00\": \"Сотрудник/Клиент\", \"SPEAKER_01\": \"Сотрудник/Клиент\"}\n"
                "  \"script_details\": {\n"
                "    \"greeting\": \"...\",\n"
                "    \"need_identification_block\": \"...\",\n"
                "    \"arena_games_info\": \"...\",\n"
                "    \"prices_and_availability\": \"...\",\n"
                "    \"booking_process\": \"...\",\n"
                "    \"booking_confirmation\": \"...\",\n"
                "    \"consent_forms\": \"...\",\n"
                "    \"full_event_description\": \"...\",\n"
                "    \"offer\": \"...\" \n"
                "  },\n"
                "}\n\n"
                "Говори только по содержимому транскрипции, ничего не придумывай."
            )
        )
    ]

    messages.append(HumanMessage(content=text))
    res = giga.invoke(messages)
    return res.content


def format_chat_dialog(labeled_transcriptions, roles_dict):
    def sec_to_timestamp(sec):
        minutes = int(sec // 60)
        seconds = int(sec % 60)
        return f"{minutes:02d}:{seconds:02d}"

    output_lines = []
    employee_lines = []
    client_lines = []

    def is_employee(role: str) -> bool:
        role_norm = role.lower()
        return "сотруд" in role_norm or "менедж" in role_norm or "операт" in role_norm

    def is_client(role: str) -> bool:
        role_norm = role.lower()
        return "клиент" in role_norm or "гость" in role_norm or "покуп" in role_norm or "заказ" in role_norm

    for item in labeled_transcriptions.get("all", []):
        start, end = item["timestamp"]
        raw_role = item["speaker_label"]
        human_role = roles_dict.get(raw_role, raw_role)

        text = item["text"]
        if text.startswith(raw_role + ":"):
            text = text[len(raw_role) + 1:].strip()

        block_text = (
            f"[{sec_to_timestamp(start)} - {sec_to_timestamp(end)}] {human_role}:\n"
            f"    {text}"
        )
        output_lines.append(block_text)

        phrase_text = f"[{sec_to_timestamp(start)} - {sec_to_timestamp(end)}]    {text}"
        if is_employee(human_role):
            employee_lines.append(phrase_text)
        elif is_client(human_role):
            client_lines.append(phrase_text)

    final_dialog = "\n\n".join(output_lines)
    employee_phrases = "\n\n".join(employee_lines)
    client_phrases = "\n\n".join(client_lines)

    return final_dialog, employee_phrases, client_phrases


def generate_recommendations(script_details: dict) -> list:
    """Generate human-readable recommendations based on script_details dict."""
    recs = []
    mapping = {
        "greeting": "Приветствуйте клиента и представляйтесь.",
        "need_identification_block": "Уточняйте потребности клиента.",
        "arena_games_info": "Кратко расскажи об играх на арене и их уникальности.",
        "prices_and_availability": "Сообщи цены и наличие свободного времени.",
        "booking_process": "Объясни, как проходит бронирование.",
        "booking_confirmation": "Подтверждайте бронь вместе с клиентом.",
        "consent_forms": "Напоминайте о заполнении согласий участников.",
        "full_event_description": "Кратко объясняйте, как проходит мероприятие.",
        "offer": "Предлагайте дополнительные услуги и уточняйте важную информацию."
    }

    for key, advice in mapping.items():
        val = script_details.get(key)
        if not (val is True or str(val).lower() == "true"):
            recs.append({"item": key, "recommendation": advice})

    if not recs:
        recs.append({"ok": "Все пункты скрипта отмечены как выполненные."})

    return recs


def download_audio_file(url, filename):
    filepath = os.path.join(AUDIO_FOLDER, filename)

    print("Начинаем скачивание...")
    print("URL:", url)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "*/*"
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=30
        )
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type:
            print("❌ Получен HTML вместо файла (Google Drive блокирует скачивание)")
            return None

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)

        print("Файл успешно скачан:", filepath)
        return filepath

    except Exception as e:
        print("Ошибка скачивания:", e)
        return None


def process_webhook_async(form, note_id, lead_id):
    print("START HEAVY PROCESSING\n")

    try:
        if is_lead_note(form):
            if form.get("leads[note][0][note][note_type]") == "10":
                print(">>> СОБЫТИЕ: Добавлено примечание")

                note_type = form.get("leads[note][0][note][note_type]")
                text_raw = form.get("leads[note][0][note][text]")
                timestamp_str = form.get("leads[note][0][note][timestamp_x]")

                if timestamp_str:
                    dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                    timestamp_unix = int(dt.timestamp())

                text_dict = json.loads(text_raw)
                link = text_dict["LINK"]
                uniq = text_dict["UNIQ"]
                if link:
                    filename = f"{uniq}.mp3"
                    local_path_ = f"audio_files/{filename}"

                    if os.path.exists(local_path_):
                        print(text_dict)
                        print(f"⚠️ Файл {local_path_} уже существует — пропускаем дублирующий вебхук.")
                        return "duplicate"

                    local_path = download_audio_file(link, filename)
                    if local_path is None:
                        return "error_file"

                    file_format = os.path.splitext(filename)[1].lstrip('.').lower() or None
                    duration, sample_rate = get_audio_metadata(local_path)
                    file_id = insert_audio_file(
                        file_name=filename,
                        file_path=local_path,
                        file_format=file_format,
                        duration=duration,
                        sample_rate=sample_rate,
                        upload_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    )
                    call_id = insert_call(file_id,lead_id,note_id)

                print("ID сделки:", lead_id)
                print("ID примечания:", note_id)
                print("Тип примечания:", note_type)
                print("Текст примечания:", text_raw)

                get_lead_info_rest(lead_id)

                result, dialog_text, labeled_transcriptions = transcribe_with_diarization(
                    audio_path=local_path,
                    whisper_model_path="C:/Users/123/.cache/whisper/large-v2.pt",
                    hf_token=USE_AUTH_TOKEN_HUGGING_FACE,
                    prompt="Разговор сотрудника арены виртуальной реальности и клиента"
                )
                if result is None:
                    print("⚠️ Ошибка транскрибации, обработка остановена")
                    return "error"

                #final_dialog = "[00:01 - 00:03] Сотрудник:\n    Добрый день. Арена Виртуальной Реальности.\n[00:04 - 00:10] Клиент:\n    Здравствуйте. Подскажите, пожалуйста, ни разу вас не было, хотели по поводу дня рождения уточнить.\n[00:11 - 00:13] Клиент:\n    Сколько по времени, какая стоимость, сколько туалет.\n[00:14 - 00:15] Сотрудник:\n    На какой день планируете?\n[00:16 - 00:18] Клиент:\n    25 августа. Есть у вас места?\n[00:19 - 00:24] Сотрудник:\n    Так, на 25, если только на вечер есть. Вам удобно будет?\n[00:25 - 00:26] Клиент:\n    На сколько?\n[00:26 - 00:29] Сотрудник:\n    18.30\n[00:30 - 00:32] Клиент:\n    Да, нормально.\n[00:33 - 00:35] Сотрудник:\n    Сколько у вас игроков будет?\n[00:36 - 00:40] Клиент:\n    Так, у нас игроков получается 7.\n[00:41 - 00:44] Сотрудник:\n    Ну и взрослые, наверное, еще будут, да, играть?\n[00:45 - 00:52] Клиент:\n    Да, ну играть я не знаю, но то, что присутствовать, это точно. Вот я хотела уточнить.\n[00:53 - 00:56] Сотрудник:\n    А у нас на арене максимум 10 игроков.\n[00:57 - 00:59] Сотрудник:\n    Могут играть как и дети, так и взрослые.\n[01:00 - 01:02] Сотрудник:\n    Например, если взрослые захотят, могут также присоединиться к детям играть.\n[01:03 - 01:05] Сотрудник:\n    А какой возраст будет у детей?\n[01:06 - 01:13] Клиент:\n    Ну вот у меня дочке 10 лет исполняется. В основном 10, там 2, 14 и 15.\n[01:14 - 01:20] Сотрудник:\n    Ну главное, что у нас от 6 лет и выше, возможно.\n[01:21 - 01:25] Сотрудник:\n    По поводу тарифов, есть разные тарифы. Есть 2-часовой, 3-часовой и 4-часовой.\n[01:26 - 01:30] Сотрудник:\n    В основном берут тариф 3-часовой, называется у нас стандарт.\n[01:31 - 01:34] Сотрудник:\n    Он идет 3 часа и в нем включены 2 часа Aviariver.\n[01:35 - 01:37] Сотрудник:\n    То есть 2 сеанса по часу.\n[01:38 - 01:41] Сотрудник:\n    Также мы электронные пригласительные для ваших гостей делаем.\n[01:42 - 01:45] Сотрудник:\n    Подарок имениннику в конце и подарки домовым игрокам.\n[01:46 - 01:51] Сотрудник:\n    Получается по стоимости в будний день у нас 12900 стоит.\n[01:52 - 01:54] Клиент:\n    12900, да?\n[01:55 - 02:00] Сотрудник:\n    Да, это получается мероприятие 3-часовое и из них будет 2 часа игры.\n[02:01 - 02:05] Клиент:\n    А комнаты есть, да, куда могут играть?\n[02:05 - 02:10] Сотрудник:\n    Да, также будет комната отдыха вся в вашем распоряжении на все 3 часа.\n[02:11 - 02:15] Сотрудник:\n    Там будет 2 больших стола, также телевизор, Playstation, у нас там не игры.\n[02:16 - 02:19] Сотрудник:\n    Есть кухонная зона, холодильник, микроволновка, чайник.\n[02:20 - 02:22] Клиент:\n    Все есть.\n[02:23 - 02:25] Клиент:\n    То есть я ничего больше не доплачиваю?\n[02:26 - 02:28] Клиент:\n    Да, вот 12900 это за все.\n[02:29 - 02:32] Сотрудник:\n    Это у вас будет комната и 2 игры по часу для детей.\n[02:33 - 02:35] Клиент:\n    Угу, хорошо, ладно.\n[02:36 - 02:39] Клиент:\n    Получается вы с собой приносите только еду?\n[02:40 - 02:45] Клиент:\n    Так, а в этой комнате, например, если я там сколько человек могут находиться?\n[02:46 - 02:49] Сотрудник:\n    У нас вместимость человек 18.\n[02:52 - 02:54] Клиент:\n    Так что можете, главное не больше 20 человек.\n[02:55 - 02:58] Клиент:\n    Нет, у меня просто там, да, нет, нет, там так не будет.\n[02:59 - 03:00] Клиент:\n    Все, я поняла.\n[03:00 - 03:03] Клиент:\n    Так, предоплата или что-то там нужно?\n[03:04 - 03:07] Сотрудник:\n    Работаем без предоплаты, у нас плата по факту.\n[03:08 - 03:11] Сотрудник:\n    Мы сейчас для вас можем забронировать время, а мы останемся за вами.\n[03:12 - 03:14] Сотрудник:\n    Вот, а плата будет уже на месяц полностью.\n[03:15 - 03:20] Клиент:\n    Угу, хорошо, давайте тогда наличными переводим, есть чем вам нравится?\n[03:21 - 03:24] Сотрудник:\n    Да, да, как угодно сделаешь наличными переводами.\n[03:24 - 03:30] Клиент:\n    Угу, сейчас я тогда все быстренько с мужем пообсуждаю и вам сразу перезвоню.\n[03:31 - 03:36] Сотрудник:\n    Да, а хорошо, если что, вот время на 18.30 есть, либо 18.30.\n[03:37 - 03:39] Клиент:\n    18.30, с полседьмого.\n[03:40 - 03:43] Сотрудник:\n    Да, с полседьмого до полдесятого получается мероприятие будет проходить.\n[03:44 - 03:45] Клиент:\n    С полседьмого до полдесятого.\n[03:46 - 03:48] Сотрудник:\n    Это вот там единственное время вот свободно на понедельник.\n[03:49 - 03:53] Клиент:\n    Угу, с полседьмого до полдесятого, лишь бы детей отпустили.\n[03:54 - 03:58] Клиент:\n    Ладно, сейчас тогда будем решать, я перезвоню, спасибо.\n[03:59 - 04:01] Сотрудник:\n    Угу, ну все, хорошо, тогда ждем звонком.\n[04:02 - 04:03] Клиент:\n    Угу, хорошо, до свидания.\n[04:04 - 04:05] Сотрудник:\n    До свидания."


                #print(dialog_text)
                print("---------------------------------------------------------------------------------")

                #------анализ гигачатом-----
                print("Анализ GigaChat\n")
                #response_giga = gigachat_analys(dialog_text)

                response_giga = """
                {
                "summary": "Клиент обратился с вопросом о проведении дня рождения на арене виртуальной реальности. Обсудили количество участников, продолжительность мероприятия, наличие свободных мест, стоимость и дополнительные услуги. Сотрудник предложил забронировать место и уточнил способы оплаты.",
                "category": "Консультация по ДР",
                "criteria": {
                    "greeting_politeness": 9,
                    "need_identification": 8,
                    "proactivity": 7,
                    "tone_friendliness": 8
                },
                "speaker_map": {
                    "SPEAKER_00": "Сотрудник",
                    "SPEAKER_01": "Клиент"
                },
                "script_details": {
                    "greeting": true,
                    "need_identification_block": true,
                    "arena_games_info": false,
                    "prices_and_availability": true,
                    "booking_process": true,
                    "booking_confirmation": false,
                    "consent_forms": false,
                    "full_event_description": false,
                    "offer": true
                }
                }
                """


                if isinstance(response_giga, str):
                    response_giga = json.loads(response_giga)

                note_text = (
                    f"Категория звонка: {response_giga['category']}\n"
                    f"Краткое изложение: {response_giga['summary']}"
                )

                post_note_lead_rest(lead_id, note_text)

                message = (
                    f"🆕 <b>Новая транскрипция звонка</b>\n\n"
                    f"💼 <b>Сделка:</b> https://awsaransk.amocrm.ru/leads/detail/{lead_id}\n"
                    f"🎧 <b>Аудиофайл:</b> {link}\n\n"
                    f"📝 <b>Итоги анализа:</b>\n"
                    f"• Категория: {response_giga['category']}\n"
                    f"📊 <b>Оценка по критериям:</b>\n"
                    f"• Приветствие и вежливость: {response_giga['criteria']['greeting_politeness']} / 10\n"
                    f"• Выявление потребности: {response_giga['criteria']['need_identification']} / 10\n"
                    f"• Инициативность: {response_giga['criteria']['proactivity']} / 10\n"
                    f"• Дружелюбие: {response_giga['criteria']['tone_friendliness']} / 10\n"
                    f"• Кратко: {response_giga['summary']}\n\n"
                    f"\n"
                )

                if response_giga['category'] == "Консультация по ДР":
                    script_details = response_giga.get("script_details", {})

                    def mark(val):
                        if val is True or str(val).lower() == "true":
                            return "✅"
                        return "❌"

                    message += (
                        f"📝 <b>Проверка выполнения скрипта:</b>\n"
                        f"• Приветствие: {mark(script_details.get('greeting'))}\n"
                        f"• Выявление потребности: {mark(script_details.get('need_identification_block'))}\n"
                        f"• Информация про игры: {mark(script_details.get('arena_games_info'))}\n"
                        f"• Цены и доступность: {mark(script_details.get('prices_and_availability'))}\n"
                        f"• Процесс бронирования: {mark(script_details.get('booking_process'))}\n"
                        f"• Подтверждение брони: {mark(script_details.get('booking_confirmation'))}\n"
                        f"• Согласия участников: {mark(script_details.get('consent_forms'))}\n"
                        f"• Полное описание мероприятия: {mark(script_details.get('full_event_description'))}\n"
                        f"• Предложение дублировать информацию: {mark(script_details.get('offer'))}\n\n"
                    )

                final_dialog, employee_phrases, client_phrases = format_chat_dialog(
                    labeled_transcriptions,
                    response_giga.get("speaker_map", {})
                )

                print("--------Диалог восстановлен--------\n")
                print(final_dialog)
                
                print("-----Фразы клиента------\n")
                print(client_phrases)
                
                print("-----Фразы сотрудника------\n")
                print(employee_phrases)

                words = load_words_from_db()

                #----Просмотр загруженных слов из бд ----

                # print("Загружено слов из БД:", len(words))
                # for w in words:
                #     print(f"  [{w['word_id']}] {w['original']} (лемма: {w['word']}, категория: {w['category_id']})")
                
                #---- /Просмотр загруженных слов из бд/ ----

                result_analyze_phrases = analyze_phrases(client_phrases, employee_phrases, words)
                
                print("=== Клиент ===")
                for word_id, count in result_analyze_phrases["client"].items():
                    word = next(w["original"] for w in words if w["word_id"] == word_id)
                    print(f"  [{word_id}] {word!r}: {count} раз")

                print("\n=== Сотрудник ===")
                for word_id, count in result_analyze_phrases["employee"].items():
                    word = next(w["original"] for w in words if w["word_id"] == word_id)
                    print(f"  [{word_id}] {word!r}: {count} раз")

                print("\n=== Итого ===")
                for word_id, count in result_analyze_phrases["total"].items():
                    word = next(w["original"] for w in words if w["word_id"] == word_id)
                    print(f"  [{word_id}] {word!r}: {count} раз")

                # Сохраняем статистику слов (client и employee в одной записи JSONB)
                save_mentions(call_id, result_analyze_phrases["client"], result_analyze_phrases["employee"])



                #---------------------------------------------------------------------------------

                try:
                    # Сохраняем транскрипт в таблицу `transcriptions`
                    transcription_id = insert_transcription(
                        call_id=call_id,
                        labeled_text=final_dialog,
                        client_phrases=client_phrases,
                        employee_phrases=employee_phrases
                    )
                    print("Inserted transcription id:", transcription_id)
                except Exception as e:
                    print("Ошибка при сохранении транскрипта в БД:", e)
                # Сохраняем результаты анализа в таблицу analysis_results
                try:
                    criteria = response_giga.get("criteria", {}) if isinstance(response_giga, dict) else {}
                    vals = [float(v) for v in criteria.values() if isinstance(v, (int, float)) or (isinstance(v, str) and v.replace('.', '', 1).isdigit())]
                    score = round(sum(vals) / len(vals), 2) if vals else None

                    script_details = response_giga.get("script_details", {}) if isinstance(response_giga, dict) else {}
                    total_checks = len(script_details)
                    passed = sum(1 for v in script_details.values() if v is True or (isinstance(v, str) and v.lower() == "true"))
                    script_compliance_pct = round((passed / total_checks) * 100, 2) if total_checks > 0 else None

                    recommendations = generate_recommendations(script_details)
                    summary = response_giga.get("summary") if isinstance(response_giga, dict) else None

                    db_call_id = call_id if 'call_id' in locals() else None
                    if db_call_id is not None:
                        insert_analysis_result(
                            call_id=db_call_id,
                            score=score,
                            summary=summary,
                            criteria_json={"criteria": criteria} if criteria else None,
                            recommendations_json={"recommendations": recommendations},
                            script_compliance_pct=script_compliance_pct,
                            category_call=response_giga.get("category") if isinstance(response_giga, dict) else None
                        )
                except Exception as e:
                    print("Ошибка при сохранении анализа в БД:", e)


                #    получаем сотрудников из бд и делаем клаву в вк
                employees = get_employees()
                ###########################################


                if len(final_dialog) + len(message) > MAX_MSG_LEN:
                    print("\n⚠️ Диалог слишком длинный, отправляем файлом.\n")

                    dialog_folder = os.path.join(AUDIO_FOLDER, "dialog")
                    os.makedirs(dialog_folder, exist_ok=True)

                    dialog_file_path = os.path.join(dialog_folder, f"dialog_{uniq}.txt")

                    with open(dialog_file_path, "w", encoding="utf-8") as f:
                        f.write(final_dialog)

                    vk = True
                    tg = False

                    if vk:

                        send_vk_message(message, keyboard=build_employee_keyboard(employees,call_id))
                        send_vk_voice(local_path)
                        send_vk_document(dialog_file_path)
                    elif tg:
                        send_telegram_message(message, parse_mode="HTML")
                        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
                        with open(dialog_file_path, "rb") as doc:
                            requests.post(
                                url,
                                data={"chat_id": TELEGRAM_CHAT_ID},
                                files={"document": doc}
                            )
                else:
                    message += f"💬 <b>Диалог:</b>\n<pre>{final_dialog}</pre>"
                    send_vk_message(message, keyboard=build_employee_keyboard(employees,call_id))
                    send_vk_voice(local_path)

                return "note_ok"
    except Exception as e:
        print("Ошибка:", e)
        return "error"
