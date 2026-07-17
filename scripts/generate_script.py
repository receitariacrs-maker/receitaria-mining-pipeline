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
import time

import anthropic
import requests

import context
import notifier

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

[Número]. [Título Principal do Roteiro]

TITULOS A/B
A: [Opção de Título A - foco em curiosidade ou problema]
B: [Opção de Título B - foco em resultado ou promessa de transformação]

HASHTAGS
#[tag1] #[tag2] #[tag3] #[tag4]

RECEITA RESUMIDA
- [Ingrediente 1]
- [Ingrediente 2]
[Instruções de preparo e uso em um parágrafo contínuo, sem listas nem traços.]

ROTEIRO VERSAO-MAE
[0-10s - Etapa]
[Texto falado da versão mãe, com detalhes e aplicação.]

[10-25s - Etapa]
[Continuação...]

[Tempo final - Chamada para Ação]
[Texto de fechamento.]

ROTEIRO VERSAO-RAPIDA
[0-3s - Etapa]
[Texto da versão de 1 minuto, ritmo acelerado.]

[3-10s - Etapa]
[Continuação...]

ROTEIRO VERSAO-SHORTS
- 0-3s: "[Frase de impacto inicial]"
- 3-18s: "[Lista de benefícios em ritmo curto]"
- 18-30s: "[Chamada de ação direta]"

Não numere nada além do [Número] no título. Não use emoji nos cabeçalhos.
""".strip()


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
        "definido acima (CATEGORIA:, PILAR:, TITULOS A/B, HASHTAGS, RECEITA RESUMIDA, ROTEIRO "
        "VERSAO-MAE, ROTEIRO VERSAO-RAPIDA, ROTEIRO VERSAO-SHORTS) — um script vai fazer parsing "
        "automático da sua resposta procurando exatamente essas tags, sem markdown, sem emoji nos "
        "cabeçalhos, sem texto antes ou depois."
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

    message = client.messages.create(
        model=MODEL,
        max_tokens=8192,
        # claude-sonnet-5 roda com "adaptive thinking" ligado por padrão quando esse
        # parâmetro é omitido (diferente do Sonnet 4.6) - sem desligar, o "pensamento"
        # pode consumir o max_tokens inteiro antes de escrever o roteiro, devolvendo
        # resposta vazia. Essa tarefa é só formatação seguindo um template, não precisa
        # de raciocínio em múltiplas etapas.
        thinking={"type": "disabled"},
        system=build_system_prompt(kb, vencedor[1] if vencedor else None, use_cache),
        messages=[{
            "role": "user",
            "content": (
                f"Transcrição do vídeo de referência (plataforma: {ctx.get('platform') or 'anexo enviado direto'}, "
                f"link de origem: {ctx.get('source_url') or 'sem link, mídia enviada direto no Telegram'}):\n\n"
                f"{ctx['transcript']}"
            ),
        }],
    )

    if use_cache:
        print(
            f"--- Cache de prompt: escrita={message.usage.cache_creation_input_tokens} "
            f"tokens, leitura={message.usage.cache_read_input_tokens} tokens ---"
        )

    roteiro_text = "".join(block.text for block in message.content if block.type == "text")
    print(f"--- stop_reason: {message.stop_reason} ---")
    print("--- Resposta bruta da Claude (primeiros 500 chars) ---")
    print(roteiro_text[:500])
    print("--- fim do trecho ---")
    context.update(
        roteiro=roteiro_text,
        vencedor_relacionado_id=vencedor[0] if vencedor else None,
    )


if __name__ == "__main__":
    notifier.run_stage(
        etapa="escrever o roteiro",
        inicio="✍️ Escrevendo o roteiro no seu estilo...",
        sucesso="✅ Roteiro pronto. Agora vou salvar no Notion.",
        func=main,
        dica_erro="Pode ser algo na base de conhecimento (os Gists) ou na chave da Anthropic.",
    )
