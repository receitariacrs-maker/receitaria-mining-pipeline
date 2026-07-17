/**
 * Substitui o papel de "detectar mensagem nova" do telegram_poll.py. Em vez do
 * GitHub perguntar pro Telegram de tempos em tempos (cron - melhor esforço,
 * pode atrasar/pular horas sem avisar ninguém), o Telegram avisa esse Worker
 * na hora que chega mensagem (webhook) - sempre ativo, sem cron, sem atraso.
 *
 * Mesma lógica de decisão do telegram_poll.py (link TikTok/Instagram/Facebook
 * ou mídia direta), mesmo formato de client_payload pro process-video.yml -
 * nada muda do lado do Python além de não precisar mais do offset do
 * getUpdates (o webhook empurra cada mensagem uma vez só).
 *
 * Fila e lote (concluidos/total) continuam no MESMO Gist de estado
 * (mining_pipeline_state.json), pra o fallback em Python (queue_flush.py,
 * rodando de tempos em tempos como rede de segurança de baixa frequência)
 * continuar enxergando a mesma fila.
 *
 * Rotas:
 *   POST /telegram-webhook   - endpoint que o Telegram chama a cada mensagem
 *   GET  /setup-webhook?key= - roda uma vez pra registrar esse Worker como
 *                              webhook do bot (key = WEBHOOK_SETUP_SECRET)
 *   GET  /health             - checagem simples
 *
 * Secrets esperados (via `wrangler secret put` ou painel do Cloudflare):
 *   TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_ID, GH_DISPATCH_TOKEN,
 *   GITHUB_REPOSITORY (ex: "receitariacrs-maker/receitaria-mining-pipeline"),
 *   GIST_TOKEN, GIST_ID, WEBHOOK_SETUP_SECRET (qualquer string aleatória sua,
 *   só pra proteger a rota de setup).
 */

const BATCH_TRIGGER = 7;
const BATCH_MAX_WAIT_SECONDS = 15 * 60;

const URL_PATTERNS = {
  tiktok: /https?:\/\/(?:www\.|vm\.|vt\.)?tiktok\.com\/\S+/i,
  instagram: /https?:\/\/(?:www\.)?instagram\.com\/\S+/i,
  facebook: /https?:\/\/(?:www\.|m\.)?facebook\.com\/\S+|https?:\/\/fb\.watch\/\S+/i,
};

function detectPlatform(text) {
  if (!text) return null;
  for (const [platform, pattern] of Object.entries(URL_PATTERNS)) {
    const match = text.match(pattern);
    if (match) return { platform, url: match[0] };
  }
  return null;
}

async function githubRequest(env, url, options = {}) {
  const resp = await fetch(url, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      // a API do GitHub recusa qualquer requisição sem User-Agent (403
      // "Request forbidden by administrative rules") - não é opcional.
      "User-Agent": "receitaria-mining-pipeline-worker",
      ...options.headers,
    },
  });
  if (!resp.ok) {
    const body = await resp.text();
    throw new Error(`GitHub API ${resp.status} em ${url}: ${body}`);
  }
  return resp;
}

async function loadState(env) {
  const resp = await githubRequest(env, `https://api.github.com/gists/${env.GIST_ID}`, {
    headers: { Authorization: `Bearer ${env.GIST_TOKEN}` },
  });
  const data = await resp.json();
  const file = data.files["mining_pipeline_state.json"];
  if (!file || !file.content) return {};
  return JSON.parse(file.content);
}

async function saveState(env, state) {
  await githubRequest(env, `https://api.github.com/gists/${env.GIST_ID}`, {
    method: "PATCH",
    headers: {
      Authorization: `Bearer ${env.GIST_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      files: { "mining_pipeline_state.json": { content: JSON.stringify(state, null, 2) } },
    }),
  });
}

async function dispatchEvent(env, clientPayload) {
  await githubRequest(env, `https://api.github.com/repos/${env.GITHUB_REPOSITORY}/dispatches`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ event_type: "new-video", client_payload: clientPayload }),
  });
}

async function sendTelegramMessage(env, chatId, text) {
  await fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ chat_id: chatId, text }),
  });
}

