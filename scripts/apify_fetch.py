"""
Baixa um vídeo do Facebook ou Instagram usando o Apify (scraper pago, centavos por
vídeo) em vez de tentar acesso direto/login. Roda um "actor" do Apify de forma
síncrona e pega a URL do vídeo no resultado.

IMPORTANTE: o nome do campo de input (ex: "startUrls" vs "postURLs" vs
"directUrls") e o nome do campo de saída com a URL do vídeo variam de actor pra
actor. Os valores abaixo são um ponto de partida — depois de escolher o actor
específico no Apify Store (ver README), confira a aba "Input"/"Output" dele e
ajuste ACTOR_IDS e os nomes de campo se for diferente.
"""
import os
import time

import requests

APIFY_TOKEN = os.environ["APIFY_API_TOKEN"]

ACTOR_IDS = {
    "facebook": os.environ.get("APIFY_ACTOR_FACEBOOK", "apify~facebook-reels-scraper"),
    "instagram": os.environ.get("APIFY_ACTOR_INSTAGRAM", "apify~instagram-reel-scraper"),
}

RUN_SYNC_URL = "https://api.apify.com/v2/acts/{actor_id}/run-sync-get-dataset-items"


def fetch_video_url(platform: str, post_url: str) -> str:
    actor_id = ACTOR_IDS[platform]
    resp = requests.post(
        RUN_SYNC_URL.format(actor_id=actor_id),
        params={"token": APIFY_TOKEN},
        json={"startUrls": [{"url": post_url}]},
        timeout=180,
    )
    resp.raise_for_status()
    items = resp.json()
    if not items:
        raise RuntimeError(f"Apify não retornou nenhum resultado para {post_url}")

    item = items[0]
    for key in ("videoUrl", "video_url", "downloadUrl", "playable_url", "url"):
        if item.get(key):
            return item[key]

    raise RuntimeError(f"Não achei a URL do vídeo no resultado do Apify: {item.keys()}")


def download_video(platform: str, post_url: str, dest_path: str) -> str:
    video_url = fetch_video_url(platform, post_url)
    with requests.get(video_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest_path
