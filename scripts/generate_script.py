"""
Terceiro passo. Busca a base de conhecimento (SISTEMA_VIRAL_RECEITARIA.md e
BANCO_VIRAIS_RECEITARIA.md) de um Gist privado — não fica commitada nesse
repositório público — e chama a API da Anthropic pra gerar o roteiro, no
formato estruturado que o notion_insert.py sabe montar em blocos ricos (ver
scripts/roteiro_parser.py).

Antes de gerar, confere se o link de origem já é um vencedor conhecido (base
"Banco de Vencedores Próprios") — se for, o roteiro é forçosamente um caso de
"Reciclagem" (remake de algo que já provou funcionar), não uma decisão da IA.
"""
import os
import re
import time

import anthropic
import requests

import context
import notifier
import roteiro_parser

MAX_RETRIES = 3

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
KB_GIST_ID = os.environ["KB_GIST_ID"]
# Pode ser o mesmo valor do GIST_TOKEN (offset do Telegram) colado aqui de novo,
# ou um token dedicado só pra esse Gist — mas precisa existir como secret próprio
# (KB_GIST_TOKEN), o workflow não repassa o GIST_TOKEN pra esse passo.
KB_GIST_TOKEN = os.environ["KB_GIST_TOKEN"]

NOTION_TOKEN = os.environ.get("NOTION_TOKEN")
VENCEDORES_DATABASE_ID = os.environ.get("VENCEDORES_DATABASE_ID")
VENCEDORES_LINK_PROP = "Link"  # nome da propriedade de link na base "Banco de Vencedores Próprios"

SISTEMA_FILENAME = "SISTEMA_VIRAL_RECEITARIA.md"
BANCO_FILENAME = "BANCO_VIRAIS_RECEITARIA.md"

MODEL = "claude-sonnet-5"

CATEGORIAS = [
    "Cabelo & Fios", "Unhas & Micose", "Dores Articulares", "Respiração & Tosse",
    "Fígado & Digestão", "Saúde & Colesterol", "Casa & Pragas", "Saúde Natural",
]
PILARES = ["Limpeza doméstica", "Remédio caseiro", "Reciclagem", "Experimental"]

FORMATO_SAIDA = """
Responda EXATAMENTE nesse formato de tags textuais (sem markdown extra, sem
explicações antes ou depois):

CATEGORIA: [uma das opções: {categorias}]
PILAR: [uma das opções: {pilares}]
TITULO_CURTO: [Mini-título autoexplicativo (Categoria)]

[Número]. [Título Principal do Roteiro]

TITULOS A/B
A: [Opção de Título A - foco em curiosidade ou problema]
B: [Opção de Título B - foco em resultado ou promessa de transformação]

HASHTAGS
#[tag1] #[tag2] #[tag3] #[tag4]

INGREDIENTES
- [Ingrediente 1]
- [Ingrediente 2]

MODO DE PREPARO
1. [Primeiro passo, curto e direto]
2. [Segundo passo]
3. [Passo final / como usar]

ROTEIRO VERSAO-MAE
[0-10s - Gancho]
[Texto falado, 2 a 4 frases completas — não uma linha solta.]

[10-25s - Contexto/História]
[Continuação, 2 a 4 frases completas.]

[25-50s - Explicação do Problema]
[Continuação, 2 a 4 frases completas.]

[50s-2min - Passo a Passo Completo, com detalhe de cada ingrediente]
[Continuação, 2 a 4 frases completas — normalmente precisa de 2 a 3 blocos
de tempo/etapa pra caber o passo a passo inteiro com detalhe, não só 1.]

[2min-2min30 - Por que Funciona]
[Continuação, 2 a 4 frases completas.]

[Tempo final - Chamada para Ação]
[Texto de fechamento, 2 a 3 frases completas.]
Meta de caracteres desta versão: entre 3.600 e 3.700 caracteres de texto
falado (não conte os marcadores de tempo/etapa entre colchetes) — isso
equivale a aproximadamente 650-700 palavras, ou uns 7-9 blocos de
[Tempo - Etapa] como os do exemplo acima, cada um com 2 a 4 frases completas
(nunca frases soltas de uma linha só). ATENÇÃO: o erro mais comum é entregar
essa versão curta demais (na prática, a IA costuma parar por volta de
2.200-2.500 caracteres, bem abaixo da meta) — se ao planejar a resposta você
perceber que vai fechar abaixo de 3.500 caracteres, ANTES de finalizar volte
e desenvolva mais cada bloco (mais detalhe de aplicação, mais explicação do
porquê funciona, mais contexto/história), em vez de simplesmente encerrar
cedo. É uma versão longa de propósito — trate os placeholders do exemplo como
o mínimo de blocos, não o máximo.

ROTEIRO VERSAO-RAPIDA
[0-3s - Gancho]
[Texto da versão de 1 minuto, ritmo acelerado, 2 a 3 frases completas.]

[3-15s - Contexto/Problema]
[Continuação, 2 a 3 frases completas.]

[15-45s - Passo a Passo Resumido]
[Continuação, 2 a 3 frases completas.]

[45s-1min - Chamada para Ação]
[Continuação, 1 a 2 frases completas.]
Meta de caracteres desta versão: entre 1.200 e 1.300 caracteres de texto
falado (não conte os marcadores de tempo/etapa entre colchetes) — uns
200-250 palavras. Mesmo aviso da versão-mãe: não encerre cedo demais, prefira
desenvolver mais cada bloco a ficar abaixo da meta.

ROTEIRO VERSAO-SHORTS
- 0-3s: "[Frase de impacto inicial]"
- 3-18s: "[Lista de benefícios em ritmo curto, sem quantidades exatas, 3 a 5 benefícios]"
- 18-30s: "[Chamada de ação direta]"
Meta de caracteres desta versão: entre 500 e 600 caracteres de texto falado
(não conte os marcadores de tempo entre colchetes) — uns 85-100 palavras.

Regras adicionais:
- TITULO_CURTO deve ser um mini-título autoexplicativo seguido da categoria
  entre parênteses, ex: "Óleo de Alecrim Anticaspa (Cabelo & Fios)" — não
  precisa listar todos os ingredientes literalmente, só comunicar o tema em
  poucas palavras.
- Em INGREDIENTES, cada linha começa com "- " e traz só o item (sem
  quantidade obrigatória, pode incluir se for curto).
- Em MODO DE PREPARO, cada linha começa com "N. " (número sequencial) e é um
  passo curto e imperativo — não escreva parágrafo corrido.
- Não numere nada além do [Número] no título. Não use emoji em cabeçalho,
  tag ou em nenhuma parte da resposta.
- IMPORTANTE sobre tamanho: as metas de caracteres de cada versão (acima) são
  regra obrigatória, não sugestão. O padrão de erro mais comum é entregar
  texto curto demais, principalmente na VERSAO-MAE. Antes de finalizar cada
  versão, conte mentalmente se já bateu a meta mínima — se não bateu,
  desenvolva mais em vez de encerrar.
""".strip()

