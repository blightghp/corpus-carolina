# 02 — Arquitetura

## 1. O princípio organizador: Filtrar → Verificar → Enriquecer

Todo o sistema decorre de uma observação: **nenhum motor de busca de texto sabe português
o suficiente para um sintaticista, e nenhuma ferramenta linguística é rápida o suficiente
para 14 GB.** A solução não é escolher entre os dois — é encadeá-los, aproveitando que a
saída do primeiro é minúscula comparada à sua entrada.

```
   14 GB de texto
        │
        │  ┌──────────────────────────────────────────────────────────┐
        └─▶│ 1. FILTRAR — SQLite FTS5                                 │
           │    índice invertido, sem acento, sem caixa               │
           │    otimizado para RECALL (nunca perde ocorrência)        │
           │    ~4 ms [medido]                                        │
           └──────────────────────────────────────────────────────────┘
                              │  ~10³–10⁵ sentenças candidatas
                              ▼
           ┌──────────────────────────────────────────────────────────┐
           │ 2. VERIFICAR — autômato de tokens em Python              │
           │    regex, acento, caixa, sequência, lacunas, fronteiras  │
           │    otimizado para PRECISÃO                               │
           │    ~10–500 ms                                            │
           └──────────────────────────────────────────────────────────┘
                              │  ~10¹–10⁴ ocorrências confirmadas
                              ▼
           ┌──────────────────────────────────────────────────────────┐
           │ 3. ENRIQUECER — spaCy pt_core_news_sm sob demanda        │
           │    POS, morfologia, lema — só sobre o que foi recuperado │
           │    ~5 s para 5.000 linhas [medido]                       │
           └──────────────────────────────────────────────────────────┘
                              │
                              ▼
              KWIC · frequências · colocações · exportação
```

**Por que isso responde ao requisito "mesmo não sendo anotado":** o corpus permanece cru;
a anotação existe apenas como *função* aplicada aos resultados. O custo medido de anotar
5.000 linhas de concordância é **5,4 s**, contra **~20 h** para anotar o corpus inteiro —
uma diferença de quatro ordens de grandeza para o mesmo poder de consulta na prática.

O estágio 2 é o que distingue este sistema de um `grep` rápido: ele permite consultas que
o FTS5 não expressa (sensibilidade a acento, regex sobre token, sequências com lacuna) sem
pagar o preço de varrer o corpus.

---

## 2. Camadas

```
┌───────────────────────────────────────────────────────────────────────┐
│  C5 · INTERFACES                                                      │
│      csearch (CLI typer+rich) · API Python · Web local (Fase 5)       │
├───────────────────────────────────────────────────────────────────────┤
│  C4 · ANÁLISE                                                         │
│      KWIC · frequências · colocações (MI, t, LL, log-Dice)            │
│      distribuições · keyness · amostragem · exportação                │
├───────────────────────────────────────────────────────────────────────┤
│  C3 · CONSULTA                                                        │
│      parser CQL-lite → AST → planejador → executor                    │
│      ├── pré-filtro FTS5   (recall)                                   │
│      ├── verificador       (precisão)                                 │
│      └── anotador spaCy    (sob demanda, com cache)                   │
├───────────────────────────────────────────────────────────────────────┤
│  C2 · ÍNDICE                                                          │
│      9 shards SQLite: docs · doctext · segments · fts · vocab         │
│      manifesto de reprodutibilidade                                   │
├───────────────────────────────────────────────────────────────────────┤
│  C1 · INGESTÃO                                                        │
│      leitor TEI → extrator de metadados → normalizador →              │
│      segmentador de sentenças → escritor de shard                     │
└───────────────────────────────────────────────────────────────────────┘
                                   ▲
                          corpus/*.xml.gz (somente leitura)
```

Regra de dependência: **as camadas só dependem das inferiores.** A camada de análise nunca
lê XML; a camada de consulta nunca conhece o formato TEI. Isso permite trocar o motor de
índice (C2) ou adicionar outro corpus (C1) sem tocar em C3–C5.

---

## 3. Componentes

### C1 · Ingestão

| Componente | Responsabilidade |
|---|---|
| `varredor` | Enumera `corpus/**/*.xml.gz`, casa com `checksum.sha256`, decide o que reindexar |
| `leitor_tei` | `iterparse` em *streaming*; emite `(teiHeader, [textos de <p>])` por `<TEI>`; `clear()` obrigatório |
| `extrator_meta` | XPath fixos + *fallbacks* → `dict` de ~20 campos; conta ausências |
| `normalizador` | NFC, colapso de espaços, rejunção de linhas de OCR, remoção opcional de ruído; **produz o texto canônico** |
| `segmentador` | Divide em sentenças com regras de PB; devolve deslocamentos `(início, fim)` |
| `escritor_shard` | Um processo por shard; insere em lotes; mantém `vocab` local |

### C2 · Índice

