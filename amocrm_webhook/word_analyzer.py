"""
Анализ фраз транскрипта на наличие слов из словаря.

Принимает две переменные:
    client_phrases   — строка с фразами клиента (разделены переносом строки)
    employee_phrases — строка с фразами сотрудника (разделены переносом строки)
"""

import re
from collections import defaultdict
import pymorphy3
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from connect import load_words_from_db
from text_utils import lemmatize_phrase

morph = pymorphy3.MorphAnalyzer()

# ─── Подготовка текста ────────────────────────────────────────────────────────

def prepare_text(phrases_str: str) -> str:
    """
    Принимает строку с фразами (разделены \n),
    объединяет в один текст и лемматизирует.
    """
    lines = [line.strip() for line in phrases_str.strip().split('\n') if line.strip()]
    full_text = ' '.join(lines)
    return lemmatize_phrase(full_text)

# ─── Поиск вхождений ──────────────────────────────────────────────────────────

def build_pattern(word: str) -> re.Pattern:
    """
    Строит regex для поиска слова/фразы в тексте.
    Использует границы по кириллице, чтобы не находить подстроки.
    """
    escaped = re.escape(word)
    return re.compile(rf'(?<![а-яёa-z]){escaped}(?![а-яёa-z])', re.IGNORECASE)

def find_mentions(text: str, words: list[dict]) -> dict[int, int]:
    """
    Ищет слова из словаря в тексте.
    Возвращает: {word_id: count}
    """
    mentions = defaultdict(int)

    for w in words:
        pattern = build_pattern(w['word'])
        matches = pattern.findall(text)
        if matches:
            mentions[w['word_id']] = len(matches)

    return dict(mentions)

# ─── Основная функция ─────────────────────────────────────────────────────────

def analyze_phrases(client_phrases: str, employee_phrases: str, words: list[dict]) -> dict:
    """
    Анализирует фразы клиента и сотрудника на наличие слов из словаря.

    Параметры:
        client_phrases   — строка с фразами клиента, разделёнными \n
        employee_phrases — строка с фразами сотрудника, разделёнными \n
        words            — список слов из словаря (из load_words_from_db)

    Возвращает:
        {
            "client":   {word_id: count, ...},
            "employee": {word_id: count, ...},
            "total":    {word_id: count, ...}   # сумма по обоим
        }
    """
    client_text   = prepare_text(client_phrases)
    employee_text = prepare_text(employee_phrases)

    client_mentions   = find_mentions(client_text, words)
    employee_mentions = find_mentions(employee_text, words)

    # Суммируем вхождения по обоим участникам
    all_word_ids = set(client_mentions) | set(employee_mentions)
    total = {
        wid: client_mentions.get(wid, 0) + employee_mentions.get(wid, 0)
        for wid in all_word_ids
    }

    return {
        "client":   client_mentions,
        "employee": employee_mentions,
        "total":    total,
    }

if __name__ == '__main__':
    client_phrases = """Здравствуйте, у вас забронировали на 4 часа, хотелось уточнить, а у вас в сменную обувь можно играть?

Я понял, поэтому уточняю, можно ли в сменную обувь у вас играть?

Ага, понятно, хорошо, спасибо."""

    employee_phrases = """Добрый день, реанимационная реальность, Анжелик, слушаю вас.

Вы будете играть в носочках.

Нет, у нас она в носочках именно.

До свидания."""

    # Мок-словарь для теста без БД
    # mock_words = [
    #     {"word_id": 1,  "word": lemmatize_phrase("забронировать"), "category_id": 1, "original": "забронировать"},
    #     {"word_id": 2,  "word": lemmatize_phrase("спасибо"),       "category_id": 2, "original": "спасибо"},
    #     {"word_id": 3,  "word": lemmatize_phrase("добрый день"),   "category_id": 2, "original": "добрый день"},
    #     {"word_id": 4,  "word": lemmatize_phrase("я вас слушаю"),  "category_id": 4, "original": "я вас слушаю"},
    #     {"word_id": 5,  "word": lemmatize_phrase("до свидания"),   "category_id": 2, "original": "до свидания"},
    #     {"word_id": 6,  "word": lemmatize_phrase("здравствуйте"), "category_id": 2, "original": "здравствуйте"},
    # ]
    words = load_words_from_db()

    print("Загружено слов из БД:", len(words))
    for w in words:
        print(f"  [{w['word_id']}] {w['original']} (лемма: {w['word']}, категория: {w['category_id']})")

    result = analyze_phrases(client_phrases, employee_phrases, words)

    print("=== Клиент ===")
    for word_id, count in result["client"].items():
        word = next(w["original"] for w in words if w["word_id"] == word_id)
        print(f"  [{word_id}] {word!r}: {count} раз")

    print("\n=== Сотрудник ===")
    for word_id, count in result["employee"].items():
        word = next(w["original"] for w in words if w["word_id"] == word_id)
        print(f"  [{word_id}] {word!r}: {count} раз")

    print("\n=== Итого ===")
    for word_id, count in result["total"].items():
        word = next(w["original"] for w in words if w["word_id"] == word_id)
        print(f"  [{word_id}] {word!r}: {count} раз")
