# processing.py
import whisper
import torch
import torchaudio
import time
from collections import defaultdict
from pyannote.audio import Pipeline
from pyannote.audio.pipelines.utils.hook import ProgressHook
from config import USE_AUTH_TOKEN_HUGGING_FACE



import torchaudio.functional as F
import torchaudio.transforms as T


import soundfile as sf
from pedalboard import PitchShift, Chorus, Compressor, LadderFilter


def format_timestamp(seconds):
    minutes = int(seconds // 60)
    sec = int(seconds % 60)
    return f"{minutes}:{sec:02}"


def find_speaker_by_overlap(segment_start: float, segment_end: float, speakers: list) -> str | None:
    """
    Назначает спикера сегменту по максимальному перекрытию.

    Вместо поиска по медиане — считаем сколько секунд каждый спикер
    перекрывается с сегментом и берём того у кого больше.

    Если перекрытий нет — ищем ближайший сегмент диаризации по времени.
    """
    speaker_overlap: dict[str, float] = defaultdict(float)

    for s_start, s_end, speaker in speakers:
        overlap = max(0.0, min(segment_end, s_end) - max(segment_start, s_start))
        if overlap > 0:
            speaker_overlap[speaker] += overlap

    if speaker_overlap:
        return max(speaker_overlap, key=speaker_overlap.get)

    # Нет перекрытий — берём ближайший сегмент по середине
    segment_mid = (segment_start + segment_end) / 2
    nearest = min(speakers, key=lambda s: abs((s[0] + s[1]) / 2 - segment_mid))
    return nearest[2]


def get_speaker_list(diarization):
    speaker_list = []

    for segment, track, speaker in diarization.itertracks(yield_label=True):
        speaker_list.append([segment.start, segment.end, speaker])

    return speaker_list


def label_transcriptions(transcription, speakers):
    """
    Назначает спикеров сегментам транскрипта через overlap-логику.
    """
    labeled_transcriptions = []

    for segment in transcription["segments"]:
        speaker = find_speaker_by_overlap(segment["start"], segment["end"], speakers)

        if speaker is not None:
            labeled_transcriptions.append({
                "timestamp":     [segment["start"], segment["end"]],
                "text":          f"{speaker}: {segment['text'].strip()}",
                "speaker_label": speaker,
            })

    return {"all": labeled_transcriptions}


def get_speaker_stats(diarization):
    stats = defaultdict(lambda: {
        "phrases": 0,
        "speech_time": 0.0
    })

    total_speech_time = 0.0

    # diarization._tracks.items()
    for segment, track_info in diarization._tracks.items():

        # track_info выглядит так: {'A': 'SPEAKER_01'}
        speaker = list(track_info.values())[0]

        duration = segment.end - segment.start

        stats[speaker]["phrases"] += 1
        stats[speaker]["speech_time"] += duration

        total_speech_time += duration

    # Добавляем проценты
    for speaker in stats:
        speech_time = stats[speaker]["speech_time"]

        stats[speaker]["percent"] = (
            speech_time / total_speech_time * 100
            if total_speech_time > 0 else 0
        )

    return dict(stats)

def preprocess_audio(audio_path: str, output_path: str) -> str:
    """
    Конвертирует аудио в формат оптимальный для диаризации:
    - Моно канал
    - 16kHz (оптимально для pyannote)
    - Нормализация громкости
    - Сохраняет в wav (без артефактов mp3-декодирования)
    """

    waveform, sample_rate = torchaudio.load(audio_path)

     # Стерео → моно
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)

    # Ресемплинг до 16kHz (pyannote оптимизирован под него)
    if sample_rate != 16000:
        resampler = torchaudio.transforms.Resample(
            orig_freq=sample_rate,
            new_freq=16000
        )
        waveform = resampler(waveform)
        sample_rate = 16000

     # Нормализация громкости
    max_val = waveform.abs().max()
    if max_val > 0:
        waveform = waveform / (max_val + 1e-8)

    torchaudio.save(output_path, waveform, sample_rate)
    print(f"Аудио предобработано: {audio_path} → {output_path} ({sample_rate}Hz, моно)")
    return output_path

def transcribe_with_diarization(audio_path, whisper_model_path, hf_token,prompt="Это диалог между сотрудником арены виртуальной реальности Аназер Ворлд и клиентом."):

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    # Очищаем память от предыдущих моделей/пайплайнов, если они были
    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()


    try:
        model = whisper.load_model(whisper_model_path)
        model.eval()  # Переключаем в режим вывода
        print(f"Модель успешно загружена на {device}")
    except Exception as e:
        print(f"Ошибка загрузки модели: {e}")
        return None
    processed_path = "processed.wav"
    preprocess_audio(audio_path, processed_path)

    waveform, sample_rate = torchaudio.load(processed_path)

    diarization_pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=USE_AUTH_TOKEN_HUGGING_FACE
    )

    diarization_pipeline._segmentation.model  
    diarization_pipeline.instantiate({
        "clustering": {
            "method": "centroid",
            "min_cluster_size": 15,
            "threshold": 0.68,  
        },
        "segmentation": {
            "min_duration_off": 0.5,
        }
    })


    with ProgressHook() as hook:
        diarization = diarization_pipeline(
            {"waveform": waveform, "sample_rate": sample_rate},
            min_speakers=2,
            max_speakers=2,
            hook=hook
        )

    print(diarization)


    print("\n=== Статистика по спикерам ===")
    speaker_stats = get_speaker_stats(diarization)

    for speaker, data in speaker_stats.items():
        print(f"\n{speaker}")
        print(f"Фраз: {data['phrases']}")
        print(f"Время речи: {data['speech_time']:.2f} сек")
        print(f"Процент речи: {data['percent']:.2f}%")


