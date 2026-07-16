"""
Roda a cada 5-10 min (telegram-poll.yml). Pergunta pro Telegram "tem mensagem nova?",
olha só as suas (TELEGRAM_ALLOWED_USER_ID), decide se é um link (TikTok/Facebook/
Instagram) ou um arquivo de áudio/vídeo anexado, e dispara o pipeline pesado
(process-video.yml) via repository_dispatch pra cada uma encontrada.
"""
import os
import re

import requests

import state_store

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
GH_DISPATCH_TOKEN = os.environ["GH_DISPATCH_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DISPATCH_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/dispatches"

URL_PATTERNS = {
    "tiktok": re.compile(r"https?://(?:www\.|vm\.|vt\.)?tiktok\.com/\S+", re.I),
    "instagram": re.compile(r"https?://(?:www\.)?instagram\.com/\S+", re.I),
    "facebook": re.compile(r"https?://(?:www\.|m\.)?facebook\.com/\S+|https?://fb\.watch/\S+", re.I),
}


def detect_platform(text: str):
    if not text:
        return None
    for platform, pattern in URL_PATTERNS.items():
        match = pattern.search(text)
        if match:
            return platform, match.group(0)
    return None


def dispatch_event(client_payload: dict) -> None:
    headers = {
        "Authorization": f"Bearer {GH_DISPATCH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    body = {"event_type": "new-video", "client_payload": client_payload}
    resp = requests.post(DISPATCH_URL, headers=headers, json=body, timeout=15)
    resp.raise_for_status()


def handle_message(message: dict) -> None:
    chat_id = message["chat"]["id"]

    # Mensagem já é mídia (áudio, vídeo, ou voice) -> pula download automático
    for media_key in ("audio", "video", "voice"):
        if media_key in message:
            file_id = message[media_key]["file_id"]
            dispatch_event({
                "source_type": "media",
                "media_type": media_key,
                "file_id": file_id,
                "chat_id": chat_id,
            })
            return

    detected = detect_platform(message.get("text", ""))
    if detected:
        platform, url = detected
        if platform == "facebook":
            # Testado e confirmado: nenhum jeito automático de baixar um link
            # específico do Facebook sem login. Avisa na hora, sem gastar um
            # run inteiro do process-video.yml só pra falhar no final.
            requests.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": "Link de Facebook eu não consigo baixar sozinho (bloqueio da própria plataforma). Manda o áudio ou vídeo direto aqui no chat, sem link, que eu processo.",
            }, timeout=15)
            return
        dispatch_event({
            "source_type": "link",
            "platform": platform,
            "url": url,
            "chat_id": chat_id,
        })
        return

    # Texto que não é link nem mídia reconhecida -> avisa e ignora
    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Não reconheci um link (TikTok/Facebook/Instagram) nem um áudio/vídeo nessa mensagem.",
    }, timeout=15)


def main() -> None:
    offset = state_store.get_offset()
    resp = requests.get(f"{TELEGRAM_API}/getUpdates", params={
        "offset": offset,
        "timeout": 0,
    }, timeout=15)
    resp.raise_for_status()
    updates = resp.json().get("result", [])

    highest_update_id = offset - 1
    for update in updates:
        highest_update_id = max(highest_update_id, update["update_id"])
        message = update.get("message")
        if not message:
            continue
        if message.get("from", {}).get("id") != ALLOWED_USER_ID:
            continue
        handle_message(message)

    if highest_update_id >= offset:
        state_store.set_offset(highest_update_id + 1)


if __name__ == "__main__":
    main()
