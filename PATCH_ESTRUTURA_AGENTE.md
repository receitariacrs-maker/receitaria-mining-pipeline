# Patch de estrutura — agente da API (`generate_script.py`)

Diagnóstico e correções a partir da comparação entre um roteiro que funcionou
(laranja + cebola, tosse/bronquite) e um que saiu estruturalmente errado
(vinagre + bicarbonato, pulgas).

---

## 1. A descoberta central: o agente renomeia os blocos

O `FORMATO_SAIDA` entrega ao modelo os rótulos corretos:

```
[10-25s - Começa a Receita JÁ (primeiro ingrediente)]
[25s-1min - Execução Intercalada (parte 1)]
[1min-1min50 - Execução Intercalada (parte 2)]
[1min50-2min20 - Camada Bônus]
```

O roteiro de pulgas saiu com estes:

```
[10-25s - Contexto/História]
[25-50s - Explicação do Problema]
[50s-2min - Passo a Passo Completo, com detalhe de cada ingrediente]
[2min-2min30 - Por que Funciona]
```

**O modelo inventou os próprios rótulos — e os rótulos que ele inventou são
exatamente a estrutura linear que o prompt proíbe.** Isso não é desobediência
aleatória: os rótulos do template estão escritos como *descrição em prosa dentro
de colchetes*, então o modelo lê como orientação a ser interpretada, não como
token literal a ser emitido. Quando ele interpreta, ele reverte ao default de
redação que conhece (intro → problema → solução → explicação).

Consequência prática no roteiro de pulgas: **a primeira ação prática só aparece
aos 50 segundos.** No roteiro que funcionou, a primeira ação aparece aos 12
segundos ("Começa pegando uma laranja e corta em rodelas com casca e tudo").

