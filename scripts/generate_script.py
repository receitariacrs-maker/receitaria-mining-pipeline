"""
Terceiro passo. Busca a base de conhecimento condensada do pipeline
(SISTEMA_VIRAL_PIPELINE.md) de um Gist privado — não fica commitada nesse
repositório público — e chama a API da Anthropic pra gerar o roteiro, no
formato estruturado que o notion_insert.py sabe montar em blocos ricos (ver
scripts/roteiro_parser.py).

Decisões de custo (jul/2026): a KB embutida é a versão pipeline (~21k chars),
não mais SISTEMA+BANCO completos (~175k chars) — entrada caiu de ~78k pra
~15k tokens por chamada. E NÃO existe retry: o prompt usa contrato estrutural
(4 frases por ingrediente) + overshoot de tamanho pra acertar de primeira;
qualquer desvio vira aviso de QA visível (log/Notion/Telegram), nunca segunda
chamada.

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

# Versão condensada da KB feita sob medida pro pipeline (~21k chars vs ~175k
# da dupla SISTEMA+BANCO completa) - é o que derrubou o custo de entrada de
# ~78k pra ~15k tokens por chamada. O documento-mestre continua sendo o
# SISTEMA_VIRAL_RECEITARIA.md (uso manual no Cowork); se a metodologia mudar
# lá, regenerar o arquivo pipeline e subir pro mesmo Gist.
PIPELINE_FILENAME = "SISTEMA_VIRAL_PIPELINE.md"

MODEL = "claude-sonnet-5"

CATEGORIAS = [
    "Cabelo & Fios", "Unhas & Micose", "Dores Articulares", "Respiração & Tosse",
    "Fígado & Digestão", "Saúde & Colesterol", "Casa & Pragas", "Saúde Natural",
]
PILARES = ["Limpeza doméstica", "Remédio caseiro", "Reciclagem", "Experimental"]

FAMILIAS_GANCHO = [
    'Curiosidade ("Você sabia que...")',
    'Comando direto / pattern interrupt ("Jogue/Coloque/Misture X no Y")',
    'Promessa absoluta ("[Ação] e nunca mais [dor]")',
    'Autoridade folk ("Minha avó/senhor da roça ensinou")',
    'Testemunho pessoal com número ("Misturei X e [resultado] há N anos")',
    'Tabu / anti-estabelecimento ("Pare de [hábito comum]")',
]

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
- [Quantidade] [Ingrediente 1]
- [Quantidade] [Ingrediente 2]

MODO DE PREPARO
1. [Primeiro passo, curto e direto]
2. [Segundo passo]
3. [Passo final / como usar]

ANALISE_GANCHO
Antes de escrever os roteiros, preencha esse bloco de análise — é seu
raciocínio estruturado sobre o gancho do vídeo de referência, e deve guiar
as 3 versões abaixo.
FAMILIA_GANCHO: [uma das opções: {familias_gancho}]
GANCHO_ORIGINAL: [resumo de até ~15 palavras da ideia central do gancho do vídeo de referência - não copie a frase literal]
INGREDIENTE_ANCORA: [o ingrediente/elemento central que ancora a promessa]
PROMESSA: [o resultado/benefício que o gancho vende - nunca a receita/quantidade de ingredientes]
GATILHO: [o gatilho psicológico: curiosidade, urgência, autoridade, prova social, tabu, etc.]
AJUSTE_VERACIDADE: [o que precisou ser ajustado, se algo, pra o gancho original ficar verídico - ou "nenhum, gancho original já era verídico"]

ROTEIRO VERSAO-MAE
[0-10s - Gancho + Micro-promessa]
[Texto falado, 2 a 4 frases completas — não uma linha solta. Família do
gancho de referência + combinação inusitada + número específico + promessa.]

[10-25s - Começa a Receita JÁ (primeiro ingrediente)]
[2 a 4 frases: primeiro ingrediente na mão e o preparo começando de verdade.
NUNCA liste todos os ingredientes de uma vez — cada um é revelado só no
momento em que entra em cena.]

[25s-1min - Execução Intercalada (parte 1)]
[Para CADA ingrediente revelado, 4 frases: mostra o ingrediente + ação visual
(cortar/amassar/misturar) + micro-benefício popular (1 frase folk, nunca
clínica) + costura emocional/narrativa (1 frase de dor, autoridade folk ou
história pessoal — 1 pedaço por ingrediente, NUNCA tudo junto).]

[1min-1min50 - Execução Intercalada (parte 2)]
[Continuação da execução, mesma fórmula de 4 frases por ingrediente, até
fechar TODOS os ingredientes da receita.]

[1min50-2min20 - Camada Bônus]
[2 a 4 frases: uma dica extra ENTREGUE na hora (variação de uso,
armazenamento, resultado adicional) — nunca anunciada sem entregar.]

[2min20-2min50 - Modo de Uso + Reforço da Promessa]
[3 a 5 frases: frequência, duração, quando usar, validade. Fecha repetindo a
promessa absoluta do gancho como confirmação.]

[2min50-3min10 - Fechamento (salvar/compartilhar, SEM comentário)]
[2 a 3 frases com gatilho de salvamento ou compartilhamento ("Salva esse
vídeo antes de esquecer." / "Manda pra alguém que precisa disso agora.").
PROIBIDO pedir comentário nesta versão.]
ESTRUTURA OBRIGATÓRIA desta versão: PROIBIDO criar um bloco separado de
"explicação do problema" ou "por que funciona" antes ou depois do passo a
passo — a explicação vive DENTRO da execução intercalada, 1 frase por
ingrediente (o micro-benefício + a costura). Dor/contexto em bloco isolado
nos primeiros 20s é o erro que mais derruba retenção.
Meta de caracteres desta versão: MÍNIMO INEGOCIÁVEL de 3.600 caracteres de
texto falado (não conte os marcadores de tempo/etapa entre colchetes); MIRE
em 3.800-4.000 caracteres (700-750 palavras) — a margem acima do mínimo é
deliberada, porque o erro sistemático é entregar curto demais. O volume vem
da ESTRUTURA: com 5-7 ingredientes × 4 frases cada na execução intercalada,
mais os blocos fixos (gancho, início da receita, bônus, modo de uso,
fechamento), as 700+ palavras saem naturalmente — se a receita tiver poucos
ingredientes, desenvolva mais a costura narrativa, a camada bônus e o modo
de uso, nunca encerre cedo. Essa meta NUNCA deve ser buscada alongando o
gancho/primeira frase — volume extra vai na execução e nos blocos finais.

ROTEIRO VERSAO-RAPIDA
[0-3s - Gancho]
[1 a 2 frases, mesma família do gancho da mãe, comprimido e direto.]

[3-45s - Preparo Passo a Passo (ingredientes um a um)]
[Ingredientes revelados um a um no momento de uso — SEM listar todos no
início. 1 micro-benefício popular por ingrediente (1 frase só). Quantidades
podem ser mencionadas normalmente. Use 2 blocos de tempo se precisar.]

[45-55s - Modo de Uso]
[1 a 3 frases.]

[55s-1min - Fechamento (salvar, SEM comentário)]
["Salva esse vídeo antes de esquecer." ou equivalente. PROIBIDO pedir
comentário nesta versão.]
Meta de caracteres desta versão: MÍNIMO de 1.200 caracteres de texto falado
(não conte os marcadores); MIRE em 1.300-1.400 (230-260 palavras). Não
encerre cedo: desenvolva o passo a passo, nunca o gancho.

ROTEIRO VERSAO-SHORTS
- 0-3s: "[Gancho ultra-enxuto, mesma família da mãe, 6-8 palavras]"
- 3-22s: "[3 a 5 benefícios em ritmo de lista, linguagem popular, SEM NENHUMA quantidade/medida/proporção — as quantidades omitidas são o gatilho do CTA]"
- 22-30s: "[CTA OBRIGATÓRIA fechando o roteiro, com a palavra RECEITA em caixa alta: 'Comenta RECEITA aqui pra receber a receita com as quantidades exatas e entrar no nosso grupo VIP — receita nova todo dia e sorteios só pra quem é do grupo.' ou variação equivalente]"
Meta de caracteres desta versão: MÍNIMO de 500 caracteres de texto falado
(não conte os marcadores); MIRE em 550-650 (95-110 palavras). Use os 5
benefícios (não 3) na linha do meio, com frases completas em vez de
fragmentos telegráficos. A linha final de CTA com RECEITA é obrigatória —
um shorts sem ela não capta lead e é considerado errado.

Regras adicionais:
- TITULO_CURTO deve ser um mini-título autoexplicativo seguido da categoria
  entre parênteses, ex: "Óleo de Alecrim Anticaspa (Cabelo & Fios)" — não
  precisa listar todos os ingredientes literalmente, só comunicar o tema em
  poucas palavras.
- Em INGREDIENTES, cada linha começa com "- " e traz a quantidade JUNTO com o
  item, ex: "- 2 colheres de sopa de mel" — quantidade é obrigatória em cada
  item (é a lista prática que o usuário usa pra separar tudo antes de
  gravar); se a transcrição de referência não disser a quantidade exata,
  estime uma quantidade razoável em vez de omitir.
- Em MODO DE PREPARO, cada linha começa com "N. " (número sequencial) e é um
  passo curto e imperativo — não escreva parágrafo corrido.
- Não numere nada além do [Número] no título. Não use emoji em cabeçalho,
  tag ou em nenhuma parte da resposta.
- IMPORTANTE sobre tamanho: os MÍNIMOS de caracteres de cada versão (acima)
  são regra obrigatória, não sugestão — e o alvo é sempre a faixa "MIRE em",
  acima do mínimo. O padrão de erro mais comum é entregar texto curto demais,
  principalmente na VERSAO-MAE. Siga o contrato estrutural (4 frases por
  ingrediente na execução intercalada, todos os blocos presentes) e o volume
  sai naturalmente — se um bloco ficou com 1-2 frases, desenvolva antes de
  finalizar.
- CTA por formato (hierarquia fixa, nunca trocar): a VERSAO-SHORTS SEMPRE
  fecha com o CTA de comentário RECEITA (palavra em caixa alta, só nessa
  versão) — sem ele o vídeo não capta lead. VERSAO-MAE e VERSAO-RAPIDA NUNCA
  pedem comentário (nem usam RECEITA em caixa alta) — fecham com gatilho de
  salvar/compartilhar. PROIBIDO em qualquer CTA: "link na bio", "direct",
  "DM", "inbox", "te mando", "te chamo", "te envio" — o verbo é sempre
  comentar/escrever/deixar + receber/entrar/fazer parte.
- PRESERVAÇÃO DO GANCHO (a regra mais importante sobre o gancho): não troque
  a estrutura/intensidade do gancho do vídeo de referência (ver abertura
  literal fornecida na mensagem do usuário) por algo genérico. Se o gancho
  original fizer uma alegação falsa ou exagerada sobre um ingrediente
  específico, mantenha a MESMA estrutura de frase e o MESMO nível de
  impacto — troque só o elemento falso por um ingrediente/mecanismo real que
  sustente uma promessa parecida ("mais leve" o suficiente pra ser
  verdadeiro, nunca watered-down genérico). Modificação radical do gancho só
  se o restante do roteiro (passo a passo, ingredientes reais) não sustentar
  mais a promessa original de jeito nenhum.
- Regra anti-spoiler do gancho: o gancho vende o RESULTADO, nunca a receita —
  proibido revelar quantidade de ingredientes ou estrutura do passo a passo
  na frase de abertura (ex: proibido "quatro ingredientes que...", "três
  coisas simples...").
- Mesma família de gancho nos 3 formatos: VERSAO-MAE, VERSAO-RAPIDA e
  VERSAO-SHORTS compartilham a MESMA família de gancho (ver FAMILIA_GANCHO
  em ANALISE_GANCHO) e a mesma ideia central — só o tamanho muda. Proibido a
  mãe usar uma família (ex: autoridade folk) e o shorts usar outra (ex:
  comando direto).
- Orçamento de palavras do gancho: a primeira frase falada de cada versão
  deve ser curta e de altíssimo impacto — até ~10 palavras na mãe, ~10-12 na
  rápida, ~6-8 no shorts. Nunca mais longo que isso.
- Ponte gancho → ação: logo após o gancho curto, a AÇÃO começa (primeiro
  ingrediente na mão) — a autoridade/origem (quem ensinou, há quanto tempo)
  entra em UMA frase curta na transição ou diluída na costura do primeiro
  ingrediente, nunca como bloco de história antes da receita começar.
- Erro comum a evitar (proibido): NUNCA abra com uma cena/anedota longa
  contando como você "descobriu" o truque (ex: "Descobri isso por acaso,
  quando fui trocar o lençol num domingo de manhã e vi que o colchão tinha
  ficado todo amarelado..."). Isso é sempre genérico, alonga o gancho e
  ignora a ideia central do vídeo de referência. Abra DIRETO com o
  resultado/promessa, no mesmo estilo do gancho original — ex: se o gancho de
  referência é "Depois que aprendi esse truque meu colchão fica sempre
  branquinho e perfumado", a abertura adaptada continua sendo resultado
  direto ("Meu colchão fica branquinho e perfumado com um truque só"), nunca
  uma cena de descoberta contada em detalhe. A cena/anedota, se fizer
  sentido, entra diluída na costura da execução intercalada (1 frase por
  ingrediente), nunca antes do gancho nem como bloco isolado.
""".strip()

