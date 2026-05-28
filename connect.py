import psycopg2
import psycopg2.extras
from config import DBNAME,DB_USER,DB_PASSWORD,DB_HOST,DB_PORT
from amocrm_webhook.text_utils import lemmatize_phrase

def get_connection():
    return psycopg2.connect(
        dbname=DBNAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )

def insert_call(file_id,id_lead,id_note):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO calls (file_id,id_lead, id_note)
        VALUES (%s, %s, %s)
        RETURNING call_id
    """, (file_id, id_lead, id_note))

    call_id = cur.fetchone()[0]

    conn.commit()

    cur.close()
    conn.close()

    return call_id

def call_exists(id_note, id_lead):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT 1 FROM calls
        WHERE id_note = %s AND id_lead = %s
        LIMIT 1
    """, (id_note, id_lead))

    exists = cur.fetchone() is not None

    cur.close()
    conn.close()
    return exists


def insert_audio_file(file_name: str, file_path: str, file_format: str = None,
                      duration: float = None, sample_rate: int = None,
                      upload_date: str = None) -> int:
    """
    Insert audio file metadata into `audiofiles` table and return generated `file_id`.

    :param file_name: filename (varchar)
    :param file_path: path to file (varchar)
    :param file_format: file extension / format (varchar(10))
    :param duration: duration in seconds (numeric)
    :param sample_rate: audio sample rate (int)
    :param upload_date: optional timestamp string (if None DB default/CURRENT_TIMESTAMP used)
    :return: inserted file_id (int)
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO audiofiles (file_name, file_path, file_format, duration, sample_rate, upload_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING file_id
    """, (file_name, file_path, file_format, duration, sample_rate, upload_date))

    file_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return file_id


def insert_transcription(call_id: int = None, labeled_text: str = None,
                         client_phrases: str = None, employee_phrases: str = None) -> int:
    """
    Insert a transcription record into `transcriptions` and return generated id.

    :param file_id: reference to audiofiles.file_id
    :param labeled_text: full labeled transcription text (raw)
    :param client_phrases: concatenated client phrases with timestamps
    :param employee_phrases: concatenated employee phrases with timestamps
    :return: transcription_id
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO transcriptions (call_id, labeled_text, client_phrases, employee_phrases)
        VALUES (%s, %s, %s, %s)
        RETURNING transcription_id
    """, (call_id, labeled_text, client_phrases, employee_phrases))

    transcription_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return transcription_id


def insert_analysis_result(call_id: int, score: float = None, summary: str = None,
                           criteria_json: dict = None,
                           recommendations_json: dict = None,
                           script_compliance_pct: float = None,
                           category_call: str = None) -> int:
    """
    Insert analysis result into `analysis_results` and return generated result_id.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO analysis_results
            (call_id, score, summary, criteria_json, recommendations_json, script_compliance_pct, category_call)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        RETURNING result_id
    """, (
        call_id,
        score,
        summary,
        psycopg2.extras.Json(criteria_json) if criteria_json is not None else None,
        psycopg2.extras.Json(recommendations_json) if recommendations_json is not None else None,
        script_compliance_pct,
        category_call
    ))

    result_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return result_id

def get_employees():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("""
        SELECT employee_id, fio, vk_id
        FROM employees
        ORDER BY employee_id
    """)

    rows = cur.fetchall()

    cur.close()
    conn.close()

    return rows




# ─── Загрузка словаря ─────────────────────────────────────────────────────────

def load_words_from_db() -> list[dict]:
    """
    Загружает активные слова из БД и лемматизирует их.
    Возвращает список: [{"word_id": 1, "word": "забронировать", "category_id": 1}, ...]
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT w.word_id, w.word, w.category_id
            FROM words w
            WHERE w.is_active = true
        """)
        rows = cur.fetchall()

    return [
        {
            "word_id":     row[0],
            "word":        lemmatize_phrase(row[1]),  # нормализуем словарь
            "category_id": row[2],
            "original":    row[1],
        }
        for row in rows
    ]

# ─── Сохранение в БД ──────────────────────────────────────────────────────────

def save_mentions(call_id: int, mentions_client: dict[int, int], mentions_employee: dict[int, int]) -> None:
    """
    Сохраняет результаты анализа слов в таблицу call_word_mentions в виде JSONB.
    
    Структура данных:
    {
        "client": {"10": 1, "17": 2},
        "employee": {"17": 2, "24": 1}
    }
    
    :param call_id: ID звонка
    :param mentions_client: dict {word_id: count} для клиента
    :param mentions_employee: dict {word_id: count} для сотрудника
    """
    if not mentions_client and not mentions_employee:
        return

    conn = get_connection()
    
    with conn.cursor() as cur:
        # Преобразуем ключи int -> str (JSON требует строковых ключей)
        words_data = {
            "client": {str(k): v for k, v in mentions_client.items()},
            "employee": {str(k): v for k, v in mentions_employee.items()}
        }
        
        cur.execute("""
            INSERT INTO call_word_mentions (call_id, words_data)
            VALUES (%s, %s)
            ON CONFLICT (call_id) 
            DO UPDATE SET words_data = EXCLUDED.words_data
        """, (
            call_id,
            psycopg2.extras.Json(words_data)
        ))

    conn.commit()
    conn.close()
