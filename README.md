# Pipeline de mineração — Telegram → Transcrição → Roteiro → Notion

Você manda um link (TikTok ou Instagram) ou um áudio/vídeo direto num bot do
Telegram. O resto acontece sozinho: baixa a mídia, transcreve, gera um roteiro
no estilo da Receitaria Curiosa (usando sua base de conhecimento) e cria o card
no "Banco de Roteiros" do Notion. **Facebook não aceita link** (testado e
confirmado — ver seção do Apify abaixo) — pra Facebook, manda o áudio/vídeo
direto no chat, sem link.

## O que o bot te avisa no Telegram

O bot manda uma mensagem a cada etapa, não só no início e no fim:

1. 📥 Recebi! Vou processar...
2. ⬇️ Baixando o vídeo/áudio... → ✅ Download concluído
3. 🎧 Transcrevendo o áudio... → ✅ Transcrição pronta
4. ✍️ Escrevendo o roteiro... → ✅ Roteiro pronto
5. 📋 Salvando o roteiro no Notion... → 🎉 Roteiro pronto! Card criado: [link]

Se alguma etapa falhar, o bot avisa **na hora**, dizendo qual etapa foi e o motivo
em palavras simples (não só "deu erro") — junto com uma dica do que fazer.

## Antes de ligar: passo a passo de setup (uma vez só)

### 1. Bot do Telegram
1. Fale com **@BotFather** no Telegram → `/newbot` → siga as instruções.
2. Guarde o token que ele te dá → isso vira o secret `TELEGRAM_BOT_TOKEN`.
3. Descubra seu próprio `chat_id`: mande qualquer mensagem pro bot recém-criado,
   depois abra `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates` no navegador
   e procure `"id"` dentro de `"from"`. Esse número é o `TELEGRAM_ALLOWED_USER_ID`
   (garante que só você consegue usar o bot).

### 2. Gist privado (guarda o "offset" do Telegram)
1. Vá em https://gist.github.com → crie um Gist **privado** (secret) com um
   arquivo chamado `mining_pipeline_state.json` e conteúdo `{}`.
2. Pegue o ID do Gist (fica na URL, depois do seu usuário).
3. Gere um **Personal Access Token clássico** (Settings → Developer settings →
   Personal access tokens → **Tokens (classic)** — não use "Fine-grained", eles
   **não suportam Gist**) com o escopo `gist` marcado → isso vira `GIST_TOKEN`,
   e o ID do Gist vira `GIST_ID`.

### 3. Gist privado da base de conhecimento
1. Crie **outro** Gist privado com dois arquivos: `SISTEMA_VIRAL_RECEITARIA.md`
   e `BANCO_VIRAIS_RECEITARIA.md` (cole o conteúdo desses dois documentos).
2. Pegue o ID → `KB_GIST_ID`. Pode reaproveitar o mesmo token clássico do passo
   2 (mesmo escopo `gist` já serve) — cole o mesmo valor como o secret
   `KB_GIST_TOKEN` (tem que existir esse secret separado, mesmo com valor igual).

### 4. Token pra disparar o pipeline (`GH_DISPATCH_TOKEN`)
Um token normal do `GITHUB_TOKEN` (automático) **não funciona** pra isso — o
GitHub bloqueia um workflow de disparar outro usando o token automático, pra
evitar loop infinito. Por isso: Settings → Developer settings → Fine-grained
tokens → crie um token com permissão de "Contents: Read and write" e
"Actions: Read and write" nesse repositório → isso vira `GH_DISPATCH_TOKEN`.

### 5. Apify (só Instagram)
1. Crie uma conta grátis em https://apify.com (plano Free, $5/mês de crédito,
   não precisa cartão).
2. Use o actor **`apify/instagram-reel-scraper`** — testado nesta sessão e
   confirmado que resolve um link de reel específico corretamente (campo de
   input `username`). **Não precisa ligar o addon pago "Include downloaded
   video"** (custa bem mais caro, ~$0,24/vídeo) — a resposta básica já traz de
   graça o campo `audioUrl` (áudio puro, tudo que a transcrição precisa),
   além de `videoUrl` como reserva. O código já vem configurado pra esse actor
   por padrão, não precisa mudar nada se usar ele.
3. Gere um token de API em Settings → Integrations → API → isso vira
   `APIFY_API_TOKEN`.
4. **Facebook foi testado e descartado:** o actor oficial `apify/facebook-
   reels-scraper` só aceita URL de página/perfil (procura uma "seção Reels"),
   e rejeita link de reel específico com erro "not available without FB
   login". É uma limitação da própria Meta, não do actor — por isso o Facebook
   não tem caminho automático por link neste pipeline; use o envio manual de
   áudio/vídeo direto no Telegram para esse caso.

### 6. Groq (transcrição)
Se você já tem a chave Groq usada no PolyglotMedia, reaproveita ela. Senão,
gere uma em https://console.groq.com → isso vira `GROQ_API_KEY`.

### 7. Anthropic (geração do roteiro)
Gere uma chave em https://console.anthropic.com → isso vira `ANTHROPIC_API_KEY`.

### 8. Notion
1. Crie uma integração interna em https://www.notion.so/my-integrations →
   copie o "Internal Integration Secret" → isso vira `NOTION_TOKEN`.