LIMITE_MAE = (3600, 3700)
LIMITE_RAPIDA = (1200, 1300)
LIMITE_SHORTS = (500, 600)


_MARCADOR_COLCHETES_RE = re.compile(r"\[[^\]]*\]")


def _tamanho_falado(texto: str) -> int:
    """Conta caracteres do texto falado, removendo marcadores de tempo/etapa
    entre colchetes (ex: '[1:00-1:15 - Resultado + CTA]') em qualquer posição
    da linha — sozinhos numa linha própria ou grudados com o texto de
    narração — e ignorando linhas de meta que porventura vazem pro conteúdo.
    Os colchetes continuam no roteiro salvo (são referência de edição), só não
    entram na contagem que valida a meta de caracteres."""
    linhas = []
    for l in texto.splitlines():
        l = _MARCADOR_COLCHETES_RE.sub("", l).strip()
        if not l or l.lower().startswith("meta de caracteres"):
            continue
        linhas.append(l)
    return len(" ".join(linhas))


def _fora_da_meta(parsed: dict) -> list[str]:
    problemas = []
    tam_mae = _tamanho_falado(parsed["versao_mae"])
    if not (LIMITE_MAE[0] <= tam_mae <= LIMITE_MAE[1]):
        problemas.append(f"VERSAO-MAE tem {tam_mae} caracteres (meta: {LIMITE_MAE[0]}-{LIMITE_MAE[1]}).")
    tam_rapida = _tamanho_falado(parsed["versao_rapida"])
    if not (LIMITE_RAPIDA[0] <= tam_rapida <= LIMITE_RAPIDA[1]):
        problemas.append(f"VERSAO-RAPIDA tem {tam_rapida} caracteres (meta: {LIMITE_RAPIDA[0]}-{LIMITE_RAPIDA[1]}).")
    tam_shorts = _tamanho_falado(parsed["versao_shorts"])
    if not (LIMITE_SHORTS[0] <= tam_shorts <= LIMITE_SHORTS[1]):
        problemas.append(f"VERSAO-SHORTS tem {tam_shorts} caracteres (meta: {LIMITE_SHORTS[0]}-{LIMITE_SHORTS[1]}).")
    return problemas


