# 06 — Camada de análise linguística

Recuperar ocorrências é metade do trabalho. A outra metade é transformá-las em evidência
defensável. Este documento especifica os instrumentos de análise.

---

## 1. KWIC — concordância

A visualização central da linguística de corpus. Requisitos:

| Recurso | Especificação |
|---|---|
| Janela | em **tokens** (padrão 7) ou caracteres; assimétrica se desejado (`--kwic 10,3`) |
| Contexto estendido | `--contexto-sentenca` inclui as sentenças `ord-1` e `ord+1` |
| Documento inteiro | `csearch ver JUD000004821a --destacar seg_id` |
| **Ordenação** | por 1ª/2ª palavra à esquerda, à direita, por frequência da chave, ou aleatória |
| Alinhamento | chave centralizada, contextos truncados com reticências |
| Proveniência | por linha: `carolina_id`, gênero, ano, licença, URL |

**A ordenação por contexto é indispensável, não cosmética.** Ordenar 14.882 ocorrências de
ênclise pela palavra imediatamente à esquerda agrupa os ambientes sintáticos e revela
padrões que nenhuma leitura sequencial revelaria — é o método de trabalho da área desde
Sinclair.

Suporte a **múltiplas ocorrências na mesma sentença**: cada uma é uma linha independente,
com deslocamentos próprios. Contá-las como uma só subestimaria sistematicamente as
frequências.

---

## 2. Frequências e normalização

```bash
csearch freq '[palavra="\w+-se"]' --por genero_l1 --por-milhao
```

```
gênero                 ocorrências     tokens do subcorpus     por milhão
─────────────────────────────────────────────────────────────────────────
WRITTEN_TEXT               412.883           1.284.221.043          321,5
TRANSCRIBED_SPEECH           8.104              41.882.190          193,5
MIXED                       97.220             133.998.712          725,5
```

