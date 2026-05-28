import whisper
import torch
import warnings
from config import WHISPER_MODEL_SIZE

warnings.filterwarnings("ignore", message="FP16 is not supported on CPU; using FP32 instead")


def load_whisper_model():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Whisper model loading on: {device}")
    model = whisper.load_model(WHISPER_MODEL_SIZE, device=device)
    print("Whisper model loaded.")
    return model, device


async def transcribe_audio(model, file_path: str, language: str = None) -> str:
    if language == "auto" or language is None:
        result = model.transcribe(file_path, fp16=False if model.device == "cpu" else True)
    else:
        result = model.transcribe(file_path, language=language, fp16=False if model.device == "cpu" else True)
    return result["text"].strip()
