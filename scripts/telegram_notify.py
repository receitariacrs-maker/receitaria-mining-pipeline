"""
Avisa o Luiz no Telegram em que ponto o pipeline está. Chamado com um argumento:
"received" (logo no início do process-video.yml), "done" (sucesso, no final) ou
"error" (se algum passo anterior falhar).
"""
import os
import sys

import requests

import context

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def send(chat_id: int, text: str) -> None:
    requests.post(f"{TELEGRAM_API}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=15)


def main() -> None:
    stage = sys.argv[1] if len(sys.argv) > 1 else "received"
    ctx = context.load()
    chat_id = ctx.get("chat_id")
    if not chat_id:
        return  # sem client_payload ainda (ex: falhou antes do download_video.py rodar)

    if stage == "received":
        send(chat_id, "Recebi o vídeo, processando (transcrição + roteiro)...")
    elif stage == "done":
        if ctx.get("notion_duplicate"):
            send(chat_id, f"Esse link já tinha sido processado antes. Card existente: {ctx['notion_page_url']}")
        else:
            send(chat_id, f"Roteiro pronto! Adicionado ao Notion: {ctx['notion_page_url']}")
    elif stage == "error":
        send(chat_id, "Deu erro processando esse vídeo. Se for Facebook/Instagram, tenta mandar o áudio/vídeo direto aqui no chat.")


if __name__ == "__main__":
    main()
