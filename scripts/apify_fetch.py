"""
Baixa um vídeo do Instagram usando o Apify (scraper pago, centavos por vídeo)
com o actor apify/instagram-reel-scraper — testado e confirmado que resolve
um link de reel específico corretamente (não é scraper de perfil inteiro).

Facebook NÃO usa Apify — testado com o actor oficial (apify/facebook-reels-
scraper) e ele só aceita URL de página/perfil (procura uma "seção Reels"),
rejeitando link de reel específico com "not available without FB login".
Não vale a pena tentar outros actors, é uma limitação da própria Meta, não
da ferramenta. Facebook cai direto no fallback manual (ver download_video.py).
"""
import os

import requests

APIFY_TOKEN = os.environ["APIFY_API_TOKEN"]
ACTOR_ID = os.environ.get("APIFY_ACTOR_INSTAGRAM", "apify~instagram-reel-scraper")

RUN_SYNC_URL = f"https://api.apify.com/v2/acts/{ACTOR_ID}/run-sync-get-dataset-items"


def fetch_video_url(post_url: str) -> str:
    resp = requests.post(
        RUN_SYNC_URL,
        params={"token": APIFY_TOKEN},
        json={
            "username": [post_url],
            "resultsLimit": 1,
            "includeDownloadedVideo": True,
        },
        timeout=180,
    )
    resp.raise_for_status()
    items = resp.json()
    if not items:
        raise RuntimeError(f"Apify não retornou nenhum resultado para {post_url}")

    item = items[0]
    # "downloadedVideo" é hospedado pelo próprio Apify (mais estável); "videoUrl"
    # é o link direto do CDN do Instagram, assinado e expira em poucas horas.
    video_url = item.get("downloadedVideo") or item.get("videoUrl")
    if not video_url:
        raise RuntimeError(f"Apify retornou o reel mas sem vídeo: {item.keys()}")
    return video_url


def download_video(post_url: str, dest_path: str) -> str:
    video_url = fetch_video_url(post_url)
    with requests.get(video_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest_path