# Mínimo inegociável e teto brando de texto falado por versão. Abaixo do
# mínimo o vídeo não atinge a duração-alvo; acima do teto o ritmo cai. Não há
# mais retry — qualquer violação vira AVISO visível (log, callout de QA no
# Notion e mensagem no Telegram), nunca uma segunda chamada de API.
LIMITE_MAE = (3600, 4300)
LIMITE_RAPIDA = (1200, 1600)
LIMITE_SHORTS = (500, 800)

# Tetos soltos (só teto, nunca piso) pra quantas palavras a primeira frase
# falada de cada versão pode ter - contar palavra em português tem margem de
# erro (contrações, aspas), por isso a folga em relação à meta "ideal" da KB
# (~10/~10-12/~6-8) que fica só no texto do prompt, não na validação.
HOOK_LIMITE_MAE_PALAVRAS = 14
HOOK_LIMITE_RAPIDA_PALAVRAS = 14
HOOK_LIMITE_SHORTS_PALAVRAS = 10


def _tamanho_falado(texto: str) -> int:
    """Conta caracteres do texto falado, removendo marcadores de tempo/etapa
    entre colchetes (ex: '[1:00-1:15 - Resultado + CTA]') em qualquer posição
    da linha — sozinhos numa linha própria ou grudados com o texto de
    narração — e ignorando linhas de meta que porventura vazem pro conteúdo.
    Os colchetes continuam no roteiro salvo (são referência de edição), só não
    entram na contagem que valida a meta de caracteres."""
    linhas = []
    for l in texto.splitlines():
        l = roteiro_parser.MARCADOR_COLCHETES_RE.sub("", l).strip()
        if not l or l.lower().startswith("meta de caracteres"):
            continue
        linhas.append(l)
    return len(" ".join(linhas))


