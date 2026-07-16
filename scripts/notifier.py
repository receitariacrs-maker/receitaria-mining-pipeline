"""
Manda avisos pro Luiz no Telegram em cada etapa do pipeline pesado — não só no
início e no fim, mas a cada passo (baixando, transcrevendo, escrevendo o
roteiro, salvando no Notion), com sucesso ou erro específico de cada um.
"""
import os

import requests

import context

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def _chat_id():
    return context.load().get("chat_id")


def _send(text: str) -> None:
    chat_id = _chat_id()
    if not (BOT_TOKEN and chat_id):
        return
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)


def start(mensagem: str) -> None:
    _send(mensagem)


def success(mensagem: str) -> None:
    _send(mensagem)


def error(etapa: str, exc: Exception, dica: str = "") -> None:
    texto = f"❌ Deu um problema em: {etapa}\nO que aconteceu: {exc}"
    if dica:
        texto += f"\n\n{dica}"
    _send(texto)
    context.update(error_notified=True)


def run_stage(etapa: str, inicio: str, sucesso: str, func, dica_erro: str = "") -> None:
    """Avisa o início, roda a função da etapa, avisa sucesso ou erro específico
    (e relança o erro, pra o GitHub Actions continuar marcando a etapa como
    falha nos logs)."""
    start(inicio)
    try:
        func()
    except Exception as exc:
        error(etapa, exc, dica_erro)
        raise
    success(sucesso)
