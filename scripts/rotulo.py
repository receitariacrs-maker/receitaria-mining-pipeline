"""
Calcula um identificador legível pro vídeo que está sendo processado nesse job,
pra colocar nas mensagens do Telegram. Com vários vídeos rodando em paralelo
(lote de vários links/áudios de uma vez), sem isso toda mensagem fica igual
("Baixando...", "Transcrevendo..." etc.) e não dá pra saber qual aviso é de
qual vídeo — nem qual deles específico deu erro.

Antes da Claude gerar o roteiro (baixar, transcrever), usa um rótulo
provisório baseado no link de origem ou na legenda/horário do envio.
generate_script.py troca esse rótulo pelo tema+categoria de verdade
(TITULO_CURTO) assim que o roteiro é gerado.
"""
import time


def provisorio(payload: dict) -> str:
    if payload.get("source_type") == "media":
        legenda = (payload.get("caption") or "").strip()
        if legenda:
            return legenda[:80]
        tipo = {"audio": "Áudio", "video": "Vídeo", "voice": "Áudio (voice)"}.get(
            payload.get("media_type"), "Mídia"
        )
        sent_at = payload.get("sent_at")
        if sent_at:
            hora = time.strftime("%H:%M UTC", time.gmtime(sent_at))
            return f"{tipo} enviado às {hora}"
        return tipo

    platform = (payload.get("platform") or "link").capitalize()
    url = payload.get("url") or ""
    return f"{platform}: {url}"
