"""
Confere se os três documentos do sistema Receitaria concordam com o
CONTRATO_FORMATOS.md — a fonte única dos parâmetros.

Motivação: a meta de caracteres da versão-mãe estava declarada em nove lugares
entre o manual mestre, a versão pipeline e este repositório, e os nove não
batiam. Mesma coisa com o tempo da camada bônus e com a regra do 25-30s. Como só
14% do texto da pipeline é cópia do mestre (são reescritas independentes das
mesmas regras), não dá pra gerar um a partir do outro — o que dá é travar os
números.

Uso:
    python scripts/verificar_contrato.py
    python scripts/verificar_contrato.py --roteiros "/caminho/para/Conteudo/Roteiros"

Sai com código 1 se achar divergência, pra poder rodar em CI ou pre-commit.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Caminho padrão da pasta de manuais. Pode ser sobrescrito por --roteiros ou
# pela variável de ambiente RECEITARIA_ROTEIROS.
ROTEIROS_PADRAO = Path(
    os.environ.get(
        "RECEITARIA_ROTEIROS",
        r"C:\Kinn Media\01 - Receitaria Curiosa\Conteudo\Roteiros",
    )
)

AQUI = Path(__file__).resolve().parent
GENERATE_SCRIPT = AQUI / "generate_script.py"


def carregar_contrato(pasta: Path) -> dict:
    caminho = pasta / "CONTRATO_FORMATOS.md"
    texto = caminho.read_text(encoding="utf-8")
    bloco = re.search(r"```json\s*(\{.*?\})\s*```", texto, re.S)
    if not bloco:
        raise SystemExit(f"Bloco json não encontrado em {caminho}")
    return json.loads(bloco.group(1))


def _int_pt(n: int) -> list[str]:
    """Formas de escrever um número que aparecem nos documentos: 3600 e 3.600."""
    s = str(n)
    formas = {s}
    if len(s) == 4:
        formas.add(f"{s[0]}.{s[1:]}")
    return sorted(formas)


def _contem_numero(texto: str, n: int) -> bool:
    return any(re.search(rf"\b{re.escape(f)}\b", texto) for f in _int_pt(n))


def checar_constantes_python(contrato: dict) -> list[str]:
    """LIMITE_* e HOOK_LIMITE_* em generate_script.py devem bater com o contrato."""
    erros = []
    src = GENERATE_SCRIPT.read_text(encoding="utf-8")

    esperado_limites = {
        "LIMITE_MAE": ("mae", "caracteres_min", "caracteres_teto_aviso"),
        "LIMITE_RAPIDA": ("rapida", "caracteres_min", "caracteres_teto_aviso"),
        "LIMITE_SHORTS": ("shorts", "caracteres_min", "caracteres_teto_aviso"),
    }
    for const, (fmt, kmin, kteto) in esperado_limites.items():
        m = re.search(rf"^{const}\s*=\s*\((\d+),\s*(\d+)\)", src, re.M)
        if not m:
            erros.append(f"{const} não encontrada em generate_script.py")
            continue
        achado = (int(m.group(1)), int(m.group(2)))
        esperado = (contrato["formatos"][fmt][kmin], contrato["formatos"][fmt][kteto])
        if achado != esperado:
            erros.append(
                f"{const} = {achado} mas o contrato diz {esperado} "
                f"(formato {contrato['formatos'][fmt]['rotulo']})"
            )

    esperado_hooks = {
        "HOOK_LIMITE_MAE_PALAVRAS": "mae",
        "HOOK_LIMITE_RAPIDA_PALAVRAS": "rapida",
        "HOOK_LIMITE_SHORTS_PALAVRAS": "shorts",
    }
    for const, fmt in esperado_hooks.items():
        m = re.search(rf"^{const}\s*=\s*(\d+)", src, re.M)
        if not m:
            erros.append(f"{const} não encontrada em generate_script.py")
            continue
        achado = int(m.group(1))
        esperado = contrato["formatos"][fmt]["gancho_max_palavras"]
        if achado != esperado:
            erros.append(f"{const} = {achado} mas o contrato diz {esperado}")

    return erros


def checar_metas_nos_documentos(contrato: dict, pasta: Path) -> list[str]:
    """Cada documento precisa citar as metas do contrato e não pode citar
    valores antigos que o contrato substituiu."""
    erros = []

    # Valores que já circularam e não valem mais. Manter esta lista atualizada é
    # o que evita que uma meta velha sobreviva num canto de prosa.
    obsoletos = {
        "mae": [3800, 4000, 4300],
        "rapida": [1400, 1600],
        "shorts": [500, 650, 850],
    }
    # 650 e 850 já foram metas da shorts; 650 ainda pode aparecer legitimamente
    # dentro da faixa alvo [600, 700], então só acusamos fora desse caso.
    alvo_shorts = contrato["formatos"]["shorts"]["caracteres_alvo"]
    if alvo_shorts[0] <= 650 <= alvo_shorts[1]:
        obsoletos["shorts"].remove(650)

    alvos = {
        "SISTEMA_VIRAL_RECEITARIA.md": True,
        "SISTEMA_VIRAL_PIPELINE.md": True,
    }
    for nome in alvos:
        caminho = pasta / nome
        if not caminho.exists():
            erros.append(f"{nome} não encontrado em {pasta}")
            continue
        texto = caminho.read_text(encoding="utf-8")
        for fmt, dados in contrato["formatos"].items():
            minimo = dados["caracteres_min"]
            if not _contem_numero(texto, minimo):
                erros.append(
                    f"{nome}: não declara o mínimo de {minimo} para o formato "
                    f"{dados['rotulo']}"
                )
            for velho in obsoletos[fmt]:
                if _contem_numero(texto, velho):
                    erros.append(
                        f"{nome}: ainda menciona {velho}, valor obsoleto do "
                        f"formato {dados['rotulo']}"
                    )

    src = GENERATE_SCRIPT.read_text(encoding="utf-8")
    for fmt, dados in contrato["formatos"].items():
        for velho in obsoletos[fmt]:
            # Nas constantes já checamos; aqui é a prosa do FORMATO_SAIDA.
            prosa = src.split("LIMITE_MAE")[0]
            if _contem_numero(prosa, velho):
                erros.append(
                    f"generate_script.py (FORMATO_SAIDA): ainda menciona {velho}, "
                    f"valor obsoleto do formato {dados['rotulo']}"
                )
    return erros


def checar_camada_bonus(contrato: dict, pasta: Path) -> list[str]:
    """A faixa da camada bônus divergia entre os documentos (1:30-1:50 contra
    1:50-2:20). Trava nos três."""
    faixa = next(
        b["faixa"] for b in contrato["blocos_versao_mae"] if "Bônus" in b["nome"]
    )
    inicio, fim = faixa.split("-")  # "1:50", "2:20"

    def variantes(t: str) -> list[str]:
        mm, ss = t.split(":")
        return [f"{mm}:{ss}", f"{mm}min{ss}"]

    erros = []
    for nome in ("SISTEMA_VIRAL_RECEITARIA.md", "SISTEMA_VIRAL_PIPELINE.md"):
        caminho = pasta / nome
        if not caminho.exists():
            continue
        texto = caminho.read_text(encoding="utf-8")
        trecho = re.search(r"[^\n]*CAMADA BÔNUS[^\n]*", texto, re.I)
        if not trecho:
            erros.append(f"{nome}: bloco da camada bônus não encontrado")
            continue
        linha = trecho.group(0)
        if not any(v in linha for v in variantes(inicio)):
            erros.append(
                f"{nome}: camada bônus não começa em {inicio} "
                f"(linha: {linha.strip()[:80]}...)"
            )
    return erros


def checar_rotulos_proibidos(contrato: dict, pasta: Path) -> list[str]:
    """Os rótulos de bloco proibidos precisam estar listados nos três lugares —
    é a regra que impede o agente de inventar estrutura linear."""
    erros = []
    amostra = ["Explicação do Problema", "Por que Funciona"]
    fontes = {
        "SISTEMA_VIRAL_RECEITARIA.md": pasta / "SISTEMA_VIRAL_RECEITARIA.md",
        "SISTEMA_VIRAL_PIPELINE.md": pasta / "SISTEMA_VIRAL_PIPELINE.md",
        "generate_script.py": GENERATE_SCRIPT,
    }
    for nome, caminho in fontes.items():
        if not caminho.exists():
            continue
        texto = caminho.read_text(encoding="utf-8")
        faltando = [r for r in amostra if r not in texto]
        if faltando:
            erros.append(
                f"{nome}: não lista os rótulos proibidos {faltando} — sem isso o "
                "agente volta a inventar blocos de estrutura linear"
            )
    return erros


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--roteiros",
        type=Path,
        default=ROTEIROS_PADRAO,
        help="pasta que contém CONTRATO_FORMATOS.md e os dois manuais",
    )
    args = ap.parse_args()

    if not args.roteiros.exists():
        print(f"Pasta de roteiros não encontrada: {args.roteiros}")
        print("Passe --roteiros ou defina RECEITARIA_ROTEIROS.")
        return 2

    contrato = carregar_contrato(args.roteiros)
    erros: list[str] = []
    erros += checar_constantes_python(contrato)
    erros += checar_metas_nos_documentos(contrato, args.roteiros)
    erros += checar_camada_bonus(contrato, args.roteiros)
    erros += checar_rotulos_proibidos(contrato, args.roteiros)

    print(f"Contrato versão {contrato['versao']}")
    if erros:
        print(f"\n{len(erros)} divergência(s):\n")
        for e in erros:
            print(f"  - {e}")
        return 1
    print("\nOK: manual mestre, pipeline e generate_script.py concordam com o contrato.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