def _extrair_abertura_referencia(transcript: str, max_palavras: int = 40) -> str:
    """Pega literalmente as 2 primeiras frases da transcrição de referência
    (o gancho de verdade que já funcionou nesse vídeo) pra destacar na
    mensagem do usuário — em vez de confiar que a IA vai localizar sozinha o
    gancho dentro de uma transcrição longa. Texto literal, sem reescrever.
    Nunca lança exceção: sem pontuação detectável, cai pro corte por palavra;
    transcrição vazia devolve string vazia."""
    transcript = (transcript or "").strip()
    if not transcript:
        return ""
    frases = re.split(r"(?<=[.!?])\s+", transcript, maxsplit=2)
    abertura = " ".join(frases[:2]).strip()
    if not abertura:
        abertura = transcript
    palavras = abertura.split()
    if len(palavras) > max_palavras:
        abertura = " ".join(palavras[:max_palavras]) + "..."
    return abertura


# CTA de comentário: obrigatória (com RECEITA em caixa alta) só na shorts;
# proibida na mãe e na rápida. As regexes são deliberadamente simples — o
# objetivo é pegar o caso comum, não cobrir toda variação de frase.
CTA_COMENTARIO_RE = re.compile(r"coment\w*[^.!?\n]{0,40}\breceita\b", re.IGNORECASE)


