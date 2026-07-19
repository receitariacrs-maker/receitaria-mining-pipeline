"""
Último passo do process-video.yml, roda sempre (sucesso ou erro - if: always()
no workflow). Quando telegram_poll.py despeja um lote de vídeos de uma vez
(7+ na fila, ou o fallback de 15 min), cada vídeo processa num job paralelo
isolado, sem saber dos outros. Esse script usa o mesmo Gist de estado (onde
telegram_poll.py guarda a fila) como contador compartilhado: cada job soma 1
em "concluidos" quando termina (não importa se deu certo ou errado - o que
importa é que "acabou"); o job que fechar a conta (concluidos == total) avisa
no Telegram que o lote inteiro terminou.

Vídeo avulso (fora de lote, "lote_id" ausente do contexto) pula a contagem de
lote, mas passa pelo flush de message_id abaixo igual a qualquer outro.

Concorrência: como os jobs rodam em paralelo de verdade, dois podem ler o
Gist quase ao mesmo tempo e um "pisar" no incremento do outro (write vence
por último, sem trava). Mitiga com: pequeno atraso aleatório antes de cada
tentativa (reduz a chance de dois jobs colidirem no mesmo instante) e
reconfirmação depois de salvar (relê o Gist; se o nosso incremento não
"pegou" - outro job já tinha sobrescrito - tenta de novo do zero com o
estado mais recente). Não é uma trava atômica de verdade (a API do Gist não
oferece isso), mas cobre bem o caso real (4-8 vídeos, terminando espalhados
ao longo de ~1-2 min, não literalmente no mesmo segundo).

Esse script também é o único ponto, pra QUALQUER job (avulso ou em lote), que
despeja os message_id acumulados localmente por notifier.py
(run_context.json, campo "sent_message_ids") no Gist compartilhado - é o que
permite ao comando "/limpar" do Telegram (e à limpeza automática diária do
Cloudflare Worker) saber depois quais mensagens apagar. Esse flush é
best-effort (poucas tentativas, sem o reconfirm-read robusto da contagem de
lote acima) - perder um id ocasionalmente só significa que aquela mensagem
sobrevive até o próximo ciclo de limpeza, não é um bug visível.
"""
import os
import random
import time

import requests

import context
import state_store

TELEGRAM_API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_TENTATIVAS = 5


def _avisar_lote_concluido(bot_token: str, chat_id, total: int) -> int | None:
    if not (bot_token and chat_id):
        return None
    texto = f"🏁 Lote concluído: {total} vídeo(s) processado(s)."
    resp = requests.post(
        TELEGRAM_API_TEMPLATE.format(token=bot_token),
        json={"chat_id": chat_id, "text": texto},
        timeout=15,
    )
    return resp.json().get("result", {}).get("message_id")


def _processar_lote(ctx: dict, lote_id: str, bot_token: str) -> None:
    """Soma 1 em concluidos e, se for o job que fechar o lote, avisa no
    Telegram - registrando o message_id desse aviso em `ctx` pro flush no
    final de main() pegar junto com o resto."""
    for tentativa in range(MAX_TENTATIVAS):
        time.sleep(random.uniform(0, 2))
        state = state_store.load_state()
        lote = state.get("lote_atual")
        if not lote or lote.get("id") != lote_id:
            return  # outro job já fechou esse lote, ou o estado foi limpo

        esperado = lote.get("concluidos", 0) + 1
        lote["concluidos"] = esperado
        terminou = esperado >= lote.get("total", 0)
        state["lote_atual"] = None if terminou else lote
        state_store.save_state(state)

        # reconfirma: relê o Gist e checa se o nosso incremento realmente
        # ficou salvo (ninguém sobrescreveu por cima entre o load e o save)
        state_confirmado = state_store.load_state()
        lote_confirmado = state_confirmado.get("lote_atual")
        if terminou:
            if lote_confirmado is None or lote_confirmado.get("id") != lote_id:
                message_id = _avisar_lote_concluido(bot_token, lote.get("chat_id"), lote["total"])
                if message_id is not None:
                    ctx.setdefault("sent_message_ids", []).append(message_id)
                return
        else:
            if lote_confirmado and lote_confirmado.get("concluidos") == esperado:
                return

        # não confirmou - outro job colidiu no meio do caminho, tenta de novo
        time.sleep(0.5 * (tentativa + 1))


def _flush_sent_message_ids(ctx: dict) -> None:
    """Despeja no Gist compartilhado os message_id que esse job acumulou
    localmente (notifier.py durante as etapas, mais o aviso de lote
    concluído acima, se houver). Best-effort: poucas tentativas, sem o
    reconfirm-read da contagem de lote - perder um id ocasionalmente só
    adia a limpeza dele pro próximo ciclo, não quebra nada."""
    ids_locais = ctx.get("sent_message_ids", [])
    if not ids_locais:
        return
    for _tentativa in range(3):
        try:
            state = state_store.load_state()
            state["sent_message_ids"] = state.get("sent_message_ids", []) + ids_locais
            state_store.save_state(state)
            return
        except Exception:
            time.sleep(random.uniform(0, 1))


def main() -> None:
    ctx = context.load()
    lote_id = ctx.get("lote_id")
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

    if lote_id:
        _processar_lote(ctx, lote_id, bot_token)

    _flush_sent_message_ids(ctx)


if __name__ == "__main__":
    main()
