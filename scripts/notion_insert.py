"""
Quarto passo. Cria o card do roteiro pronto na database "Banco de Roteiros" do
Notion, já formatado do jeito que você usa pra gravar (callouts de Títulos A/B
e Modo de Preparo com checklist, uma versão por seção, link do vídeo de
referência bem no topo, sem poluição visual). Antes de criar, checa se já
existe um card com o mesmo link de origem (evita duplicata).

Os nomes de propriedade abaixo (TITLE_PROP, LINK_PROP, etc.) precisam bater com
os nomes exatos (acentos incluídos) das colunas da sua database no Notion —
confira em "Configurações da database -> Propriedades" e ajuste se for diferente.
"""
import os

import requests

import context
import notifier
import roteiro_parser

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # versão anterior à separação database/data_source (2025-09-03)

TITLE_PROP = "Nome"
NUMERO_PROP = "Número"
LINK_PROP = "Link de origem"
CATEGORIA_PROP = "Categoria"
PILAR_PROP = "Pilar estratégico"
STATUS_PROP = "Status"
STATUS_DEFAULT_OPTION = "Para Gravar"
VENCEDOR_RELATION_PROP = "Vencedor relacionado"  # relation -> Banco de Vencedores Próprios

MAX_BLOCK_LEN = 2000

ICON_LIST = {"type": "external", "external": {"url": "https://www.notion.so/icons/list_blue.svg"}}
ICON_EDIT = {"type": "external", "external": {"url": "https://www.notion.so/icons/edit_blue.svg"}}


def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def find_existing_page(source_url: str):
    if not source_url:
        return None
    resp = requests.post(
        f"{NOTION_API}/databases/{DATABASE_ID}/query",
        headers=_headers(),
        json={"filter": {"property": LINK_PROP, "url": {"equals": source_url}}},
        timeout=15,
    )
    resp.raise_for_status()
    results = resp.json().get("results", [])
    return results[0] if results else None


def chunk_text(text: str, size: int = MAX_BLOCK_LEN):
    return [text[i:i + size] for i in range(0, len(text), size)] or [""]


def rich_text(content: str, link: str | None = None, color: str | None = None):
    text_obj = {"content": content}
    if link:
        text_obj["link"] = {"url": link}
    obj = {"type": "text", "text": text_obj}
    if color:
        obj["annotations"] = {"color": color}
    return obj


def paragraph_block(content: str, link: str | None = None, color: str | None = None):
    return {"object": "block", "type": "paragraph", "paragraph": {"rich_text": [rich_text(content, link, color)]}}


def heading_block(content: str):
    return {"object": "block", "type": "heading_2", "heading_2": {"rich_text": [rich_text(content)]}}


def divider_block():
    return {"object": "block", "type": "divider", "divider": {}}


def to_do_block(content: str):
    return {"object": "block", "type": "to_do", "to_do": {"rich_text": [rich_text(content)], "checked": False}}


def bulleted_block(content: str):
    return {"object": "block", "type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [rich_text(content)]}}


def multi_paragraph_blocks(text: str):
    """Quebra um texto longo em blocos de parágrafo — um bloco por 'etapa'
    (separada por linha em branco no roteiro), respeitando o limite de 2000
    caracteres por bloco do Notion."""
    blocks = []
    for etapa in [p.strip() for p in text.split("\n\n") if p.strip()]:
        for chunk in chunk_text(etapa):
            blocks.append(paragraph_block(chunk))
    return blocks or [paragraph_block("(sem conteúdo)")]


def build_callout(icon: dict, color: str, title: str, children: list) -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "icon": icon,
            "color": color,
            "rich_text": [rich_text(title)],
            "children": children,
        },
    }


def build_children_blocks(parsed: dict, source_url: str | None) -> list:
    blocks = []

    if source_url:
        blocks.append(paragraph_block("Vídeo de referência", link=source_url, color="gray"))

    titulos = parsed["titulos_ab"]
    blocks.append(build_callout(ICON_EDIT, "yellow_background", "Títulos A/B", [
        paragraph_block(f"A: {titulos['a']}"),
        paragraph_block(f"B: {titulos['b']}"),
    ]))

    if parsed["hashtags"]:
        blocks.append(paragraph_block(" ".join(parsed["hashtags"]), color="gray"))

    receita = parsed["receita"]
    preparo_children = [to_do_block(ingrediente) for ingrediente in receita["ingredientes"]]
    if receita["preparo"]:
        preparo_children.append(paragraph_block(""))  # linha em branco antes do modo de preparo
        preparo_children.extend(paragraph_block(chunk) for chunk in chunk_text(receita["preparo"]))
    blocks.append(build_callout(ICON_LIST, "green_background", "Modo de Preparo", preparo_children))

    blocks.append(divider_block())
    blocks.append(heading_block("Versão-Mãe (Completa)"))
    blocks.extend(multi_paragraph_blocks(parsed["versao_mae"]))

    blocks.append(heading_block("Versão Rápida (1:01)"))
    blocks.extend(multi_paragraph_blocks(parsed["versao_rapida"]))

    blocks.append(heading_block("Versão Reels / Shorts (30s)"))
    for line in [l.strip("- ").strip() for l in parsed["versao_shorts"].splitlines() if l.strip()]:
        blocks.append(bulleted_block(line))

    return blocks


def build_properties(parsed: dict, ctx: dict) -> dict:
    properties = {
        TITLE_PROP: {"title": [{"text": {"content": parsed["titulo"] or "Roteiro minerado"}}]},
        STATUS_PROP: {"status": {"name": STATUS_DEFAULT_OPTION}},
    }
    if parsed.get("numero"):
        properties[NUMERO_PROP] = {"number": int(parsed["numero"])}
    if parsed.get("categoria"):
        properties[CATEGORIA_PROP] = {"select": {"name": parsed["categoria"]}}
    if parsed.get("pilar"):
        properties[PILAR_PROP] = {"select": {"name": parsed["pilar"]}}
    if ctx.get("source_url"):
        properties[LINK_PROP] = {"url": ctx["source_url"]}
    if ctx.get("vencedor_relacionado_id"):
        properties[VENCEDOR_RELATION_PROP] = {"relation": [{"id": ctx["vencedor_relacionado_id"]}]}
    return properties


def create_page(ctx: dict) -> str:
    parsed = roteiro_parser.parse(ctx["roteiro"])
    resp = requests.post(
        f"{NOTION_API}/pages",
        headers=_headers(),
        json={
            "parent": {"database_id": DATABASE_ID},
            "properties": build_properties(parsed, ctx),
            "children": build_children_blocks(parsed, ctx.get("source_url")),
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["url"]


def main() -> None:
    ctx = context.load()

    existing = find_existing_page(ctx.get("source_url"))
    if existing:
        context.update(notion_page_url=existing["url"], notion_duplicate=True)
        return

    page_url = create_page(ctx)
    context.update(notion_page_url=page_url, notion_duplicate=False)


if __name__ == "__main__":
    notifier.start("📋 Salvando o roteiro no Notion...")
    try:
        main()
    except Exception as exc:
        notifier.error(
            "salvar no Notion", exc,
            "Confere se a integração está conectada nas duas databases e se os "
            "nomes das propriedades batem com o que está configurado.",
        )
        raise

    ctx = context.load()
    if ctx.get("notion_duplicate"):
        notifier.success(f"🔁 Esse link já tinha sido processado antes. Card existente:\n{ctx['notion_page_url']}")
    else:
        notifier.success(f"🎉 Roteiro pronto! Card criado no Notion:\n{ctx['notion_page_url']}")