def _avisos_qa(parsed: dict) -> list[str]:
    """Checagens programáticas de qualidade (tamanho, gancho, CTA). Sem retry:
    o resultado vira aviso visível (log + Notion + Telegram), nunca segunda
    chamada de API."""
    avisos = []
    for nome, texto, (minimo, teto) in (
        ("VERSAO-MAE", parsed["versao_mae"], LIMITE_MAE),
        ("VERSAO-RAPIDA", parsed["versao_rapida"], LIMITE_RAPIDA),
        ("VERSAO-SHORTS", parsed["versao_shorts"], LIMITE_SHORTS),
    ):
        tam = _tamanho_falado(texto)
        if tam < minimo:
            avisos.append(f"{nome} tem {tam} caracteres falados (mínimo: {minimo}) - saiu curta, vídeo pode não atingir a duração-alvo.")
        elif tam > teto:
            avisos.append(f"{nome} tem {tam} caracteres falados (teto: ~{teto}) - saiu longa, ritmo pode cair.")

    if parsed["versao_mae"]:
        n = len(roteiro_parser.primeira_frase_falada(parsed["versao_mae"]).split())
        if n > HOOK_LIMITE_MAE_PALAVRAS:
            avisos.append(f"Gancho da VERSAO-MAE tem {n} palavras (meta: até {HOOK_LIMITE_MAE_PALAVRAS}) - primeira frase longa/genérica.")
    if parsed["versao_rapida"]:
        n = len(roteiro_parser.primeira_frase_falada(parsed["versao_rapida"]).split())
        if n > HOOK_LIMITE_RAPIDA_PALAVRAS:
            avisos.append(f"Gancho da VERSAO-RAPIDA tem {n} palavras (meta: até {HOOK_LIMITE_RAPIDA_PALAVRAS}) - primeira frase longa/genérica.")
    if parsed["versao_shorts"]:
        n = len(roteiro_parser.primeira_linha_shorts(parsed["versao_shorts"]).split())
        if n > HOOK_LIMITE_SHORTS_PALAVRAS:
            avisos.append(f"Gancho da VERSAO-SHORTS tem {n} palavras (meta: até {HOOK_LIMITE_SHORTS_PALAVRAS}) - frase de impacto longa.")

    if parsed["versao_shorts"] and not re.search(r"\bRECEITA\b", parsed["versao_shorts"]):
        avisos.append("VERSAO-SHORTS sem o CTA de comentário RECEITA (obrigatório nesse formato - sem ele o vídeo não capta lead).")
    for nome, texto in (("VERSAO-MAE", parsed["versao_mae"]), ("VERSAO-RAPIDA", parsed["versao_rapida"])):
        if texto and CTA_COMENTARIO_RE.search(texto):
            avisos.append(f"{nome} contém CTA de comentário (proibido nesse formato - deve fechar só com salvar/compartilhar).")

    return avisos