def fetch_kb() -> str:
    resp = requests.get(
        f"https://api.github.com/gists/{KB_GIST_ID}",
        headers={"Authorization": f"Bearer {KB_GIST_TOKEN}", "Accept": "application/vnd.github+json"},
        timeout=15,
    )
    resp.raise_for_status()
    files = resp.json()["files"]
    sistema = files[SISTEMA_FILENAME]["content"]
    banco = files[BANCO_FILENAME]["content"]
    return (
        f"# SISTEMA_VIRAL_RECEITARIA.md\n\n{sistema}\n\n"
        f"# BANCO_VIRAIS_RECEITARIA.md\n\n{banco}"
    )


def find_vencedor_match(source_url: str):
    """Se o link de origem já está no Banco de Vencedores Próprios, devolve
    (page_id, nome) desse vencedor — indica que isso é uma Reciclagem, não uma
    decisão de categoria da IA."""
    if not (source_url and NOTION_TOKEN and VENCEDORES_DATABASE_ID):
        return None
    url = f"https://api.notion.com/v1/databases/{VENCEDORES_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    payload = {"filter": {"property": VENCEDORES_LINK_PROP, "url": {"equals": source_url}}}
    for attempt in range(MAX_RETRIES):
        resp = requests.post(url, headers=headers, json=payload, timeout=15)
        if resp.status_code != 429 or attempt == MAX_RETRIES - 1:
            resp.raise_for_status()
            break
        wait = float(resp.headers.get("Retry-After", 1)) * (attempt + 1)
        time.sleep(wait)
    results = resp.json().get("results", [])
    if not results:
        return None
    page = results[0]
    title_prop = next(iter(page["properties"].values()))
    nome = "".join(t["plain_text"] for t in title_prop.get("title", [])) or "vencedor sem nome"
    return page["id"], nome


def build_system_prompt(kb: str, vencedor_nome: str | None, use_cache: bool):
    """Monta o prompt de sistema. A parte estável (instruções + formato + base de
    conhecimento) é idêntica em toda chamada — quando use_cache=True, ela vai num
    bloco próprio com cache_control, e a instrução de reciclagem (que varia por
    vídeo) fica de fora, no final, pra não invalidar o prefixo cacheado.
    use_cache só deve vir True quando o telegram_poll.py detectou mais de um
    vídeo no mesmo ciclo — com um vídeo só, o prêmio de escrita do cache custa
    mais do que não cachear (ver TTL 1h: escrita 2x vs leitura 0,1x)."""
    instrucoes_reciclagem = (
        f'ATENÇÃO: este vídeo de referência já é um vencedor conhecido do seu histórico '
        f'("{vencedor_nome}"). Isso é uma RECICLAGEM — use "PILAR: Reciclagem" obrigatoriamente, '
        f"e mantenha a estrutura/gancho que já provou funcionar, só refrescando ângulo/frase de "
        f"abertura pra não soar repetido."
        if vencedor_nome else ""
    )
    stable_prompt = (
        "Você é o redator viral da Receitaria Curiosa. Use a base de conhecimento abaixo "
        "(regras de linguagem, frameworks de gancho, banco de roteiros testados) para "
        "escrever um roteiro novo de vídeo curto, no mesmo estilo e estrutura dos roteiros "
        "vencedores, a partir da transcrição de um vídeo de referência que o usuário vai "
        "fornecer. Não copie a transcrição literalmente — adapte pro formato e gancho de "
        "vídeo curto, respeitando as regras de linguagem/compliance do documento (evitar "
        "termos clínicos e frases de watchbait)."
        + "\n\n" + FORMATO_SAIDA.format(categorias=", ".join(CATEGORIAS), pilares=", ".join(PILARES))
        + "\n\n" + kb
        + "\n\n⚠️ ATENÇÃO — CONFLITO DE FORMATO: a base de conhecimento acima tem uma seção "
        "'FORMATO DE ENTREGA OBRIGATÓRIO' (com blocos 📊 ANÁLISE, 🔴🟠🟡 ROTEIRO) pensada pra "
        "colar manualmente no agente Cowork — NÃO é o formato que você deve usar aqui. Aqui, "
        "IGNORE COMPLETAMENTE aquela seção e use EXCLUSIVAMENTE o formato de tags de texto puro "
        "definido acima (CATEGORIA:, PILAR:, TITULO_CURTO:, TITULOS A/B, HASHTAGS, INGREDIENTES, "
        "MODO DE PREPARO, ROTEIRO VERSAO-MAE, ROTEIRO VERSAO-RAPIDA, ROTEIRO VERSAO-SHORTS) — um "
        "script vai fazer parsing automático da sua resposta procurando exatamente essas tags, sem "
        "markdown, sem emoji nos cabeçalhos, sem texto antes ou depois. As metas de caracteres "
        "informadas em cada versão do roteiro acima têm PRIORIDADE sobre qualquer meta de caracteres "
        "mencionada na base de conhecimento — siga sempre as metas definidas aqui."
    )

    if not use_cache:
        return stable_prompt + ("\n\n" + instrucoes_reciclagem if instrucoes_reciclagem else "")

    system = [{
        "type": "text",
        "text": stable_prompt,
        "cache_control": {"type": "ephemeral", "ttl": "1h"},
    }]
    if instrucoes_reciclagem:
        system.append({"type": "text", "text": instrucoes_reciclagem})
    return system


