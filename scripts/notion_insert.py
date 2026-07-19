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
import time

import requests

import context
import notifier
import roteiro_parser

NOTION_TOKEN = os.environ["NOTION_TOKEN"]
DATABASE_ID = os.environ["NOTION_DATABASE_ID"]
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"  # versão anterior à separação database/data_source (2025-09-03)

MAX_RETRIES = 3

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

# Ícone da PÁGINA (não do bloco/callout) por categoria - biblioteca de ícones
# vetoriais nativa do Notion (mesma família de ICON_LIST/ICON_EDIT), não emoji.
# Só as URLs abaixo foram confirmadas de verdade (vistas carregando no Notion);
# categorias sem um ícone temático confirmado caem no ICON_FALLBACK em vez de
# arriscar uma URL adivinhada (ícone quebrado na página).
ICON_FALLBACK = ICON_LIST
ICON_POR_CATEGORIA = {
    "Dores Articulares": {"type": "external", "external": {"url": "https://www.notion.so/icons/activity_blue.svg"}},
    "Saúde & Colesterol": {"type": "external", "external": {"url": "https://www.notion.so/icons/heart_blue.svg"}},
    "Casa & Pragas": {"type": "external", "external": {"url": "https://www.notion.so/icons/home_blue.svg"}},
    "Saúde Natural": {"type": "external", "external": {"url": "https://www.notion.so/icons/home_gray.svg"}},
}


def icone_para_categoria(categoria: str | None) -> dict:
    return ICON_POR_CATEGORIA.get(categoria, ICON_FALLBACK)


def _headers():
    return {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _post_with_retry(url: str, **kwargs) -> requests.Response:
    """POST com retry (até MAX_RETRIES tentativas) em erro 429 - a Notion limita a
    ~3 requisições/segundo por integração, e rodar vários vídeos em paralelo (ex.:
    vários links do Telegram processados ao mesmo tempo) pode estourar isso."""
    for attempt in range(MAX_RETRIES):
        resp = requests.post(url, **kwargs)
        if resp.status_code != 429 or attempt == MAX_RETRIES - 1:
            resp.raise_for_status()
            return resp
        wait = float(resp.headers.get("Retry-After", 1)) * (attempt + 1)
        time.sleep(wait)


def find_existing_page(source_url: str):
    if not source_url:
        return None
    resp = _post_with_retry(
        f"{NOTION_API}/databases/{DATABASE_ID}/query",
        headers=_headers(),
        json={"filter": {"property": LINK_PROP, "url": {"equals": source_url}}},
        timeout=15,
    )
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


def build_children_blocks(parsed: dict, source_url: str | None, qa_avisos: list | None = None) -> list:
    blocks = []

    if source_url:
        blocks.append(paragraph_block("Vídeo de referência", link=source_url, color="gray"))

    # Avisos das checagens programáticas de QA (tamanho/gancho/CTA) - desde a
    # remoção do retry, este callout é o lugar onde qualquer desvio fica
    # visível. Vem antes de tudo de propósito: se existir, é a primeira coisa
    # que o Luiz precisa ver no card.
    if qa_avisos:
        blocks.append(build_callout(ICON_EDIT, "red_background", "⚠️ Avisos de QA",
                                    [paragraph_block(aviso) for aviso in qa_avisos]))

    titulos = parsed["titulos_ab"]
    blocks.append(build_callout(ICON_EDIT, "yellow_background", "Títulos A/B", [
        paragraph_block(f"A: {titulos['a']}"),
        paragraph_block(f"B: {titulos['b']}"),
    ]))

    gancho = parsed.get("analise_gancho") or {}
    if gancho.get("familia_gancho"):
        blocks.append(build_callout(ICON_EDIT, "gray_background", "Análise do Gancho (QA)", [
            paragraph_block(f"Família: {gancho.get('familia_gancho') or '-'}"),
            paragraph_block(f"Gancho original (referência): {gancho.get('gancho_original') or '-'}"),
            paragraph_block(f"Ingrediente-âncora: {gancho.get('ingrediente_ancora') or '-'}"),
            paragraph_block(f"Promessa: {gancho.get('promessa') or '-'}"),
            paragraph_block(f"Gatilho: {gancho.get('gatilho') or '-'}"),
            paragraph_block(f"Ajuste de veracidade: {gancho.get('ajuste_veracidade') or '-'}"),
        ]))

    if parsed["hashtags"]:
        blocks.append(paragraph_block(" ".join(parsed["hashtags"]), color="gray"))

    preparo_children = [to_do_block(ingrediente) for ingrediente in parsed["ingredientes"]]
    if parsed["preparo_passos"]:
        if preparo_children:
            preparo_children.append(paragraph_block(""))  # separador visual ingredientes -> passos
        preparo_children.extend(to_do_block(passo) for passo in parsed["preparo_passos"])
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
    titulo_pagina = parsed.get("titulo_curto") or parsed.get("titulo") or "Roteiro minerado"
    properties = {
        TITLE_PROP: {"title": [{"text": {"content": titulo_pagina}}]},
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
    if not parsed["titulo"] and not parsed["versao_mae"]:
        raise RuntimeError(
            "O roteiro que a Claude devolveu não bateu com o formato esperado (parsing "
            "ficou tudo vazio) - a IA deve ter seguido outro formato em vez das tags de "
            "texto puro. Card não foi criado vazio de propósito; veja o log do passo "
            "'Gerar roteiro (Anthropic)' pra checar a resposta bruta."
        )
    resp = _post_with_retry(
        f"{NOTION_API}/pages",
        headers=_headers(),
        json={
            "parent": {"database_id": DATABASE_ID},
            "icon": icone_para_categoria(parsed.get("categoria")),
            "properties": build_properties(parsed, ctx),
            "children": build_children_blocks(parsed, ctx.get("source_url"), ctx.get("qa_avisos")),
        },
        timeout=30,
    )
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
