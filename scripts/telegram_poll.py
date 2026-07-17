"""
Roda a cada poucos minutos (telegram-poll.yml). Pergunta pro Telegram "tem mensagem
nova?", olha só as suas (TELEGRAM_ALLOWED_USER_ID), decide se é um link (TikTok/
Facebook/Instagram) ou um arquivo de áudio/vídeo anexado, e ACUMULA numa fila
persistida no Gist (state_store) em vez de disparar na hora. Só dispara o pipeline
pesado (process-video.yml) via repository_dispatch pra tudo que estiver na fila
quando:

- a fila atinge BATCH_TRIGGER vídeos (dispara na hora, sem esperar 15 min), ou
- o item mais antigo da fila já espera BATCH_MAX_WAIT_SECONDS (fila pequena não
  fica presa pra sempre esperando juntar 7).

Se mais de um vídeo for disparado junto, marca "use_cache" no payload de todos -
o generate_script.py usa isso pra decidir se ativa o cache de prompt da Anthropic
(só compensa quando tem mais de uma chamada batendo na mesma base de conhecimento
em sequência).
"""
import os
import re
import time

import requests

import state_store

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_USER_ID = int(os.environ["TELEGRAM_ALLOWED_USER_ID"])
GH_DISPATCH_TOKEN = os.environ["GH_DISPATCH_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]

TELEGRAM_API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DISPATCH_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/dispatches"

BATCH_TRIGGER = 7
BATCH_MAX_WAIT_SECONDS = 15 * 60

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


def handle_message(message: dict) -> dict | None:
    """Decide o que fazer com a mensagem. Devolve o payload pra entrar na fila,
    ou None se a mensagem não gerou vídeo pra processar (link de Facebook ou
    texto não reconhecido — já respondidos aqui direto, não entram na fila)."""
    chat_id = message["chat"]["id"]

    for media_key in ("audio", "video", "voice"):
        if media_key in message:
            file_id = message[media_key]["file_id"]
            return {
                "source_type": "media",
                "media_type": media_key,
                "file_id": file_id,
                "chat_id": chat_id,
            }

    detected = detect_platform(message.get("text", ""))
    if detected:
        platform, url = detected
        if platform == "facebook":
            requests.post(f"{TELEGRAM_API}/sendMessage", json={
                "chat_id": chat_id,
                "text": "Link de Facebook eu não consigo baixar sozinho (bloqueio da própria plataforma). Manda o áudio ou vídeo direto aqui no chat, sem link, que eu processo.",
            }, timeout=15)
            return None
        return {
            "source_type": "link",
            "platform": platform,
            "url": url,
            "chat_id": chat_id,
        }

    requests.post(f"{TELEGRAM_API}/sendMessage", json={
        "chat_id": chat_id,
        "text": "Não reconheci um link (TikTok/Facebook/Instagram) nem um áudio/vídeo nessa mensagem.",
    }, timeout=15)
    return None


def main() -> None:
    state = state_store.load_state()
    offset = state.get("telegram_offset", 0)
    queue = state.get("pending_queue", [])
    queued_since = state.get("pending_queue_since")

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
        payload = handle_message(message)
        if payload:
            queue.append(payload)

    if queue and queued_since is None:
        queued_since = time.time()

    esperando_ha_muito = (
        queue and queued_since is not None
        and (time.time() - queued_since) >= BATCH_MAX_WAIT_SECONDS
    )
    if len(queue) >= BATCH_TRIGGER or esperando_ha_muito:
        use_cache = len(queue) > 1
        for payload in queue:
            payload["use_cache"] = use_cache
            dispatch_event(payload)
        queue = []
        queued_since = None

    if highest_update_id >= offset:
        state["telegram_offset"] = highest_update_id + 1
    state["pending_queue"] = queue
    state["pending_queue_since"] = queued_since
    state_store.save_state(state)


if __name__ == "__main__":
    main()