/** Mesma decisão do handle_message() do telegram_poll.py. */
async function handleMessage(env, message) {
  const chatId = message.chat.id;

  for (const mediaKey of ["audio", "video", "voice"]) {
    if (message[mediaKey]) {
      return {
        source_type: "media",
        media_type: mediaKey,
        file_id: message[mediaKey].file_id,
        chat_id: chatId,
        caption: message.caption ?? null,
        sent_at: message.date ?? null,
      };
    }
  }

  const detected = detectPlatform(message.text || "");
  if (detected) {
    if (detected.platform === "facebook") {
      await sendTelegramMessage(
        env,
        chatId,
        "Link de Facebook eu não consigo baixar sozinho (bloqueio da própria plataforma). Manda o áudio ou vídeo direto aqui no chat, sem link, que eu processo."
      );
      return null;
    }
    return {
      source_type: "link",
      platform: detected.platform,
      url: detected.url,
      chat_id: chatId,
    };
  }

  await sendTelegramMessage(
    env,
    chatId,
    "Não reconheci um link (TikTok/Facebook/Instagram) nem um áudio/vídeo nessa mensagem."
  );
  return null;
}

async function handleTelegramWebhook(request, env) {
  const update = await request.json();
  console.log("update recebido:", JSON.stringify(update));

  const message = update.message;
  if (!message) {
    console.log("ignorado: update sem 'message' (ex: edited_message, callback_query, etc.)");
    return new Response("ok");
  }

  console.log("from.id recebido:", message.from?.id, "| esperado (TELEGRAM_ALLOWED_USER_ID):", env.TELEGRAM_ALLOWED_USER_ID);
  if (String(message.from?.id) !== String(env.TELEGRAM_ALLOWED_USER_ID)) {
    console.log("ignorado: from.id não bate com TELEGRAM_ALLOWED_USER_ID");
    return new Response("ok"); // ignora qualquer um que não seja você
  }

  const payload = await handleMessage(env, message);
  console.log("payload calculado:", JSON.stringify(payload));
  if (!payload) return new Response("ok");

  const state = await loadState(env);
  console.log("estado carregado do Gist:", JSON.stringify(state));
  const queue = state.pending_queue || [];
  queue.push(payload);
  let queuedSince = state.pending_queue_since;
  if (queuedSince == null) queuedSince = Date.now() / 1000;

  const esperandoHaMuito =
    queuedSince != null && Date.now() / 1000 - queuedSince >= BATCH_MAX_WAIT_SECONDS;

  if (queue.length >= BATCH_TRIGGER || esperandoHaMuito) {
    // aviso imediato de "recebi, vou processar já" pro lote que está saindo agora
    await sendTelegramMessage(
      env,
      payload.chat_id,
      `📥 Recebi! Disparando o processamento de ${queue.length} vídeo(s) agora.`
    );
    const useCache = queue.length > 1;
    const loteId = useCache ? crypto.randomUUID() : null;
    if (loteId) {
      state.lote_atual = { id: loteId, total: queue.length, concluidos: 0, chat_id: queue[0].chat_id };
    }
    for (const item of queue) {
      item.use_cache = useCache;
      if (loteId) item.lote_id = loteId;
      await dispatchEvent(env, item);
    }
    state.pending_queue = [];
    state.pending_queue_since = null;
  } else {
    // ainda não bateu o gatilho - avisa que recebeu mas vai esperar, pra não
    // parecer que sumiu no vácuo (o problema original que motivou essa mudança)
    const faltam = BATCH_TRIGGER - queue.length;
    await sendTelegramMessage(
      env,
      payload.chat_id,
      `📥 Recebi! Na fila (${queue.length}/${BATCH_TRIGGER}). Processo assim que chegar mais ${faltam} vídeo(s) ou em até 15 min.`
    );
    state.pending_queue = queue;
    state.pending_queue_since = queuedSince;
  }

  await saveState(env, state);
  console.log("estado salvo no Gist com sucesso, fila agora:", JSON.stringify(state.pending_queue));
  return new Response("ok");
}

async function handleSetupWebhook(request, env, url) {
  if (url.searchParams.get("key") !== env.WEBHOOK_SETUP_SECRET) {
    return new Response("forbidden", { status: 403 });
  }
  const webhookUrl = `${url.origin}/telegram-webhook`;
  const resp = await fetch(
    `https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/setWebhook?url=${encodeURIComponent(webhookUrl)}`
  );
  const data = await resp.json();
  return new Response(JSON.stringify(data, null, 2), {
    headers: { "Content-Type": "application/json" },
  });
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    if (url.pathname === "/telegram-webhook" && request.method === "POST") {
      try {
        return await handleTelegramWebhook(request, env);
      } catch (err) {
        console.error(err);
        // sempre 200 pro Telegram não ficar re-tentando a mesma mensagem em loop
        return new Response("erro interno, veja os logs", { status: 200 });
      }
    }

    if (url.pathname === "/setup-webhook" && request.method === "GET") {
      return handleSetupWebhook(request, env, url);
    }

    if (url.pathname === "/health") {
      return new Response("ok");
    }

    return new Response("not found", { status: 404 });
  },
};