def main() -> None:
    ctx = context.load()
    kb = fetch_kb()
    vencedor = find_vencedor_match(ctx.get("source_url"))
    use_cache = bool(ctx.get("use_cache"))
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = build_system_prompt(kb, vencedor[1] if vencedor else None, use_cache)
    user_content = (
        f"Transcrição do vídeo de referência (plataforma: {ctx.get('platform') or 'anexo enviado direto'}, "
        f"link de origem: {ctx.get('source_url') or 'sem link, mídia enviada direto no Telegram'}):\n\n"
        f"{ctx['transcript']}"
    )
    messages = [{"role": "user", "content": user_content}]

    kwargs = dict(
        model=MODEL,
        max_tokens=8192,
        # claude-sonnet-5 roda com "adaptive thinking" ligado por padrão quando esse
        # parâmetro é omitido (diferente do Sonnet 4.6) - sem desligar, o "pensamento"
        # pode consumir o max_tokens inteiro antes de escrever o roteiro, devolvendo
        # resposta vazia. Essa tarefa é só formatação seguindo um template, não precisa
        # de raciocínio em múltiplas etapas.
        thinking={"type": "disabled"},
        system=system_prompt,
    )

    message = client.messages.create(messages=messages, **kwargs)
    roteiro_text = "".join(block.text for block in message.content if block.type == "text")
    parsed = roteiro_parser.parse(roteiro_text)
    problemas = _fora_da_meta(parsed)

    if problemas:
        print(f"--- Fora da meta de caracteres, tentando 1x corrigir: {problemas} ---")
        messages.append({"role": "assistant", "content": roteiro_text})
        messages.append({"role": "user", "content": (
            "Sua resposta anterior ficou fora da meta de caracteres exigida:\n"
            + "\n".join(f"- {p}" for p in problemas)
            + "\n\nReescreva a resposta INTEIRA (mesmo formato de tags, do zero, "
            "incluindo CATEGORIA/PILAR/TITULO_CURTO), ajustando o tamanho dessas "
            "versões pra caber dentro da meta, sem perder o gancho nem virar "
            "telegráfico demais. Não adicione comentário fora do formato."
        )})
        retry_msg = client.messages.create(messages=messages, **kwargs)
        roteiro_retry = "".join(b.text for b in retry_msg.content if b.type == "text")
        parsed_retry = roteiro_parser.parse(roteiro_retry)
        # só troca se a segunda tentativa realmente melhorou o parsing/tamanho;
        # senão fica com a primeira resposta (parseável) - ter algo é melhor que
        # arriscar um retry pior.
        if parsed_retry["versao_mae"] or parsed_retry["versao_rapida"]:
            roteiro_text = roteiro_retry
            message = retry_msg
        print(f"--- Após retry: {_fora_da_meta(parsed_retry) or 'dentro da meta'} ---")

    if use_cache:
        print(
            f"--- Cache de prompt: escrita={message.usage.cache_creation_input_tokens} "
            f"tokens, leitura={message.usage.cache_read_input_tokens} tokens ---"
        )

    print(f"--- stop_reason: {message.stop_reason} ---")
    print("--- Resposta bruta da Claude (primeiros 500 chars) ---")
    print(roteiro_text[:500])
    print("--- fim do trecho ---")

    # troca o rótulo provisório (link/legenda) pelo tema+categoria de verdade
    # assim que dá pra saber - as mensagens de Telegram daqui pra frente (e o
    # aviso de sucesso desta própria etapa) passam a identificar o vídeo certo.
    parsed_final = roteiro_parser.parse(roteiro_text)
    titulo_final = parsed_final.get("titulo_curto") or parsed_final.get("titulo")
    update_kwargs = dict(
        roteiro=roteiro_text,
        vencedor_relacionado_id=vencedor[0] if vencedor else None,
    )
    if titulo_final:
        update_kwargs["rotulo"] = titulo_final
    context.update(**update_kwargs)


if __name__ == "__main__":
    notifier.run_stage(
        etapa="escrever o roteiro",
        inicio="✍️ Escrevendo o roteiro no seu estilo...",
        sucesso="✅ Roteiro pronto. Agora vou salvar no Notion.",
        func=main,
        dica_erro="Pode ser algo na base de conhecimento (os Gists) ou na chave da Anthropic.",
    )
