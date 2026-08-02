# 08 — Riscos e desempenho

## 1. Medições de referência

Todas obtidas por execução real neste ambiente em 2026-08-02
(i5-10300H · 4 núcleos físicos · 7,8 GB RAM · Python 3.13.1 · SQLite 3.45.3).

| Operação | Medição | Fonte |
|---|---|---|
| Parsing TEI (stdlib `iterparse` + gzip) | **35,4 e 36,1 MB/s** por núcleo | `SOCa`, `JUDa` |
| Indexação FTS5 | **33,7 MB de texto/s** | 1.391 docs, 18,1 MB |
| Razão `.db` / texto (com conteúdo) | **1,48×** | mesmo teste |
| Consulta de frase `"de que"` | **4,4 ms** (996 ocorrências) | índice de 18 MB |
| Consulta de termo | **0,4 ms** (461 ocorrências) | idem |
| `NEAR(recurso provido, 5)` | **0,4 ms** (208 ocorrências) | idem |
| spaCy POS (`tok2vec`+`morphologizer`) | **20.422 tokens/s** | 390.488 tokens |
| spaCy completo (+`parser`+`lemmatizer`) | **14.865 tokens/s** | 158.901 tokens |
| Densidade | **5,48 caracteres/token** | amostra `uni` |

## 2. Estimativas derivadas

Base: ~13,9 GB de XML; texto puro estimado em **7–9 GB** (fração medida: 40% em `SOCa`,
66% em `JUDa`); ~**1,3–1,6 bilhão de tokens**; ~**66 milhões de sentenças** **[a validar]**.

### 2.1 Construção do índice

| Etapa | 1 núcleo | 4 processos |
|---|---:|---:|
| Varredura + checksums | 2 min | 2 min |
| Parsing de todo o XML | ~7 min | **~2–3 min** |
| Normalização + segmentação | 25–40 min | **8–12 min** |
| Escrita FTS5 + tabelas | 1,5–4 h | **35 min – 2 h** (9 escritores) |
| Finalização (merge, VACUUM, `vocab_rev`) | 20–40 min | 20–40 min |
| **Total** | | **~1,5 – 3,5 h** |

**Fase 0** (`pub`+`soc`+`uni`, 215 MB): **< 5 min**.

> A escrita FTS5 domina, e é onde a incerteza é maior. A vazão de 33,7 MB/s foi medida em
> 18 MB — em 8 GB, o crescimento dos B-trees e o I/O do disco devem degradá-la em 5–15×. Se a
> Fase 1 revelar tempo acima de 6 h, as alavancas são: `detail=column` (índice menor, `NEAR`
> menos preciso), lotes maiores, ou `page_size=16384`.

### 2.2 Latência de consulta **[estimado]**

| Cenário | Estimativa |
|---|---:|
| Termo raro, 1 shard | < 10 ms |
| Termo raro, 9 shards (fan-out) | < 50 ms |
| Frase comum (`"de que"`), 9 shards | 200 ms – 1,5 s |
| Padrão com verificação por regex, 10⁴ candidatos | 0,3 – 1 s |
| Padrão com POS, 10⁴ candidatos, cache frio | 5 – 15 s |
| Padrão com POS, cache quente | 0,3 – 1 s |
| Varredura sem âncora, corpus completo | 25 – 40 min ⚠️ |

