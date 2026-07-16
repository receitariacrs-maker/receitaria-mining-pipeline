"""
Baixa o áudio de um Reel do Instagram usando o Apify (scraper pago, mas
centavos por vídeo) com o actor apify/instagram-reel-scraper — testado e
confirmado que resolve um link de reel específico corretamente (não é
scraper de perfil inteiro).

Testado também: o campo "audioUrl" já vem de graça na resposta básica, sem
precisar do addon pago "Include downloaded video" (que custa bem mais caro,
~$0,24/vídeo). Como só precisamos do áudio pra transcrever, isso evita pagar
por um vídeo inteiro que a gente nem usa.

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


def fetch_media_url(post_url: str) -> str:
    resp = requests.post(
        RUN_SYNC_URL,
        params={"token": APIFY_TOKEN},
        json={
            "username": [post_url],
            "resultsLimit": 1,
        },
        timeout=180,
    )
    resp.raise_for_status()
    items = resp.json()
    if not items:
        raise RuntimeError(f"Apify não retornou nenhum resultado para {post_url}")

    item = items[0]
    # Prioridade: audioUrl (só áudio, mais leve, de graça, é tudo que a
    # transcrição precisa) -> downloadedVideo (hospedado pelo Apify, só existe
    # se o addon pago estiver ligado) -> videoUrl (CDN do Instagram, assinado,
    # expira em poucas horas — por isso baixamos na hora, nunca guardamos).
    media_url = item.get("audioUrl") or item.get("downloadedVideo") or item.get("videoUrl")
    if not media_url:
        raise RuntimeError(f"Apify retornou o reel mas sem áudio/vídeo: {item.keys()}")
    return media_url


def download_video(post_url: str, dest_path: str) -> str:
    media_url = fetch_media_url(post_url)
    with requests.get(media_url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return dest_path
