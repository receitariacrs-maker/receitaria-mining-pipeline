# Sessão de Continuação — Pipeline de Mineração

**Gerado:** 2026-07-16
**Projeto:** receitaria-mining-pipeline (não usa scaffolding GSD — sem STATE.md/ROADMAP.md; relatório adaptado a partir do git log e da conversa)
**Contexto:** Continuação do setup do pipeline Telegram → transcrição → roteiro → Notion, iniciado em sessão anterior no mesmo dia.

---

## Resumo da Sessão

**Duração:** sessão única, contínua
**Commits feitos:** 3 (`f348ccf`, `0de52ac`, `e796ceb`)
**Arquivos alterados:** 4 (`scripts/download_video.py`, `scripts/generate_script.py`, `scripts/notion_insert.py`, `scripts/transcribe.py`, `.github/workflows/process-video.yml`)
**Resultado:** primeiro card de roteiro real criado com sucesso no Notion, de ponta a ponta.

## Trabalho Realizado

### Setup do Notion
- Confirmada integração "Receitaria Miner" conectada nas duas databases (Banco de Roteiros + Banco de Vencedores Próprios).
- Criadas 3 propriedades que faltavam no "Banco de Roteiros": `Pilar estratégico` (select, 4 opções: Limpeza doméstica/Remédio caseiro/Reciclagem/Experimental), `Link de origem` (url), `Vencedor relacionado` (relation → Banco de Vencedores Próprios).
- Corrigido o Gist da base de conhecimento (`mining_knowledge_gist_1`): estava com nome de arquivo errado e faltando o segundo arquivo (`BANCO_VIRAIS_RECEITARIA.md`).

### Verificação de configuração
- Confirmados os 13 secrets necessários no GitHub (nomes conferidos via login temporário, sem expor valores).
- Detectado e explicado um incidente paralelo de instabilidade da API REST do GitHub (não relacionado à configuração do usuário).

### Bugs encontrados e corrigidos (via teste real de ponta a ponta)
1. **Download do TikTok falhava** — `yt-dlp -f bestaudio` não existe para TikTok (só vídeo+áudio combinado). Corrigido para `bestaudio/best` (commit `f348ccf`).
2. **ffmpeg ausente no runner** — suposição desatualizada de que `ubuntu-latest` vem com ffmpeg pré-instalado. Adicionado passo de instalação via apt no workflow (commit `0de52ac`).
3. **Cards vazios no Notion** — conflito de instruções no prompt: a base de conhecimento tem sua própria seção "Formato de Entrega" (pensada pro uso manual), que competia com o formato de tags esperado pelo parser. Claude seguia o formato errado. Corrigido reforçando no prompt qual formato usar; também adicionada validação que falha alto (em vez de criar card vazio silenciosamente) se o parsing não reconhecer nada (commit `e796ceb`).

### Resultado final
- Rodada de teste após as 3 correções: pipeline completo rodou com sucesso (2m14s) — baixou vídeo do TikTok, transcreveu, gerou roteiro e criou o card no Notion com conteúdo completo (título, categoria, títulos A/B, hashtags, receita, e as 3 versões do roteiro).

## Decisões Tomadas

- Log de debug adicionado em `generate_script.py` (primeiros 500 chars da resposta bruta da Claude) para facilitar diagnóstico se o parsing falhar de novo no futuro.
- Estimativa de custo por roteiro discutida: ~$0,10-0,11 (preço promocional atual do Sonnet 5) por geração, dominado pelo reenvio integral da base de conhecimento (~45k tokens) a cada chamada — sem prompt caching. Oportunidade de otimização identificada, não implementada (aguardando decisão sobre volume de uso).

## Arquivos Alterados

```
.github/workflows/process-video.yml |  4 +++-
scripts/download_video.py           |  7 ++++++-
scripts/generate_script.py          | 11 +++++++++++
scripts/notion_insert.py            |  7 +++++++
scripts/transcribe.py               |  7 +++++---
```

## Bloqueios & Itens em Aberto

- Nenhum bloqueio ativo. Pipeline está funcional de ponta a ponta.
- Pendente (não bloqueante): decidir se vale a pena implementar prompt caching pra reduzir custo por roteiro, dependendo do volume de uso real.
- Pendente: deixar o cron do `telegram-poll.yml` rodando sozinho (próximo passo natural, conforme README) — ainda não confirmado com o usuário.

## Uso Estimado de Recursos

| Métrica | Estimativa |
|---|---|
| Commits | 3 |
| Arquivos alterados | 5 |
| Rodadas de teste (Actions) | ~7 (4 falhas diagnosticadas + 1 sucesso, mais reruns do telegram-poll) |
| Chamadas à API da Claude (geração de roteiro) | 2 (1 falha por conflito de formato, 1 sucesso) |

> **Nota:** estimativas de tokens/custo exigem instrumentação a nível de API, não disponível neste ambiente. As métricas acima refletem apenas atividade observável da sessão (git log + GitHub Actions).

---

*Gerado via `/gsd-pause-work --report` (adaptado — projeto sem scaffolding GSD)*
