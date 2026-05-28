import re
import pymorphy3

morph = pymorphy3.MorphAnalyzer()


# ─── Лемматизация ─────────────────────────────────────────────────────────────

def lemmatize_word(word: str) -> str:
    """Приводит одно слово к нормальной форме."""
    return morph.parse(word)[0].normal_form


def lemmatize_phrase(phrase: str) -> str:
    """Приводит все слова фразы к нормальной форме."""
    tokens = re.findall(r'[а-яёА-ЯЁa-zA-Z]+', phrase.lower())
    return ' '.join(lemmatize_word(t) for t in tokens)