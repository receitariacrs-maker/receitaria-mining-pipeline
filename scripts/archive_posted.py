"""
Roda 1x por dia (archive-posted.yml). Varre a database "Banco de Roteiros" e
arquiva (manda pro lixo do Notion, recuperável, não é exclusão permanente —
a API pública do Notion nem oferece isso) qualquer card cujo Status já esteja
como "Postado". Assim o Kanban não fica lotado de cards antigos.
"""
import os

import requests

from notion_insert import DATABASE_ID, NOTION_API, STATUS_PROP, _headers

ARCHIVE_STATUS_VALUE = os.environ.get("ARCHIVE_STATUS_VALUE") or "Postado"


def find_posted_pages():
    pages = []
    cursor = None
    while True:
        body = {"filter": {"property": STATUS_PROP, "status": {"equals": ARCHIVE_STATUS_VALUE}}}
        if cursor:
            body["start_cursor"] = cursor
        resp = requests.post(
            f"{NOTION_API}/databases/{DATABASE_ID}/query",
            headers=_headers(),
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data["results"])
        if not data.get("has_more"):
            break
        cursor = data["next_cursor"]
    return pages


def archive_page(page_id: str) -> None:
    resp = requests.patch(
        f"{NOTION_API}/pages/{page_id}",
        headers=_headers(),
        json={"archived": True},
        timeout=15,
    )
    resp.raise_for_status()


def main() -> None:
    pages = find_posted_pages()
    for page in pages:
        archive_page(page["id"])
    print(f"Arquivados {len(pages)} card(s) com Status = {ARCHIVE_STATUS_VALUE!r}.")


if __name__ == "__main__":
    main()
