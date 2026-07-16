"""
Cada passo do process-video.yml roda num script Python separado. Esse arquivo
guarda/lê um JSON local (run_context.json) pra um passo passar informação pro
próximo dentro do mesmo job (ex: caminho do vídeo baixado, texto da transcrição).
"""
import json
import os

CONTEXT_PATH = os.path.join(os.getcwd(), "run_context.json")


def load() -> dict:
    if not os.path.exists(CONTEXT_PATH):
        return {}
    with open(CONTEXT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save(context: dict) -> None:
    with open(CONTEXT_PATH, "w", encoding="utf-8") as f:
        json.dump(context, f, ensure_ascii=False, indent=2)


def update(**kwargs) -> dict:
    context = load()
    context.update(kwargs)
    save(context)
    return context