| Componente | Responsabilidade |
|---|---|
| `esquema` | DDL das 5 tabelas (ver [03](03-modelo-de-dados.md)) |
| `armazem_texto` | Texto canônico em blocos comprimidos com `zlib`; leitura por deslocamento |
| `manifesto` | JSON com versão do corpus, `sha256` por arquivo, contagens, configuração do tokenizador, tempos |
| `catalogo` | Descobre shards disponíveis; expõe totais para normalização por milhão |

### C3 · Consulta

| Componente | Responsabilidade |
|---|---|
| `parser` | CQL-lite → AST (descida recursiva, sem dependências) |
| `planejador` | Deriva pré-filtro FTS5 dos literais; estima custo; **recusa/avisa** consultas sem âncora |
| `executor` | Fan-out por shard (`ThreadPool` — SQLite libera o GIL em I/O), merge, paginação |
| `verificador` | Casa o AST contra a sequência de tokens da sentença |
| `tokenizador` | Tokenização determinística e **estável**, compartilhada entre índice e verificação |
| `anotador` | spaCy sob demanda + cache `(shard, seg_id) → tags` |

### C4 · Análise

`kwic` · `frequencias` · `colocacoes` · `distribuicao` · `keyness` · `amostragem` ·
`exportador` — detalhados em [06](06-analise-linguistica.md).

### C5 · Interfaces

`csearch` (CLI) e a API Python (`from carolina_search import Corpus`). Interface web local
opcional na Fase 5.

---

## 4. Fluxo de uma consulta

Exemplo: ênclise a verbo finito em textos jurídicos, excluindo transcrições.

```
csearch buscar '[palavra="\w+-(me|te|lhe|se|nos|vos|lhes)"]' \
        --filtro 'taxonomia=jud & genero_l1=WRITTEN_TEXT' \
        --kwic 8 --exportar enclise_jud.csv
```

```
 1. parser        → AST: Token(regex=r"\w+-(me|te|lhe|se|nos|vos|lhes)")
                    Filtro: taxonomia=jud AND genero_l1=WRITTEN_TEXT

 2. planejador    → sem literal fixo, mas o regex tem sufixos fechados
                    ⇒ pré-filtro FTS5 por sufixo:  "*-me OR *-te OR *-lhe OR …"
                       (FTS5 não faz sufixo ⇒ recorre ao índice de sufixos, §5)
                    ⇒ predicado SQL: docs.taxonomia='jud' AND docs.genero_l1='WRITTEN_TEXT'
                    ⇒ custo estimado: ~200 k candidatos → AVISO se > limiar

 3. executor      → shard jud: SELECT seg_id FROM fts WHERE fts MATCH ? 
                                 AND seg_id IN (segmentos de docs filtrados)

 4. armazem_texto → carrega blocos de doctext, fatia por (cstart, cend)

 5. verificador   → tokeniza cada sentença; aplica o regex token a token;
                    devolve (seg_id, índice do token inicial, final)

 6. anotador      → [opcional] spaCy nas sentenças confirmadas p/ marcar POS do verbo

 7. kwic          → janela de 8 tokens à esquerda/direita, com metadados

 8. exportador    → CSV com BOM (Excel-PT) + colunas de proveniência
```

---

## 5. Índice de sufixos — apoio a padrões morfológicos

O FTS5 suporta prefixo (`palav*`) mas **não** sufixo. Para o português, sufixo é
frequentemente o que importa: `-se`, `-lhe`, `-ria`, `-mente`, `-ção`, `-inho`.

**Solução:** uma tabela auxiliar `vocab_rev` com as formas do vocabulário **invertidas**,
indexada por prefixo. Buscar `*-lhe` vira buscar `ehl-*` em `vocab_rev`, resolvendo para o
conjunto de formas reais, que então alimentam o pré-filtro FTS5 como uma disjunção de
termos exatos.

Custo: o vocabulário de um shard é da ordem de 10⁶–10⁷ formas — trivial frente aos 8 GB
de texto. Ganho: consultas morfológicas ganham âncora e deixam de ser varredura completa.
Esta é a peça que torna viável a persona sintaticista sem anotar o corpus.

---

## 6. Concorrência

| Etapa | Modelo | Motivo |
|---|---|---|
| Ingestão — parsing/normalização | `ProcessPoolExecutor`, **4 processos** | CPU-bound; 4 núcleos físicos; RAM de 7,8 GB não comporta mais |
| Ingestão — escrita | **1 processo por shard**, via fila | SQLite admite um escritor por banco; 9 shards ⇒ paralelismo natural |
| Consulta — fan-out | `ThreadPoolExecutor` sobre shards | `sqlite3` libera o GIL durante I/O; *threads* bastam |
| Verificação | serial por lote, ou processos se > 10⁵ candidatos | evita sobrecusto de serialização em consultas pequenas |
| Anotação spaCy | `nlp.pipe(batch_size=…)`, 1 processo | os lotes são pequenos; paralelizar não compensa |

**Ordem de construção proposta:** shards grandes primeiro (`leg`, `wik-pt`) para que os
pequenos preencham as lacunas de I/O ao final, minimizando o tempo de parede total.

