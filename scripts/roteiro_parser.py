"""
Interpreta o texto que a Claude devolve em generate_script.py, no formato
combinado (extensão do template Antigravity — ver README): linhas de
metadado (CATEGORIA/PILAR/TITULO_CURTO) no topo, seguidas do roteiro no
formato de tags textuais (TITULOS A/B, HASHTAGS, INGREDIENTES, MODO DE
PREPARO, ROTEIRO VERSAO-*).

notion_insert.py usa o dicionário retornado por parse() pra montar as
propriedades e os blocos da página no Notion.
"""
import re

SECTION_ORDER = [
    "TITULOS A/B",
    "HASHTAGS",
    "INGREDIENTES",
    "MODO DE PREPARO",
    "ROTEIRO VERSAO-MAE",
    "ROTEIRO VERSAO-RAPIDA",
    "ROTEIRO VERSAO-SHORTS",
]


def parse(text: str) -> dict:
    text = text.strip()

    categoria = _extract_line(text, "CATEGORIA")
    pilar = _extract_line(text, "PILAR")
    titulo_curto = _extract_line(text, "TITULO_CURTO")
    body = re.sub(r"^CATEGORIA:.*$\n?", "", text, flags=re.M)
    body = re.sub(r"^PILAR:.*$\n?", "", body, flags=re.M)
    body = re.sub(r"^TITULO_CURTO:.*$\n?", "", body, flags=re.M).strip()

    numero, titulo, rest = _split_title(body)
    sections = _split_sections(rest)

    return {
        "categoria": categoria,
        "pilar": pilar,
        "titulo_curto": titulo_curto,
        "numero": numero,
        "titulo": titulo,
        "titulos_ab": _parse_titulos_ab(sections.get("TITULOS A/B", "")),
        "hashtags": sections.get("HASHTAGS", "").split(),
        "ingredientes": _parse_lista_com_marcador(sections.get("INGREDIENTES", ""), r"^-\s*"),
        "preparo_passos": _parse_passos_preparo(sections.get("MODO DE PREPARO", "")),
        "versao_mae": sections.get("ROTEIRO VERSAO-MAE", "").strip(),
        "versao_rapida": sections.get("ROTEIRO VERSAO-RAPIDA", "").strip(),
        "versao_shorts": sections.get("ROTEIRO VERSAO-SHORTS", "").strip(),
    }


def _extract_line(text: str, key: str):
    m = re.search(rf"^{key}:\s*(.+)$", text, flags=re.M)
    return m.group(1).strip() if m else None


def _split_title(body: str):
    first_line, _, rest = body.partition("\n")
    m = re.match(r"\s*(\d+)\.\s*(.+)", first_line)
    if m:
        return m.group(1), m.group(2).strip(), rest.strip()
    return None, first_line.strip(), rest.strip()


def _split_sections(rest: str) -> dict:
    pattern = "|".join(re.escape(s) for s in SECTION_ORDER)
    parts = re.split(rf"^({pattern})\s*$", rest, flags=re.M)
    sections = {}
    # parts alterna: [antes do primeiro cabeçalho, cabeçalho1, conteúdo1, cabeçalho2, conteúdo2, ...]
    for i in range(1, len(parts), 2):
        header = parts[i].strip()
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        sections[header] = content
    return sections


def _parse_titulos_ab(text: str) -> dict:
    a = re.search(r"^A:\s*(.+)$", text, flags=re.M)
    b = re.search(r"^B:\s*(.+)$", text, flags=re.M)
    return {"a": a.group(1).strip() if a else "", "b": b.group(1).strip() if b else ""}


def _parse_lista_com_marcador(text: str, marcador_regex: str) -> list[str]:
    """Extrai itens de uma lista onde cada linha começa com um marcador
    (ex: '- ' ou '1. '), devolvendo só o conteúdo, na ordem original."""
    itens = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(marcador_regex, line)
        if m:
            itens.append(line[m.end():].strip())
    return itens


def _parse_passos_preparo(text: str) -> list[str]:
    """Extrai os passos numerados de MODO DE PREPARO. Se a IA não numerou
    como instruído, cai para um fallback que aproveita cada linha não vazia
    como um passo — evita perder o conteúdo silenciosamente (mesmo tipo de
    bug que já mordeu esse pipeline antes: parsing zerado sem aviso)."""
    passos = _parse_lista_com_marcador(text, r"^\d+\.\s*")
    if passos:
        return passos
    return [line.strip() for line in text.splitlines() if line.strip()]