Corolário importante: nenhuma quantidade de advertência em prosa conserta isso.
O prompt atual já tem quatro parágrafos separados combatendo esse erro exato
(a REGRA 1 no topo da KB, o "ESTRUTURA OBRIGATÓRIA desta versão", o "Erro comum
a evitar", e o lembrete final). O erro aconteceu mesmo assim. Advertência
repetida é sintoma de regra que não pega, não solução.

---

## 2. Os quatro consertos, em ordem de impacto

### 2.1 Rótulos de bloco viram vocabulário fechado + validação em Python

Trocar a instrução em prosa por uma lista literal e checar no `_avisos_qa`.
O roteiro de pulgas teria sido pego na hora.

Adicionar ao `FORMATO_SAIDA`, logo antes de `ROTEIRO VERSAO-MAE`:

```
Os rótulos entre colchetes abaixo são LITERAIS: copie cada um exatamente como
está escrito, na ordem em que aparecem, sem renomear, sem traduzir, sem
acrescentar e sem remover nenhum. É PROIBIDO criar rótulo próprio. Em especial,
são proibidos rótulos como "Contexto", "História", "Explicação do Problema",
"Por que Funciona", "Passo a Passo Completo" — eles descrevem uma estrutura
linear que este roteiro não usa. A quantidade de blocos [Ingrediente N] deve
ser exatamente igual à quantidade de itens da lista INGREDIENTES.
```

E a validação nova em `generate_script.py`:

```python
ROTULOS_MAE = [
    "0-10s - Gancho + Micro-promessa",
    "10-25s - Primeiro Ingrediente (ação começa aqui)",
    # seguido de N blocos "[Ingrediente N - <nome>]", um por item de INGREDIENTES
    "Camada Bônus (entregue, não anunciada)",
    "Modo de Uso + Reforço da Promessa",
    "Fechamento (salvar/compartilhar, SEM comentário)",
]

RE_BLOCO = re.compile(r"^\[([^\]]+)\]\s*$", re.MULTILINE)
RE_INGREDIENTE = re.compile(r"^Ingrediente \d+\b", re.IGNORECASE)

def _avisos_estrutura(parsed: dict) -> list[str]:
    avisos = []
    rotulos = RE_BLOCO.findall(parsed["versao_mae"])
    if not rotulos:
        return ["VERSAO-MAE sem rótulos de bloco entre colchetes."]

    inventados = [
        r for r in rotulos
        if r not in ROTULOS_MAE and not RE_INGREDIENTE.match(r)
    ]
    if inventados:
        avisos.append(
            "VERSAO-MAE com rótulos fora do vocabulário fixo "
            f"(estrutura linear provável): {inventados}"
        )

    n_blocos = sum(1 for r in rotulos if RE_INGREDIENTE.match(r))
    n_itens = len(parsed.get("ingredientes") or [])
    if n_itens and n_blocos != n_itens:
        avisos.append(
            f"VERSAO-MAE tem {n_blocos} blocos de ingrediente para {n_itens} "
            "itens em INGREDIENTES - execução intercalada incompleta."
        )
    return avisos
```

### 2.2 Rótulos nomeados por CONTEÚDO, nunca por FUNÇÃO

`[Explicação do Problema]` é um rótulo funcional: ele convida a escrever um bloco
de explicação. `[Ingrediente 2 - bicarbonato de sódio]` é um rótulo de conteúdo:
não há como preenchê-lo com um bloco de dor amplificada.

Essa é a razão de fundo pela qual o roteiro bom tem a estrutura certa. Ele não é
organizado por função narrativa, é organizado por ingrediente — e a função
narrativa (dor, autoridade, história) só existe *dentro* de cada ingrediente, uma
frase por vez. A estrutura correta é uma consequência automática de nomear os
blocos pelo ingrediente.

Novo esqueleto da VERSAO-MAE no `FORMATO_SAIDA`:

```
ROTEIRO VERSAO-MAE
[0-10s - Gancho + Micro-promessa]
[2 a 4 frases. Família do gancho de referência + combinação inusitada + número
específico + a promessa mais ousada, sempre em 1ª pessoa. Fecha com uma frase
curta de ponte do tipo "vou te mostrar cada passo".]

[10-25s - Primeiro Ingrediente (ação começa aqui)]
[3 a 5 frases. O primeiro ingrediente JÁ na mão, com quantidade, e a ação
física acontecendo. Nada de contexto antes disso.]

[Ingrediente 2 - <nome do ingrediente>]
[Exatamente 4 frases, nesta ordem: (1) revela o ingrediente com a quantidade;
(2) a ação física visível — cortar, jogar, mexer, e o que se vê ou se cheira
acontecendo; (3) o micro-benefício em linguagem popular, uma frase só;
(4) a costura — UM pedaço de dor, autoridade folk ou história pessoal.
Termina com uma transição de open loop para o próximo.]

[Ingrediente 3 - <nome do ingrediente>]
[Mesma fórmula de 4 frases.]

... repita um bloco [Ingrediente N - <nome>] para CADA item restante da lista
INGREDIENTES, sem exceção ...

[Camada Bônus (entregue, não anunciada)]
[3 a 5 frases. Uma dica extra ENTREGUE na hora. Comece por "E tem mais uma
coisa que ..." e já diga qual é.]

[Modo de Uso + Reforço da Promessa]
[4 a 6 frases: frequência, duração, quando usar, validade, mais uma variação
prática para quem não conseguir fazer do jeito padrão. Fecha repetindo a
promessa do gancho em 1ª pessoa, com o número específico.]

[Fechamento (salvar/compartilhar, SEM comentário)]
[2 frases. Gatilho de compartilhamento + "Te vejo no próximo vídeo."]
```

### 2.3 `PLANO_EXECUCAO`: devolver o planejamento sem religar o thinking

`thinking={"type": "disabled"}` está certo pelo motivo errado. O comentário no
código diz *"essa tarefa é só formatação seguindo um template"* — não é. Escrever
três versões encadeadas respeitando ~15 restrições cruzadas é planejamento. Mas
religar o thinking traz de volta o risco de estourar `max_tokens` antes de
escrever o roteiro.

A saída é obter o planejamento **dentro do output**, num bloco que o parser
descarta. Custa ~150 tokens e é determinístico:

```
PLANO_EXECUCAO
Preencha antes de escrever qualquer roteiro. Uma linha por ingrediente, na ordem
em que serão revelados. Este bloco é descartado pelo parser — é rascunho.
ORDEM: [ingrediente 1] > [ingrediente 2] > [ingrediente 3] > ...
COSTURA_1: [qual pedaço da narrativa entra no ingrediente 1 - dor, quem ensinou, ou resultado pessoal]
COSTURA_2: [outro pedaço diferente, para o ingrediente 2]
COSTURA_3: [outro pedaço diferente, para o ingrediente 3]
... uma linha COSTURA_N por ingrediente, todas DIFERENTES entre si ...
BONUS: [qual é a dica extra, em até 10 palavras - precisa ser algo que ainda não foi dito]
```

Forçar as costuras a serem diferentes entre si é o que impede o empilhamento:
se cada pedaço da narrativa já tem dono, não sobra nada para juntar num bloco de
"Contexto/História" no começo.

No `roteiro_parser.py`, descartar tudo entre `PLANO_EXECUCAO` e `ROTEIRO
VERSAO-MAE`.

### 2.4 Autoverificação com evidência citada

O `_avisos_qa` atual só roda depois, e sem retry ele nunca corrige nada. Um bloco
de conferência no próprio output pega boa parte antes de virar aviso. Checklist
de sim/não não funciona (o modelo responde "sim" para tudo); **exigir a citação
literal é o que funciona**:

```
CONFERENCIA
Preencha citando trecho literal do que você escreveu. Se algum item não puder
ser preenchido com uma citação real, volte e reescreva o roteiro antes de
responder.
PRIMEIRA_ACAO: [cite a frase em que o primeiro ingrediente entra em cena, e diga em que segundo ela cai - precisa ser antes dos 25s]
BLOCO_LINEAR: [cite o rótulo de qualquer bloco que descreva contexto/problema/explicação, ou escreva "nenhum"]
COSTURAS: [liste os rótulos [Ingrediente N] e, em 3 palavras, a costura de cada um - precisam ser todas diferentes]
CTA_MAE: [cite a última frase da versão-mãe - não pode conter pedido de comentário]
CTA_SHORTS: [cite a última frase do shorts - precisa conter RECEITA em caixa alta]
```

Descartar no parser junto com o `PLANO_EXECUCAO`.

---

## 3. Divergência entre os documentos (corrigir na fonte)

A estrutura está definida em três lugares que não batem:

| Documento | Camada bônus | Modo de uso |
|---|---|---|
| `SISTEMA_VIRAL_RECEITARIA.md` §7 | 1:30–1:50 | 2:20–2:50 |
| `SISTEMA_VIRAL_PIPELINE.md` §4 | 1:50–2:20 | 2:20–2:50 |
| `FORMATO_SAIDA` | 1min50-2min20 | 2min20-2min50 |

O mestre deixa um buraco de 30 segundos entre 1:50 e 2:20 e contradiz os outros
dois. Instrução duplicada e divergente faz o modelo escolher uma arbitrariamente
— e escolher arbitrariamente é o começo de improvisar o resto.

**Ação:** corrigir `SISTEMA_VIRAL_RECEITARIA.md` §7 para `1:50–2:20 CAMADA
BÔNUS`, e passar a tratar o `FORMATO_SAIDA` como a única fonte da estrutura da
versão-mãe. A Seção 4 da KB pipeline deve remeter a ele em vez de repetir os
tempos.

---

## 4. O conserto do outro lado: regra de concretude

O padrão de erro é espelhado. O agente da API é específico e erra estrutura; o
Cowork acerta estrutura e sai genérico. A causa da genericidade é que **nenhuma
regra dos manuais exige detalhe físico** — só exigem conformidade. Sem essa
exigência, a saída converge para as formulações seguras do próprio manual.

Comparando as duas versões do mesmo ingrediente:

> ❌ "O vinagre tem um cheiro ácido forte que pulga e carrapato detestam."
> ✅ "Já sobe aquele cheiro ácido forte na hora que você despeja."

A segunda diz a mesma coisa, mas ancorada em algo que a câmera filma. É a
diferença entre descrever a propriedade e mostrar o momento.

Acrescentar ao `SISTEMA_VIRAL_RECEITARIA.md` §7 e ao `SISTEMA_VIRAL_PIPELINE.md`
§4 (vale para os dois agentes):

```
REGRA DE CONCRETUDE — toda frase de ação de ingrediente precisa carregar um
detalhe físico filmável: o corte, a espuma subindo, o vapor, a cor mudando, o
cheiro no momento em que sobe, o som da panela. Descrever a propriedade do
ingrediente não conta — "o vinagre tem cheiro forte que pulga detesta" é
propriedade; "já sobe aquele cheiro ácido na hora que você despeja" é momento.
Um detalhe por ingrediente, no mínimo. Roteiro sem detalhe filmável é roteiro
genérico, mesmo com a estrutura toda correta.
```

---

## 5. Resumo do que muda onde

| Arquivo | Mudança |
|---|---|
| `generate_script.py` → `FORMATO_SAIDA` | Rótulos literais + esqueleto por ingrediente (2.1, 2.2); blocos `PLANO_EXECUCAO` e `CONFERENCIA` (2.3, 2.4) |
| `generate_script.py` → `_avisos_qa` | Nova função `_avisos_estrutura` (2.1) |
| `roteiro_parser.py` | Descartar `PLANO_EXECUCAO` e `CONFERENCIA` |
| `SISTEMA_VIRAL_PIPELINE.md` §4 | Remover tempos duplicados, remeter ao `FORMATO_SAIDA`; incluir regra de concretude |
| `SISTEMA_VIRAL_RECEITARIA.md` §7 | Corrigir bônus para 1:50–2:20; incluir regra de concretude |

Ordem sugerida: 2.1 sozinho primeiro. Ele é barato, é validável em Python e
sozinho teria pego o roteiro de pulgas. Só depois de ver se o número de avisos
cai é que vale acrescentar 2.3 e 2.4, que custam tokens em toda chamada.
