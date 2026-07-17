"""
Rede de segurança de baixa frequência (queue-flush.yml, a cada ~30 min).

Antes disso detectava mensagem nova no Telegram via getUpdates (polling).
Isso foi substituído pelo Worker do Cloudflare (cloudflare-worker/worker.js),
que recebe cada mensagem na hora via webhook - sem depender do agendamento
"melhor esforço" do GitHub, que já ficou horas sem disparar. Como usar
getUpdates E webhook ao mesmo tempo não funciona (o Telegram desativa
getUpdates assim que um webhook é registrado, e passa a devolver erro 409),
esse script NÃO fala mais com o Telegram pra detectar mensagem - só olha o
mesmo Gist de estado que o Worker usa e completa o que ficou preso:

- se tiver algo na fila (pending_queue) esperando há mais de
  BATCH_MAX_WAIT_SECONDS, dispara mesmo assim (o Worker já devia ter feito
  isso sozinho ao passar os 15 min - isso aqui só cobre o cenário raro de o
  Worker ter caído ou o Cloudflare ter tido algum problema nesse meio tempo).
"""
import os
import time
import uuid

import requests

import state_store

GH_DISPATCH_TOKEN = os.environ["GH_DISPATCH_TOKEN"]
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]
DISPATCH_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}/dispatches"

BATCH_MAX_WAIT_SECONDS = 15 * 60


def dispatch_event(client_payload: dict) -> None:
    headers = {
        "Authorization": f"Bearer {GH_DISPATCH_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    body = {"event_type": "new-video", "client_payload": client_payload}
    resp = requests.post(DISPATCH_URL, headers=headers, json=body, timeout=15)
    resp.raise_for_status()


def main() -> None:
    state = state_store.load_state()
    queue = state.get("pending_queue", [])
    queued_since = state.get("pending_queue_since")

    if not queue or queued_since is None:
        return

    esperando_ha_muito = (time.time() - queued_since) >= BATCH_MAX_WAIT_SECONDS
    if not esperando_ha_muito:
        return

    print(f"--- Fila presa há mais de 15 min ({len(queue)} item(ns)) - o Worker não flushou sozinho. Disparando. ---")

    use_cache = len(queue) > 1
    lote_id = uuid.uuid4().hex if use_cache else None
    if lote_id:
        state["lote_atual"] = {
            "id": lote_id,
            "total": len(queue),
            "concluidos": 0,
            "chat_id": queue[0]["chat_id"],
        }
    for payload in queue:
        payload["use_cache"] = use_cache
        if lote_id:
            payload["lote_id"] = lote_id
        dispatch_event(payload)

    state["pending_queue"] = []
    state["pending_queue_since"] = None
    state_store.save_state(state)


if __name__ == "__main__":
    main()