---

## 7. Estrutura de pacotes

```
carolina_search/
├── __init__.py             # API pública: Corpus, Consulta, Resultado
├── config.py               # caminhos, validação anti-OneDrive, TOML de configuração
├── cli.py                  # typer: indexar | buscar | freq | colocar | info | validar
│
├── ingestao/
│   ├── varredor.py         # enumeração + checksums + incrementalidade
│   ├── leitor_tei.py       # iterparse streaming
│   ├── extrator_meta.py    # teiHeader → dict
│   ├── normalizador.py     # NFC, espaços, rejunção de linhas, ruído
│   ├── segmentador.py      # sentenças de PB com deslocamentos
│   └── construtor.py       # orquestração e pool de processos
│
├── indice/
│   ├── esquema.py          # DDL
│   ├── shard.py            # abre/consulta/escreve um shard
│   ├── armazem_texto.py    # blocos zlib + leitura por deslocamento
│   ├── vocab.py            # frequências + vocab_rev (índice de sufixos)
│   ├── manifesto.py        # reprodutibilidade
│   └── catalogo.py         # descoberta e totais de shards
│
├── consulta/
│   ├── lexer.py
│   ├── parser.py           # CQL-lite → AST
│   ├── ast.py
│   ├── planejador.py       # AST → plano; estimativa de custo
│   ├── executor.py         # fan-out, merge, paginação
│   ├── verificador.py      # casamento sobre tokens
│   ├── tokenizador.py      # regra única, compartilhada
│   └── filtros.py          # expressões de metadados
│
├── linguistica/
│   ├── anotador.py         # spaCy sob demanda + cache
│   ├── mwe.py              # normalização de acento/caixa
│   └── recursos/           # abreviaturas de PB, listas de clíticos, stopwords
│
├── analise/
│   ├── kwic.py
│   ├── frequencias.py
│   ├── colocacoes.py       # MI, escore-t, log-verossimilhança, log-Dice
│   ├── distribuicao.py     # por taxonomia/gênero/ano, normalizado
│   ├── keyness.py
│   ├── amostragem.py       # aleatória reprodutível (semente)
│   └── exportador.py       # CSV/TSV/JSONL/query card
│
└── recursos/
    └── taxonomia.json      # as 109 categorias com rótulos pt/en e hierarquia
```

**Testes** em `tests/`, com um **corpus-fixture** de ~2 MB extraído de `pub` e `soc`
(licença permite), para que a suíte rode em segundos sem depender do corpus completo.

---

## 8. Contratos entre camadas

Estabilizar quatro tipos torna as camadas substituíveis:

```python
Documento   = { doc_id, carolina_id, taxonomia, lang, genero, genero_l1,
                titulo, autor, url, ano, licenca, n_tokens, originalidade, arquivo }

Segmento    = { shard, seg_id, doc_id, ord, cstart, cend, ntok }

Ocorrencia  = { segmento, tok_ini, tok_fim, texto_esq, texto_kw, texto_dir, doc: Documento }

Resultado   = { ocorrencias: [Ocorrencia], total, total_docs,
                por_milhao, consulta, shards, ms, avisos: [str] }
```

`Resultado.avisos` é parte do contrato, não um detalhe: é por onde o sistema comunica
"esta consulta entrou em modo varredura", "shard X está desatualizado em relação ao
corpus", "1.203 documentos foram ignorados por texto vazio".

---

## 9. Alternativas de motor consideradas

| Opção | Por que foi descartada |
|---|---|
| **Whoosh** (Python puro) | 1–2 ordens de grandeza mais lento na indexação; 8 GB tornaria a construção de dias |
| **Tantivy / PyLucene** | Excelente desempenho, mas exige *toolchain* de compilação (Rust/JVM) — barreira real para um laboratório de Letras em Windows |
| **Elasticsearch / OpenSearch** | Servidor + JVM + ≥ 4 GB de heap, em máquina com 7,8 GB; operação desproporcional para um único pesquisador |
| **DuckDB FTS** | Promissor, mas sem busca de frase e sem `NEAR` maduros — justamente o que a sintaxe exige |
| **`ripgrep` sobre texto extraído** | Rápido, porém sem metadados, sem ranking, sem contagem por subcorpus e relendo GBs a cada consulta |
| **CWB / CQP nativo** | O padrão-ouro da área, mas instalação em Windows é hostil e a indexação exige formato vertical pré-anotado — o oposto do requisito "não anotado" |

**SQLite FTS5 vence** por: já estar presente (verificado), zero instalação, um arquivo por
shard (fácil de copiar e compartilhar), suporte nativo a frase/`NEAR`/prefixo, BM25, e
desempenho medido adequado. Ver [ADR-01](07-decisoes-adr.md#adr-01).

---

**Anterior:** [01 — Análise do corpus](01-analise-do-corpus.md) · **Próximo:** [03 — Modelo de dados](03-modelo-de-dados.md)