# очищаем память от пайплайна, который больше не нужен, так как он может занимать много видеопамяти
    del diarization_pipeline
    torch.cuda.empty_cache()
#----------------------------------------
    start_time = time.time()
    result = model.transcribe(
        audio_path,
        language="ru",
        beam_size=5,
        word_timestamps=False,
        initial_prompt=prompt,
        condition_on_previous_text=True
    )
    print(result['text'])

    # with torch.amp.autocast('cuda', dtype=torch.float16), torch.no_grad():
    #     result = model.transcribe(
    #         audio_path,
    #         language="ru",
    #         initial_prompt=prompt,
    #         word_timestamps=False,  # Включаем тайминги для слов
    #         condition_on_previous_text=True  # Учитываем контекст
    #     )

    end_time = time.time()
    print(f"Время транскрибации: {end_time - start_time:.2f} секунд")

    speaker_list = get_speaker_list(diarization)
    print("speaker_list = " + str(speaker_list))
    labeled_transcriptions = label_transcriptions(result, speaker_list)
    print("labeled_transcriptions = " + str(labeled_transcriptions))


    # Формируем чистый текст
    full_text = ""
    for trans in labeled_transcriptions["all"]:
        ts = f"[{format_timestamp(trans['timestamp'][0])} - {format_timestamp(trans['timestamp'][1])}]"
        full_text += f"{trans['text']} {ts}\n"

    dialog_text = format_chat_dialog(labeled_transcriptions)
    print("dialog_text = " + dialog_text)

    return result["text"],dialog_text, labeled_transcriptions

def format_chat_dialog(labeled_transcriptions):
    """
    Преобразует массив сегментов в форматированный диалог.

    Формат:
    [00:01 - 00:04] Сотрудник:
        Добрый день...

    Возвращает готовую строку.
    """

    def sec_to_timestamp(sec):
        """Преобразование секунд → mm:ss"""
        minutes = int(sec // 60)
        seconds = int(sec % 60)
        return f"{minutes:02d}:{seconds:02d}"

    output_lines = []

    for item in labeled_transcriptions.get("all", []):
        start, end = item["timestamp"]
        role = item["speaker_label"]
        text = item["text"]

        # Убираем "Сотрудник: ..." дубль в тексте (если Whisper его добавил)
        if text.startswith(role + ":"):
            text = text[len(role) + 1:].strip()

        # Формирование блока
        output_lines.append(
            f"[{sec_to_timestamp(start)} - {sec_to_timestamp(end)}] {role}:\n"
            f"    {text}\n"
        )

    return "\n".join(output_lines)


# # Проверка CUDA
# device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
# print("="*50)
# print("Диагностика CUDA:")
# print(f"PyTorch версия: {torch.__version__}")
# print(f"CUDA доступна: {torch.cuda.is_available()}")
# if torch.cuda.is_available():
#     print(f"CUDA версия: {torch.version.cuda}")
#     print(f"GPU: {torch.cuda.get_device_name(0)}")

# audio_path = "./audio/1min 26sec.mp3"
# result,labeled_text, full_text = transcribe_with_diarization(
#     audio_path=audio_path,
#     whisper_model_path="C:/Users/123/.cache/whisper/large-v2.pt",
#     hf_token=USE_AUTH_TOKEN_HUGGING_FACE
# )

# print(labeled_text)

# print(full_text)


# if __name__ == "__main__":

#     audio_path = "C:\\Учеба\\bots tg\\voice_bot\\bot\\services\\10min.mp3"

#     result,labeled_text, full_text = transcribe_with_diarization(
#         audio_path=audio_path,
#         whisper_model_path="C:/Users/123/.cache/whisper/large-v2.pt",
#         hf_token=USE_AUTH_TOKEN_HUGGING_FACE
#     )























    # print("===================================large-v3-turbo========================================")

    # result,labeled_text, full_text = transcribe_with_diarization(
    #     audio_path=audio_path,
    #     whisper_model_path="C:/Users/123/.cache/whisper/large-v3-turbo.pt",
    #     hf_token=USE_AUTH_TOKEN_HUGGING_FACE
    # )

    # print("=================================medium==========================================")

    # result,labeled_text, full_text = transcribe_with_diarization(
    #     audio_path=audio_path,
    #     whisper_model_path="C:/Users/123/.cache/whisper/medium.pt",
    #     hf_token=USE_AUTH_TOKEN_HUGGING_FACE
    # )

    # print("=================================large-v3==========================================")

    # result,labeled_text, full_text = transcribe_with_diarization(
    #     audio_path=audio_path,
    #     whisper_model_path="C:/Users/123/.cache/whisper/large-v3.pt",
    #     hf_token=USE_AUTH_TOKEN_HUGGING_FACE
    # )