2. Abra a página da database "Banco de Roteiros" no Notion → menu "..." →
   "Conexões" → adicione essa integração pelo nome. **Não esqueça esse passo**
   — é a causa mais comum de erro depois. Faça o mesmo na database "Banco de
   Vencedores Próprios" (é usada pra detectar reciclagem, ver abaixo).
3. Pegue o ID da database "Banco de Roteiros" pela URL (string de 32 caracteres
   antes do `?`) → `NOTION_DATABASE_ID`. Pegue também o ID da database "Banco de
   Vencedores Próprios" → `VENCEDORES_DATABASE_ID`.
4. **Garanta que "Banco de Roteiros" tenha estas propriedades** (nomes exatos,
   acentuação inclusa — ajuste as constantes no topo de `scripts/notion_insert.py`
   se preferir nomes diferentes):
   - `Nome` (title)
   - `Número` (number)
   - `Categoria` (select) — opções: Cabelo & Fios, Unhas & Micose, Dores
     Articulares, Respiração & Tosse, Fígado & Digestão, Saúde & Colesterol,
     Casa & Pragas, Saúde Natural
   - `Pilar estratégico` (select) — opções: Limpeza doméstica, Remédio caseiro,
     Reciclagem, Experimental
   - `Link de origem` (url)
   - `Vencedor relacionado` (relation → aponta pra database "Banco de
     Vencedores Próprios")
   - `Status` (status), com a opção `Para Gravar` existindo (é o valor inicial
     de todo card criado pelo pipeline)
5. **Na database "Banco de Vencedores Próprios"**, confirme que a propriedade
   de link do vídeo se chama `Link` (tipo url) — é nela que `generate_script.py`
   procura pra saber se o vídeo mandado já é um vencedor conhecido (e forçar
   Pilar = Reciclagem). Se o nome for diferente, ajuste `VENCEDORES_LINK_PROP`
   no topo de `scripts/generate_script.py`.

### 9. Configurar os secrets no GitHub
No repositório: Settings → Secrets and variables → Actions → aba "Secrets":

```
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_ID
GIST_TOKEN
GIST_ID
KB_GIST_ID
KB_GIST_TOKEN
GH_DISPATCH_TOKEN
APIFY_API_TOKEN
GROQ_API_KEY
ANTHROPIC_API_KEY
NOTION_TOKEN
NOTION_DATABASE_ID
VENCEDORES_DATABASE_ID
```

E na aba "Variables" (não são segredos, só configuração):
```
APIFY_ACTOR_INSTAGRAM    (opcional — só se quiser usar um actor diferente do padrão apify~instagram-reel-scraper)
ARCHIVE_STATUS_VALUE     (opcional — nome exato da coluna/status "Postado" no seu Kanban; se não setar, usa "Postado")
```

## Arquivamento automático dos cards "Postado"

`archive-posted.yml` roda 1x por dia e arquiva (manda pro lixo do Notion — some
do Kanban, mas fica recuperável, não é uma exclusão permanente e sem volta)
qualquer card cujo Status já esteja como "Postado". Se o nome exato da opção de
status no seu Kanban for diferente, ajuste a variável `ARCHIVE_STATUS_VALUE`.

## Testando antes de ligar de vez

1. Rode `telegram-poll.yml` manualmente (aba Actions → "Run workflow") depois de
   mandar um link de TikTok pro bot — confirme que dispara o `process-video.yml`.
2. Rode `process-video.yml` de novo com o mesmo link — confirme que ele detecta
   que já existe (não duplica o card no Notion).
3. Teste mandando um link de Instagram (deve baixar via Apify sozinho) e depois
   um link de Facebook (deve responder na hora pedindo áudio/vídeo direto, sem
   nem disparar o pipeline pesado) e um áudio direto no chat — confirme os três
   comportamentos.
4. Só depois disso, deixe o cron do `telegram-poll.yml` rodando sozinho.

## Formato do card gerado no Banco de Roteiros

Cada card criado pelo pipeline segue o mesmo layout que você já usava (vindo
do template Antigravity/Gemini), com duas adições: uma linha discreta com o
link do vídeo de referência logo no topo (só aparece se você mandou um link,
não aparece se mandou áudio direto), e a propriedade `Pilar estratégico`
correlacionando cada roteiro com o mix 40/35/15/10:

1. Link do vídeo de referência (linha discreta, cinza)
2. Callout amarelo — Títulos A/B
3. Linha de hashtags (discreta, cinza)
4. Callout verde — Modo de Preparo (ingredientes como checklist + instruções)
5. Versão-Mãe (Completa), Versão Rápida (1:01), Versão Reels/Shorts (30s) —
   cada uma como seção com cabeçalho H2

## Antigravity/Gemini — retirado

O importador antigo (Antigravity/Gemini) não deve mais ser usado — esse
pipeline substitui ele por completo, escrevendo direto no mesmo formato de
card que você já usava. Só uma "linha de montagem" escrevendo no Banco de
Roteiros agora, evitando formatos divergentes no mesmo Kanban.

## O que NÃO está automatizado (por decisão, não por limitação)

- A mineração em si — você continua decidindo quais vídeos valem a pena.
- A reorganização visual da página "gerenciador de conteúdos minerados" no
  Notion — é uma tarefa separada, pode ser feita depois com a mesma integração
  criada no passo 8.
- O calendário fixo de garimpo mensal (31 dias) continua manual, sem ligação
  automática com o Banco de Roteiros — foi uma escolha deliberada de manter
  simples por enquanto.
