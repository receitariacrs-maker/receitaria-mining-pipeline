"""
Guarda o "offset" do Telegram (qual mensagem já foi lida) num Gist privado do GitHub.
Os runners do GitHub Actions são apagados a cada execução, então esse é o único
lugar que sobrevive de uma execução do telegram-poll.yml pra outra.
"""
import json
import os

import requests

GIST_TOKEN = os.environ["GIST_TOKEN"]
GIST_ID = os.environ["GIST_ID"]
STATE_FILENAME = "mining_pipeline_state.json"
GIST_API = f"https://api.github.com/gists/{GIST_ID}"


def _headers():
    return {
        "Authorization": f"Bearer {GIST_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def load_state() -> dict:
    resp = requests.get(GIST_API, headers=_headers(), timeout=15)
    resp.raise_for_status()
    file_info = resp.json()["files"].get(STATE_FILENAME)
    if not file_info or not file_info.get("content"):
        return {}
    return json.loads(file_info["content"])


def save_state(state: dict) -> None:
    payload = {"files": {STATE_FILENAME: {"content": json.dumps(state, indent=2, ensure_ascii=False)}}}
    resp = requests.patch(GIST_API, headers=_headers(), json=payload, timeout=15)
    resp.raise_for_status()


def get_offset() -> int:
    return load_state().get("telegram_offset", 0)


def set_offset(offset: int) -> None:
    state = load_state()
    state["telegram_offset"] = offset
    save_state(state)
