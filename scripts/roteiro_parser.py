"""
Interpreta o texto que a Claude devolve em generate_script.py, no formato
combinado (extensão do template Antigravity — ver README): duas linhas de
metadado (CATEGORIA/PILAR) no topo, seguidas do roteiro no formato de tags
textuais (TITULOS A/B, HASHTAGS, RECEITA RESUMIDA, ROTEIRO VERSAO-*).

notion_insert.py usa o dicionário retornado por parse() pra montar as
propriedades e os blocos da página no Notion.
"""
import re

SECTION_ORDER = [
    "TITULOS A/B",
    "HASHTAGS",
    "RECEITA RESUMIDA",
    "ROTEIRO VERSAO-MAE",
    "ROTEIRO VERSAO-RAPIDA",
    "ROTEIRO VERSAO-SHORTS",
]


def parse(text: str) -> dict:
    text = text.strip()

    categoria = _extract_line(text, "CATEGORIA")
    pilar = _extract_line(text, "PILAR")
    body = re.sub(r"^CATEGORIA:.*$\n?", "", text, flags=re.M)
    body = re.sub(r"^PILAR:.*$\n?", "", body, flags=re.M).strip()

    numero, titulo, rest = _split_title(body)
    sections = _split_sections(rest)

    return {
        "categoria": categoria,
        "pilar": pilar,
        "numero": numero,
        "titulo": titulo,
        "titulos_ab": _parse_titulos_ab(sections.get("TITULOS A/B", "")),
        "hashtags": sections.get("HASHTAGS", "").split(),
        "receita": _parse_receita(sections.get("RECEITA RESUMIDA", "")),
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


def _parse_receita(text: str) -> dict:
    lines = text.splitlines()
    ingredientes = [line.strip()[1:].strip() for line in lines if line.strip().startswith("-")]
    preparo_lines = [line.strip() for line in lines if line.strip() and not line.strip().startswith("-")]
    return {"ingredientes": ingredientes, "preparo": " ".join(preparo_lines).strip()}
