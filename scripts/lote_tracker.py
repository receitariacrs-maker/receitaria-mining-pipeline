"""
Último passo do process-video.yml, roda sempre (sucesso ou erro - if: always()
no workflow). Quando telegram_poll.py despeja um lote de vídeos de uma vez
(7+ na fila, ou o fallback de 15 min), cada vídeo processa num job paralelo
isolado, sem saber dos outros. Esse script usa o mesmo Gist de estado (onde
telegram_poll.py guarda a fila) como contador compartilhado: cada job soma 1
em "concluidos" quando termina (não importa se deu certo ou errado - o que
importa é que "acabou"); o job que fechar a conta (concluidos == total) avisa
no Telegram que o lote inteiro terminou.

Vídeo avulso (fora de lote, "lote_id" ausente do contexto) não passa por
nada disso - sai na primeira linha do main().

Concorrência: como os jobs rodam em paralelo de verdade, dois podem ler o
Gist quase ao mesmo tempo e um "pisar" no incremento do outro (write vence
por último, sem trava). Mitiga com: pequeno atraso aleatório antes de cada
tentativa (reduz a chance de dois jobs colidirem no mesmo instante) e
reconfirmação depois de salvar (relê o Gist; se o nosso incremento não
"pegou" - outro job já tinha sobrescrito - tenta de novo do zero com o
estado mais recente). Não é uma trava atômica de verdade (a API do Gist não
oferece isso), mas cobre bem o caso real (4-8 vídeos, terminando espalhados
ao longo de ~1-2 min, não literalmente no mesmo segundo).
"""
import os
import random
import time

import requests

import context
import state_store

TELEGRAM_API_TEMPLATE = "https://api.telegram.org/bot{token}/sendMessage"
MAX_TENTATIVAS = 5


def _avisar_lote_concluido(bot_token: str, chat_id, total: int) -> None:
    if not (bot_token and chat_id):
        return
    texto = f"🏁 Lote concluído: {total} vídeo(s) processado(s)."
    requests.post(
        TELEGRAM_API_TEMPLATE.format(token=bot_token),
        json={"chat_id": chat_id, "text": texto},
        timeout=15,
    )


def main() -> None:
    ctx = context.load()
    lote_id = ctx.get("lote_id")
    if not lote_id:
        return  # vídeo avulso, não faz parte de um lote rastreado

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")

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
                _avisar_lote_concluido(bot_token, lote.get("chat_id"), lote["total"])
                return
        else:
            if lote_confirmado and lote_confirmado.get("concluidos") == esperado:
                return

        # não confirmou - outro job colidiu no meio do caminho, tenta de novo
        time.sleep(0.5 * (tentativa + 1))


if __name__ == "__main__":
    main()
