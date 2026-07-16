"""
Primeiro passo do pipeline pesado (process-video.yml). Lê o que o telegram_poll.py
mandou (client_payload do repository_dispatch), baixa a mídia pelo caminho certo:

- TikTok            -> yt-dlp (sem login, já validado, grátis)
- Instagram (link)  -> Apify (apify_fetch.py, testado e confirmado)
- Facebook (link)   -> não dá — testado e confirmado que nenhum scraper resolve
  um link de reel específico sem login (limitação da Meta). Erro amigável na
  hora, pedindo pra mandar o áudio/vídeo direto.
- Áudio/vídeo anexado direto no Telegram -> baixa via Bot API

e grava o caminho do arquivo baixado + metadados no run_context.json pro
próximo passo (transcribe.py) usar.
"""
import json
import os
import subprocess

import requests

import apify_fetch
import context
import notifier

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
DOWNLOAD_PATH = "downloaded_media"


def download_tiktok(url: str) -> str:
    subprocess.run(
        ["yt-dlp", "-f", "bestaudio", "-o", f"{DOWNLOAD_PATH}.%(ext)s", url],
        check=True,
    )
    matches = [f for f in os.listdir(".") if f.startswith(DOWNLOAD_PATH)]
    if not matches:
        raise RuntimeError("yt-dlp não gerou nenhum arquivo de saída")
    return matches[0]


def download_telegram_media(file_id: str, media_type: str) -> str:
    resp = requests.get(
        f"https://api.telegram.org/bot{BOT_TOKEN}/getFile",
        params={"file_id": file_id},
        timeout=15,
    )
    resp.raise_for_status()
    file_path = resp.json()["result"]["file_path"]
    ext = file_path.rsplit(".", 1)[-1] if "." in file_path else "bin"
    dest = f"{DOWNLOAD_PATH}.{ext}"
    file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
    with requests.get(file_url, stream=True, timeout=60) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest


def main() -> None:
    # o workflow já grava o client_payload no contexto num passo anterior (pra dar
    # pra avisar o Luiz "recebido" antes mesmo de baixar); se não existir por algum
    # motivo (ex: rodando o script à mão), cai pra ler direto da env var.
    payload = context.load() or json.loads(os.environ["CLIENT_PAYLOAD_JSON"])
    chat_id = payload["chat_id"]

    if payload["source_type"] == "media":
        local_path = download_telegram_media(payload["file_id"], payload["media_type"])
        context.update(
            chat_id=chat_id,
            source_type="media",
            platform=None,
            source_url=None,
            local_media_path=local_path,
        )
        return

    platform = payload["platform"]
    url = payload["url"]

    if platform == "tiktok":
        local_path = download_tiktok(url)
    elif platform == "instagram":
        local_path = apify_fetch.download_video(url, f"{DOWNLOAD_PATH}.mp4")
    elif platform == "facebook":
        raise RuntimeError(
            "Facebook não tem como baixar automaticamente por link (bloqueio "
            "sem login, testado e confirmado). Manda o áudio ou vídeo direto "
            "aqui no chat, sem link."
        )
    else:
        raise ValueError(f"Plataforma não suportada: {platform}")

    context.update(
        chat_id=chat_id,
        source_type="link",
        platform=platform,
        source_url=url,
        local_media_path=local_path,
    )


if __name__ == "__main__":
    notifier.run_stage(
        etapa="baixar o vídeo",
        inicio="⬇️ Baixando o vídeo/áudio...",
        sucesso="✅ Download concluído. Agora vou transcrever.",
        func=main,
        dica_erro="Se for link de Facebook, manda o áudio ou vídeo direto aqui no chat, sem link.",
    )
