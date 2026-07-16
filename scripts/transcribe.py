"""
Segundo passo do pipeline pesado. Pega o arquivo baixado (vídeo ou áudio, tanto
faz), extrai o áudio com ffmpeg (ubuntu-latest já vem com ffmpeg instalado) e
manda pro Groq transcrever com o whisper-large-v3 (mais preciso que rodar um
modelo local, e sem gastar tempo de CPU do runner transcrevendo).
"""
import os
import subprocess

import requests

import context

GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
AUDIO_PATH = "audio_extracted.mp3"


def extract_audio(source_path: str) -> str:
    subprocess.run(
        ["ffmpeg", "-y", "-i", source_path, "-vn", "-acodec", "libmp3lame", AUDIO_PATH],
        check=True,
    )
    return AUDIO_PATH


def transcribe(audio_path: str) -> str:
    with open(audio_path, "rb") as f:
        resp = requests.post(
            GROQ_TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            files={"file": f},
            # sem "language" fixo: o conteúdo vem em PT/ES/FR/EN dependendo da página de origem,
            # deixa o whisper detectar sozinho.
            data={"model": "whisper-large-v3", "response_format": "text"},
            timeout=120,
        )
    resp.raise_for_status()
    return resp.text.strip()


def main() -> None:
    ctx = context.load()
    audio_path = extract_audio(ctx["local_media_path"])
    transcript = transcribe(audio_path)
    context.update(transcript=transcript)


if __name__ == "__main__":
    main()
