# Worker do Telegram (substitui o polling)

Recebe mensagem do Telegram por webhook (instantâneo) em vez do GitHub ficar
perguntando de tempos em tempos (cron, que ficou horas sem disparar). Ver
comentário no topo de `worker.js` pra entender a lógica completa.

## Deploy (painel do Cloudflare, sem precisar instalar nada)

1. workers.cloudflare.com → **Create Worker** → dê um nome (ex:
   `receitaria-telegram-webhook`) → **Deploy** (cria com o código padrão de
   exemplo, tudo bem, vamos substituir).
2. **Edit code** → apague tudo → cole o conteúdo de `worker.js` → **Save and deploy**.
3. Volta pra página do Worker → **Settings → Variables and Secrets** → **Add**
   pra cada um destes, tipo **Secret** (não "Text"):

   | Nome | De onde vem |
   |---|---|
   | `TELEGRAM_BOT_TOKEN` | o mesmo token do bot que já está no secret do GitHub (BotFather, ou onde você guardou quando criou) |
   | `TELEGRAM_ALLOWED_USER_ID` | o mesmo ID que já está no secret do GitHub |
   | `GH_DISPATCH_TOKEN` | o mesmo token que já está no secret do GitHub (ou gere um novo Personal Access Token com escopo `repo` só pra isso) |
   | `GITHUB_REPOSITORY` | `receitariacrs-maker/receitaria-mining-pipeline` |
   | `GIST_TOKEN` | o mesmo token que já está no secret do GitHub |
   | `GIST_ID` | o mesmo ID que já está no secret do GitHub |
   | `WEBHOOK_SETUP_SECRET` | invente uma senha aleatória qualquer, só sua (não precisa anotar em lugar nenhum crítico - só protege a rota de setup) |

   Eu não tenho acesso a nenhum desses valores (o GitHub não deixa reler
   secret já salvo) - só você pode colar eles aqui.

4. Depois de salvar todos, visite no navegador:
   `https://<nome-do-worker>.<seu-subdominio>.workers.dev/setup-webhook?key=SEU_WEBHOOK_SETUP_SECRET`
   Isso registra o Worker como webhook do bot. Deve devolver um JSON com
   `"ok": true`.

5. Pronto - a partir daí, mandar uma mensagem no Telegram já cai direto no
   Worker, sem esperar nenhum agendamento.

## Testando

Manda uma mensagem de teste (um link) no bot depois do passo 4 e veja se
chega a resposta "📥 Recebi! Na fila (1/7)..." — se chegar, o webhook está
funcionando.