def fetch_kb() -> str:
    resp = requests.get(
        f"https://api.github.com/gists/{KB_GIST_ID}",
        headers={"Authorization": f"Bearer {KB_GIST_TOKEN}", "Accept": "application/vnd.github+json"},
        timeout=15,
    )
    resp.raise_for_status()
    files = resp.json()["files"]
    pipeline = files.get(PIPELINE_FILENAME, {}).get("content")
    if not pipeline:
        # Sem fallback pra KB completa de propósito: cair silenciosamente pra
        # SISTEMA+BANCO inteiros voltaria ao custo antigo (~5x) sem ninguém ver.
        raise RuntimeError(
            f"{PIPELINE_FILENAME} não encontrado (ou vazio) no Gist da KB ({KB_GIST_ID}). "
            "Suba a versão condensada do pipeline pro Gist antes de gerar roteiro."
        )
    return f"# SISTEMA_VIRAL_PIPELINE.md\n\n{pipeline}"


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
        "(regras de estrutura intercalada, famílias de gancho, léxico viral, CTA por "
        "formato e exemplos padrão-ouro) para escrever um roteiro novo a partir da "
        "transcrição de um vídeo de referência que o usuário vai fornecer. Não copie a "
        "transcrição literalmente — adapte pro estilo Receitaria, respeitando as regras de "
        "linguagem/compliance (nada de termos clínicos nem watchbait). Sua resposta será "
        "parseada automaticamente por um script: use EXCLUSIVAMENTE o formato de tags de "
        "texto puro definido a seguir, sem markdown, sem emoji, sem texto antes ou depois."
        + "\n\n" + FORMATO_SAIDA.format(
            categorias=", ".join(CATEGORIAS),
            pilares=", ".join(PILARES),
            familias_gancho=", ".join(FAMILIAS_GANCHO),
        )
        + "\n\n" + kb
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
    abertura_referencia = _extrair_abertura_referencia(ctx["transcript"])
    user_content = (
        (
            f'Abertura literal da transcrição do vídeo de referência — o gancho que já '
            f'funcionou nesse vídeo. Preserve ao MÁXIMO a estrutura e a intensidade dessa '
            f'abertura. NÃO copie a frase literal e NÃO troque por um gancho genérico — só '
            f'ajuste se a alegação for falsa/exagerada, e nesse caso troque apenas o elemento '
            f'falso (ex: o ingrediente) por algo real de eficácia comparável, mantendo o resto '
            f'da estrutura e o impacto:\n\n"{abertura_referencia}"\n\n'
            if abertura_referencia else ""
        )
        + f"Transcrição completa do vídeo de referência (plataforma: {ctx.get('platform') or 'anexo enviado direto'}, "
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

    # Sem retry (decisão deliberada de custo): o prompt foi desenhado pra
    # acertar de primeira (contrato estrutural + overshoot de tamanho). Se algo
    # sair fora, vira aviso visível — nunca uma segunda chamada de API.
    avisos = _avisos_qa(parsed)
    if avisos:
        print(f"--- Avisos de QA (sem retry, roteiro segue mesmo assim): {avisos} ---")
        notifier.success("⚠️ Roteiro gerado com avisos de QA:\n- " + "\n- ".join(avisos))
    else:
        print("--- QA ok: tamanhos, ganchos e CTAs dentro do esperado ---")

    print(
        f"--- Uso de tokens: entrada={message.usage.input_tokens}, "
        f"saída={message.usage.output_tokens} ---"
    )

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
        qa_avisos=avisos,
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