Meta de p95 < 2 s para consultas ancoradas ([00 §5](00-visao-geral.md#5-requisitos-não-funcionais)).

### 2.3 Espaço em disco

| Estrutura | Estimativa |
|---|---:|
| `doctext` (zlib ~3×) | ~2,7 GB |
| `fts` (contentless, `detail=full`) | ~3,6 GB |
| `segments` | ~2,4 GB |
| `docs` | ~0,9 GB |
| `vocab` + `vocab_forma` + `vocab_rev` | ~0,6 GB |
| **Total** | **~10,2 GB** |
| Pico transitório durante `VACUUM` | +3,5 GB |
| `anot_cache` (cresce com o uso) | +0,1 – 1 GB |

Contra **99 GB livres [medido]** — folga de ~9×.

### 2.4 Custo de anotação

| Escopo | Tokens | 1 núcleo | 4 processos |
|---|---:|---:|---:|
| 5.000 linhas de concordância | 110 k | **5,4 s** | — |
| 50.000 linhas | 1,1 M | 54 s | — |
| `pub`+`soc`+`uni` | 39 M | 32 min | **~10 min** |
| Corpus completo (POS) | 1,46 G | ~20 h | **~5 h** |
| Corpus completo (POS + dependências) | 1,46 G | ~27 h | ~7 h |

Anotação sintática completa é tecnicamente possível (um fim de semana), mas armazenar
dependências de 1,46 bilhão de tokens custaria dezenas de GB e não é objetivo
([00 §4](00-visao-geral.md#fora-do-escopo-não-objetivos)).

---

## 3. Registro de riscos

Severidade = impacto × probabilidade. **A** = crítico, **M** = médio, **B** = baixo.

### R-01 · Índice dentro do OneDrive — **A**

**Impacto:** corrupção silenciosa do banco, `database is locked`, sincronização contínua de
GBs, estouro de cota, arquivos marcados como *online-only*.
**Por que é provável:** o repositório **está** no OneDrive; o caminho default óbvio seria ao
lado do corpus.
**Mitigação:** [ADR-08](07-decisoes-adr.md#adr-08) — índice em `%LOCALAPPDATA%`; verificação
na inicialização que **recusa** caminhos sob pastas sincronizadas (OneDrive, Dropbox, Google
Drive, iCloud), salvo `--permitir-nuvem`.
**Sinal de alerta:** `sqlite3.OperationalError: database is locked` durante a construção.

### R-02 · Segmentação incorreta compromete todo o índice — **A**

**Impacto:** fronteiras erradas quebram consultas multipalavra e distorcem `NEAR`. Corrigir
depois exige reconstruir tudo (horas).
**Onde dói mais:** `leg`+`jud` = 6,3 GB (45% do corpus), repletos de `art.`, `inc.`, `§`,
`fls.`, `Min.`, `Des.`
**Mitigação:** validação obrigatória na Fase 0 sobre 200 sentenças anotadas manualmente **por
taxonomia**, meta ≥ 95%; lista de abreviaturas jurídicas específica; `versao_segmentador` no
manifesto para invalidação automática.

### R-03 · Política de hífen perde ou infla ocorrências — **A**

**Impacto:** decisão errada torna a colocação pronominal — objeto da persona primária —
inconsultável ou sistematicamente subcontada.
**Mitigação:** [ADR-05](07-decisoes-adr.md#adr-05); medição comparativa das duas políticas em
`jud` e `soc` na Fase 0; se a expansão de consulta não bastar, segunda coluna FTS (+40% de
índice).
**Teste:** `dar-lhe-ia` (mesóclise) precisa ser recuperável como token único.

### R-04 · Estouro de memória durante a construção — **A**

**Impacto:** com 7,8 GB de RAM e documentos de 16 MB com 366 k elementos `<p>`, esquecer
`el.clear()` derruba o processo.
**Mitigação:** `clear()` obrigatório; teste de regressão que indexa o maior documento de `leg`
monitorando o pico de RSS; limite de 4 processos; `cache_size` de 256 MB por escritor;
`vocab` em memória com despejo parcial acima de um limiar.
**[a validar]:** se o pico crescer ao longo do arquivo, adotar limpeza de irmãos anteriores no
elemento-raiz.

### R-05 · Tempo de construção maior que o previsto — **M**

**Impacto:** 8 h em vez de 3 h desestimula a reconstrução e trava a iteração.
**Mitigação:** incrementalidade por `sha256` desde a Fase 1; medição real na Fase 1 com o
maior shard antes de rodar tudo; alavancas conhecidas (`detail=column`, `page_size=16384`,
lotes maiores).

### R-06 · Divergência entre tokenização do índice e da verificação — **M**

**Impacto:** falsos negativos silenciosos — o pior modo de falha.
**Mitigação:** **um único módulo** `tokenizador.py`, usado pelas duas etapas; teste de
propriedade que confere, sobre 10.000 sentenças, que todo token indexado é recuperável pela
verificação.

### R-07 · Ruído de OCR em `leg` distorce frequências — **M**

**Impacto:** cabeçalhos/rodapés repetidos inflam contagens; um n-grama de altíssima frequência
pode ser artefato.
**Mitigação:** remoção de ruído **desligada por padrão** (fidelidade > limpeza); métricas de
dispersão (DP, *range*) e alerta quando > 50% das ocorrências vêm de um documento
([06 §2](06-analise-linguistica.md#dispersão)).

### R-08 · Metadados esparsos levam a conclusões inválidas — **M**

**Impacto:** análise diacrônica sobre um shard em que 69% dos documentos não têm ano.
**Mitigação:** `cobertura_meta` no manifesto; aviso automático ao agregar por campo de baixa
cobertura ([06 §9](06-analise-linguistica.md#9-diagnósticos-e-honestidade-metodológica)).

### R-09 · Acurácia do `pt_core_news_sm` — **M**

**Impacto:** o modelo pequeno erra POS em texto jurídico arcaizante e em fala transcrita;
consultas por POS herdam o erro.
**Mitigação:** documentar explicitamente que POS é **inferido, não anotado**; permitir
`pt_core_news_lg`; registrar o modelo em `anot_cache.modelo` e nos resultados; recomendar
verificação manual por amostragem em resultados baseados em POS.

### R-10 · Disco cheio — **M**

**Impacto:** 99 GB livres, mas em 80% de uso; ~10 GB de índice + 3,5 GB de pico de `VACUUM` +
crescimento do OneDrive.
**Mitigação:** verificação de espaço antes de indexar (aborta se < 25 GB); relatório de
tamanho por shard; `--somente-shards` para construção parcial.

### R-11 · Console do Windows corrompe acentos — **B**

**Impacto:** `Vitória` exibido como `Vit?ria`; parece defeito de dado, não de terminal
(confirmado: **zero `U+FFFD` nos arquivos [medido]**).
**Mitigação:** `PYTHONIOENCODING=utf-8`; saída via `rich`; CSV em `utf-8-sig`; nota na
documentação de instalação.

### R-12 · Contentless FTS5 e limitações de manutenção — **B**

**Impacto:** tabela contentless não suporta `'rebuild'`; corromper exige reconstruir o shard.
**Mitigação:** `contentless_delete=1` (disponível na 3.45.3) permite remoção por documento;
sharding limita o dano a um shard; incrementalidade torna a reconstrução barata.

### R-13 · Corpus atualizado (v2.1+) invalida o índice — **B**

**Impacto:** nova versão do corpus torna o índice obsoleto sem sinal visível.
**Mitigação:** manifesto guarda versão e `sha256`; `csearch validar` compara com
`checksum.sha256` e avisa; a incrementalidade reindexa só o alterado.

### R-14 · Ambição de escopo — **B**

**Impacto:** o plano tem seis fases; parar na 2 já entrega valor, mas a tentação de construir
tudo antes de usar atrasa a pesquisa.
**Mitigação:** roadmap com **entregável utilizável ao fim de cada fase**
([09](09-roadmap.md)); Fases 5 e 6 explicitamente opcionais.

---

## 4. Matriz de severidade

```
        │ Baixo impacto      │ Alto impacto
────────┼────────────────────┼─────────────────────────────────
Provável│ R-11 console       │ R-01 OneDrive
        │ R-14 escopo        │ R-02 segmentação
        │                    │ R-03 hífen
        │                    │ R-04 memória
────────┼────────────────────┼─────────────────────────────────
Pouco   │ R-12 contentless   │ R-05 tempo de construção
provável│ R-13 nova versão   │ R-06 tokenização divergente
        │                    │ R-07 ruído de OCR
        │                    │ R-08 metadados esparsos
        │                    │ R-09 acurácia do modelo
        │                    │ R-10 disco
```

**R-01 a R-04 são as que a Fase 0 existe para resolver.** Nenhuma construção completa deve
começar antes que as quatro estejam fechadas.

---

## 5. Estratégia de validação

| Nível | O que verifica | Quando |
|---|---|---|
| **Unitário** | Extrator de metadados, normalizador, segmentador, parser CQL, medidas de associação | contínuo |
| **Fixture** | Pipeline completo sobre corpus de ~2 MB (extraído de `pub`/`soc`) | contínuo, segundos |
| **Propriedade** | Todo token indexado é recuperável pela verificação (10.000 sentenças) | por versão |
| **Regressão** | `"atribuídos à União por tratados internacionais"` é encontrada em `leg` | por construção |
| **Regressão** | `dar-lhe-ia` recuperável como token único | por construção |
| **Memória** | Indexar o maior documento de `leg` com pico de RSS < 3 GB | por versão |
| **Integridade** | Contagens vs. `README.md`; `sha256` vs. manifesto | pós-construção |
| **Linguística** | 200 fronteiras de sentença por taxonomia, anotadas à mão, ≥ 95% | Fase 0 e por mudança do segmentador |
| **Desempenho** | p95 de consultas ancoradas < 2 s | Fase 1 e Fase 4 |

Os dois testes de regressão em negrito no §5 são os mais valiosos do conjunto: cada um
protege uma decisão (ADR-02 e ADR-05) cuja reversão acidental produziria **resultados
silenciosamente errados** em vez de erro visível.

---

**Anterior:** [07 — Decisões de arquitetura](07-decisoes-adr.md) · **Próximo:** [09 — Roadmap](09-roadmap.md)