**A normalização por milhão de palavras é obrigatória neste corpus**, não opcional: `pub`
tem 1,5 MB e `leg` tem 1.115 MB — **743× de diferença** ([01 §1](01-analise-do-corpus.md#1-inventário-físico)).
Comparar contagens brutas entre subcorpora produziria conclusões invertidas.

O denominador vem de `shard_info.n_tokens` (para shards inteiros) ou de `SUM(docs.n_tokens)`
sobre o filtro aplicado — sempre calculado sobre **o mesmo recorte** da consulta, nunca
sobre o corpus todo.

### Eixos de agregação

`--por` aceita: `taxonomia`, `shard`, `lang`, `genero`, `genero_l1`, `genero_l2`, `ano`,
`decada`, `dominio`, `modo`, `doc`, `autor`.

### Dispersão

Frequência bruta engana quando as ocorrências se concentram em poucos documentos. Junto com
a contagem, o sistema reporta:

- **DP** (*deviation of proportions*, Gries 2008) — 0 = uniforme, 1 = concentrado;
- **intervalo (*range*)** — em quantos documentos a forma ocorre;
- **alerta automático** quando > 50% das ocorrências vêm de um único documento.

Sem isso, uma expressão que aparece 3.000 vezes numa única ata de OCR defeituosa passaria
por fenômeno geral do PB. Esse risco é concreto neste corpus, dada a natureza de `leg`.

---

## 3. Colocações

```bash
csearch colocar '[lema="dizer"]' --janela 5 --medida ll --min-freq 5 --top 30
```

Medidas de associação implementadas (todas padrão na área):

| Medida | Fórmula (resumo) | Comportamento |
|---|---|---|
| **Informação mútua (MI)** | `log₂( O / E )` | favorece pares raros e distintivos |
| **MI³** | `log₂( O³ / E )` | corrige o viés de MI para *hapax* |
| **Escore-t** | `(O − E) / √O` | favorece pares frequentes |
| **Log-verossimilhança (LL)** | `2 Σ O·ln(O/E)` | robusta em baixa frequência — **padrão** |
| **log-Dice** | `14 + log₂( 2·f(xy) / (f(x)+f(y)) )` | independente do tamanho do corpus; comparável entre subcorpora |

**LL como padrão** por ser a mais robusta com frequências baixas — situação comum quando se
restringe a um gênero específico. **log-Dice** é a recomendada quando se comparam subcorpora
de tamanhos muito distintos, exatamente o caso aqui.

Opções: janela assimétrica (`--janela 5,0` para colocados apenas à esquerda), filtro por
classe (`--colocado-pos NOUN`), exclusão de palavras funcionais (`--sem-stopwords`).

As contagens marginais `f(x)` e `f(y)` vêm de `vocab` — **sem varrer o corpus**
([03 §2.5](03-modelo-de-dados.md#25-vocab-e-vocab_rev--vocabulário-e-índice-de-sufixos)).
É por isso que a tabela `vocab` foi projetada desde o início e não deixada para depois.

---

## 4. N-gramas

```bash
csearch ngramas 3 --shards soc --top 100 --min-freq 10
csearch ngramas 4 --contendo 'que' --por genero_l1
```

Extração de n-gramas (2–6) sobre um subcorpus ou sobre o conjunto de ocorrências de uma
consulta. Útil para fraseologia (P2) e para detectar o ruído recorrente de OCR em `leg` — um
n-grama de altíssima frequência restrito a um documento é a assinatura de um cabeçalho
repetido.

---

## 5. *Keyness* — palavras-chave

```bash
csearch keyness --alvo jud --referencia wik --medida ll --top 50
```

Compara as frequências relativas de um subcorpus-alvo com um de referência, listando o que é
significativamente mais frequente no alvo. Medidas: LL (padrão), *ratio* de frequências
relativas, e *Log Ratio* (Hardie 2014).

Aplicação direta à sintaxe: comparar a distribuição de formas verbais entre
`genero_l1=TRANSCRIBED_SPEECH` e `WRITTEN_TEXT` quantifica o contraste fala/escrita em
1,4 bilhão de tokens de PB contemporâneo — algo que o corpus permite e que hoje ninguém faz
por falta de ferramenta.

---

## 6. Anotação sob demanda

Núcleo da resposta ao requisito *"mesmo não sendo anotado"*.

```
consulta menciona pos/lema/morf ?
        │ não → segue sem anotar (custo zero)
        │ sim
        ▼
 para cada sentença candidata:
     está em anot_cache com o mesmo modelo ?
        │ sim → usa o cache
        │ não → nlp.pipe(lote) → grava no cache
        ▼
 casa o padrão contra os tokens anotados
```

**Custos medidos** ([01 §6.3](01-analise-do-corpus.md#63-anotação-com-spacy-pt_core_news_sm)):

| Escopo | Tokens | Tempo |
|---|---:|---:|
| 5.000 linhas de concordância | ~110 k | **5,4 s** |
| 50.000 linhas | ~1,1 M | ~54 s |
| `pub`+`soc`+`uni` completos (4 processos) | 39 M | **~10 min** |
| Corpus completo (4 processos) | 1,46 G | **~5 h** |
| Corpus completo, 1 núcleo | 1,46 G | ~20 h |

A partir da segunda consulta sobre o mesmo material, o cache torna o custo praticamente nulo
— e o trabalho de tese revisita o mesmo material dezenas de vezes.

### Alinhamento de tokenização ⚠️

A tokenização do spaCy **difere** da usada no índice (notadamente em hífens e contrações:
`disse-me`, `d'água`, `pelo`). Sem alinhamento explícito, `[palavra="disse-me" & pos="VERB"]`
falharia de modo intermitente e difícil de diagnosticar.

**Solução:** alinhamento por deslocamento de caractere. Cada token nosso guarda `(início, fim)`
na sentença; cada token do spaCy também (`token.idx`). O casamento é por sobreposição de
intervalos, com a regra: um token nosso recebe as etiquetas do token spaCy de maior
sobreposição. Quando um token nosso corresponde a vários do spaCy (`disse-me` → `disse` +
`-me`), guardam-se **todas** as etiquetas, e `[pos="VERB"]` casa se **alguma** delas for
`VERB`.

Essa é a decisão semanticamente correta para o PB: `disse-me` **é** um verbo com clítico, e a
consulta do sintaticista deve encontrá-lo.

### Pré-anotação opcional

`csearch anotar --shards pub,soc,uni` popula `anot_cache` integralmente (~10 min), tornando
viáveis consultas puramente morfossintáticas (`[pos="VERB"] [pos="PRON"]`) nesses shards, sem
âncora lexical. Recomendado: são justamente os shards em que a varredura completa é barata.

---

## 7. Amostragem reprodutível

```bash
csearch buscar '…' --amostra 200 --semente 20260802 --exportar amostra.csv
```

Fluxo padrão de tese: recuperar milhares de ocorrências, extrair uma amostra aleatória para
anotação manual, e generalizar com intervalo de confiança.

Requisitos:

1. **Determinismo** — mesma semente, mesma amostra, sempre. Implementado com
   `random.Random(semente)` sobre a lista de `seg_id` **ordenada**, nunca sobre a ordem de
   chegada do índice (que pode variar).
2. **Amostragem estratificada** (`--estratificar genero_l1`) — proporcional por categoria,
   evitando que um subcorpus dominante monopolize a amostra.
3. **Registro** — a amostra é gravada no *query card*, com semente e total da população, para
   que a banca possa reconstituí-la.
4. **Planilha de anotação** — exportação com colunas vazias (`julgamento`, `observacao`)
   prontas para preenchimento manual, e reimportação para cruzar as etiquetas com os
   metadados.

O item 4 fecha o ciclo entre busca automática e análise qualitativa — que é onde o trabalho
de linguística de fato acontece.

---

## 8. Exportação

| Formato | Uso | Detalhe |
|---|---|---|
| **CSV** | Excel / LibreOffice | `utf-8-sig` (BOM) — sem isso o Excel em português exibe acentos quebrados |
| **TSV** | R, `read.delim` | separador de tabulação; campos escapados |
| **JSONL** | processamento em Python | um objeto por ocorrência, com metadados aninhados |
| **DataFrame** | via API | `pandas` 3.0.5, já instalado |
| **Texto KWIC** | apêndice de dissertação | largura fixa, alinhado |
| ***Query card*** | reprodutibilidade | TOML ([03 §6](03-modelo-de-dados.md#6-query-card--consulta-reprodutível)) |

Colunas padrão da exportação:

```
n · carolina_id · shard · taxonomia · genero · genero_l1 · lang · ano ·
esquerdo · chave · direito · sentenca_completa · seg_ord ·
autor · titulo · url · licenca · arquivo_fonte
```

Cada linha é autossuficiente para citação. Um revisor que receba o CSV consegue localizar a
ocorrência no corpus original sem acesso ao índice.

---

## 9. Diagnósticos e honestidade metodológica

O sistema emite avisos automáticos quando os dados não sustentam a análise pretendida:

| Situação | Aviso |
|---|---|
| > 50% das ocorrências em 1 documento | `⚠ Baixa dispersão (DP=0,94). Resultado pode refletir um único texto.` |
| Subcorpus < 100.000 tokens | `⚠ Subcorpus pequeno; frequências por milhão são instáveis.` |
| Agregação por `ano` com cobertura baixa | `⚠ Apenas 31% dos documentos deste recorte têm ano. A série temporal é parcial.` |
| Consulta com `pos` sem anotação prévia em shard grande | `⚠ Serão anotadas 84.000 sentenças (~90 s).` |
| Shard desatualizado em relação ao corpus | `⚠ leg foi indexado antes da última alteração dos arquivos-fonte.` |
| Índice construído com falhas de parsing | `⚠ 1.203 documentos falharam na indexação de wik-pt (0,1%).` |

Estes avisos são o que separa uma ferramenta de pesquisa de um gerador de números. Um sistema
que devolve `14.882` sem contexto convida à conclusão errada; um que devolve `14.882` com
`DP=0,94` protege quem o usa.

---

## 10. Fluxo completo de um estudo

Exemplo integrando os componentes — colocação pronominal por modalidade:

```bash
# 1 · panorama
csearch freq '[palavra="\w+-(me|te|lhe|se|nos|vos|lhes)"]' \
        --por genero_l1 --por-milhao

# 2 · recorte e concordância
csearch buscar '[palavra="\w+-(me|te|lhe|se)"]' \
        --filtro 'genero_l1=TRANSCRIBED_SPEECH' \
        --kwic 8 --ordenar esq \
        --salvar enclise_fala.consulta.toml

# 3 · ambientes à esquerda
csearch colocar '[palavra="\w+-se"]' --janela 3,0 --medida ll --top 30

# 4 · amostra para anotação manual
csearch buscar '[palavra="\w+-(me|te|lhe|se)"]' \
        --filtro 'genero_l1=TRANSCRIBED_SPEECH' \
        --amostra 200 --semente 20260802 \
        --exportar amostra_fala.csv

# 5 · contraste
csearch distribuicao '[palavra="\w+-se"]' --por genero_l2 --por-milhao \
        --exportar dist.csv

# 6 · meses depois, na defesa
csearch repetir enclise_fala.consulta.toml     # confere se os números batem
```

---

**Anterior:** [05 — Pipeline de indexação](05-pipeline-de-indexacao.md) · **Próximo:** [07 — Decisões de arquitetura](07-decisoes-adr.md)
