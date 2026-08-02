# 03 — Modelo de dados

## 1. Organização física

```
%LOCALAPPDATA%\carolina-search\index\          ← FORA do OneDrive (ADR-08)
├── manifesto.json                             ← reprodutibilidade global
├── taxonomia.json                             ← 109 categorias, hierarquia, rótulos pt/en
├── leg.db          (~3,5 GB est.)
├── wik-pt.db       (~3,2 GB est.)
├── dat-ptbr.db     (~1,5 GB est.)
├── jud.db          (~0,8 GB est.)
├── dat-pt.db       (~0,2 GB est.)
├── uni.db          (~0,1 GB est.)
├── soc.db          (~30 MB est.)
├── wik-ptbr.db     (~10 MB est.)
└── pub.db          (~1 MB est.)
```

Cada `.db` é **autossuficiente**: contém metadados, texto e índice do seu shard. Consequência
prática valiosa — `jud.db` pode ser enviado a um colega por si só, e ele terá o subcorpus
jurídico completo e consultável sem baixar 14 GB de XML.

---

## 2. Esquema por shard

### 2.1 `docs` — um registro por documento

```sql
CREATE TABLE docs (
    doc_id         INTEGER PRIMARY KEY,
    carolina_id    TEXT NOT NULL UNIQUE,   -- 'JUD000012345a'
    arquivo        TEXT NOT NULL,          -- 'judicial_branch/JUDa.xml.gz'
    ord_arquivo    INTEGER NOT NULL,       -- n-ésimo <TEI> do arquivo (proveniência exata)

    -- classificação
    taxonomia      TEXT NOT NULL,          -- 'jud'
    lang           TEXT,                   -- 'pt' | 'pt-BR'
    genero         TEXT,                   -- 'APPELLATE_DECISION_RECORDS_JUR_W'  (folha)
    genero_l2      TEXT,                   -- 'JURIDICAL_W'
    genero_l1      TEXT,                   -- 'WRITTEN_TEXT' | 'TRANSCRIBED_SPEECH' | 'MIXED'
    dominio        TEXT,                   -- textDesc/domain
    modo           TEXT,                   -- textDesc/channel/@mode  ('w' | 's')
    constituicao   TEXT,
    preparacao     TEXT,

    -- proveniência
    titulo         TEXT,
    autor          TEXT,
    url            TEXT,
    mime           TEXT,
    fonte_arquivo  TEXT,                   -- media/@source
    autoridade     TEXT,
    patrocinador   TEXT,
    serie          TEXT,
    licenca        TEXT,
    licenca_url    TEXT,

    -- datas
    data_orig      TEXT,                   -- literal do TEI: '1987', '2015-11-13 - 2015-12-07'
    ano            INTEGER,                -- normalizado, NULL se indeterminável
    data_download  TEXT,
    data_extracao  TEXT,

    -- medidas declaradas pelo TEI
    tei_tokens     INTEGER,
    originalidade  INTEGER,                -- 0–100
    tei_bytes      INTEGER,
    tei_paginas    INTEGER,

    -- medidas nossas
    n_chars        INTEGER NOT NULL,       -- do texto canônico normalizado
    n_tokens       INTEGER NOT NULL,       -- pela nossa tokenização
    n_segs         INTEGER NOT NULL,
    n_p_orig       INTEGER                 -- nº de <p> na origem (diagnóstico de fragmentação)
);

CREATE INDEX ix_docs_genero  ON docs(genero);
CREATE INDEX ix_docs_gl1     ON docs(genero_l1, genero_l2);
CREATE INDEX ix_docs_ano     ON docs(ano);
CREATE INDEX ix_docs_lang    ON docs(lang);
CREATE INDEX ix_docs_orig    ON docs(originalidade);
```

Observações de projeto:

- `genero_l1`/`genero_l2` são **desnormalizados** a partir da hierarquia. Custam ~20 bytes
  por documento e evitam uma junção recursiva em toda consulta filtrada. Para 2,1 M
  documentos, ~40 MB — barato pelo ganho.
- `n_p_orig` não serve à busca; serve ao diagnóstico. É a métrica que revelou o achado do
  `<p>`-como-linha e permite monitorá-lo continuamente.
- `tei_tokens` (declarado pelo corpus) e `n_tokens` (nosso) coexistem de propósito: a
  divergência entre os dois é um sinal de qualidade e deve ser reportada no manifesto.

### 2.2 `doctext` — texto canônico comprimido

```sql
CREATE TABLE doctext (
    doc_id   INTEGER NOT NULL,
    blk      INTEGER NOT NULL,       -- índice do bloco, 0-based
    cstart   INTEGER NOT NULL,       -- deslocamento do 1º caractere do bloco no documento
    raw_len  INTEGER NOT NULL,       -- caracteres (não bytes) descomprimidos
    z        BLOB NOT NULL,          -- zlib.compress(bloco.encode('utf-8'), 6)
    PRIMARY KEY (doc_id, blk)
) WITHOUT ROWID;
```

**Blocos de ~256 KB de caracteres.** Motivo direto do achado do documento de 16 MB: sem
blocagem, exibir uma linha de KWIC exigiria descomprimir 16 MB para ler 200 caracteres.
Com blocos, descomprime-se um bloco (~256 KB) — 64× menos trabalho — e a fatia é obtida por
`cstart` do bloco.

`WITHOUT ROWID` porque a chave é composta e o acesso é sempre por ela.

`zlib` nível 6: presente na stdlib (`zstandard` não está instalado), razão de compressão de
~3× em português. **[a validar]** na Fase 0: comparar níveis 1/6/9 em tempo × tamanho.

### 2.3 `segments` — sentenças (a unidade de busca)

```sql
CREATE TABLE segments (
    seg_id  INTEGER PRIMARY KEY,     -- == rowid da tabela fts
    doc_id  INTEGER NOT NULL,
    ord     INTEGER NOT NULL,        -- ordinal da sentença no documento
    cstart  INTEGER NOT NULL,        -- deslocamentos no texto canônico do documento
    cend    INTEGER NOT NULL,
    ntok    INTEGER NOT NULL
);
CREATE INDEX ix_seg_doc ON segments(doc_id, ord);
```

`segments` **não armazena texto** — apenas coordenadas. O texto sai de `doctext` por
deslocamento. Isso evita a terceira cópia do corpus (a primeira é o XML original, a segunda
é `doctext`).

Guardar `ord` permite recuperar **contexto além da sentença**: a sentença anterior e a
seguinte são `ord-1` e `ord+1` do mesmo `doc_id`, essenciais quando o sintaticista precisa
julgar se uma oração é principal ou encaixada.

### 2.4 `fts` — índice invertido

```sql
CREATE VIRTUAL TABLE fts USING fts5(
    txt,
    content = '',                 -- sem conteúdo: o texto vive em doctext
    contentless_delete = 1,       -- exige SQLite ≥ 3.43 — temos 3.45.3 [medido]
    tokenize = "unicode61 remove_diacritics 2 tokenchars '-'",
    detail = full                 -- necessário para frase e NEAR
);
```

Quatro decisões embutidas:

1. **`content=''` (contentless).** O texto já está em `doctext`; armazená-lo de novo dentro
   do FTS quase dobraria o índice. Perde-se `snippet()`/`highlight()` — irrelevante, pois o
   KWIC é construído a partir dos deslocamentos, com controle total da janela (algo que
   `snippet()` não oferece).
2. **`contentless_delete=1`.** Permite reindexação incremental de um documento sem recriar
   o shard. Disponível na versão instalada.
3. **`remove_diacritics 2`.** Índice tolerante a acento — `sentenca` casa com `sentença`
   **[medido]**. A sensibilidade a acento é reposta na verificação.
4. **`tokenchars '-'`.** ⚠️ Decisão de maior impacto linguístico do esquema — ver
   [ADR-05](07-decisoes-adr.md#adr-05). Sem ela, `disse-me` é indexado como `disse` + `me`,
   e a ênclise — objeto central de estudo em sintaxe do PB — torna-se **inconsultável**.

`rowid` do `fts` é igual a `segments.seg_id`, por construção. É o que permite ir do
resultado do índice às coordenadas sem junção adicional.

### 2.5 `vocab` e `vocab_rev` — vocabulário e índice de sufixos

```sql
CREATE TABLE vocab (
    term   TEXT PRIMARY KEY,       -- forma dobrada (sem acento, minúscula) = chave do FTS
    df     INTEGER NOT NULL,       -- em quantas sentenças ocorre
    cf     INTEGER NOT NULL        -- frequência total
) WITHOUT ROWID;

CREATE TABLE vocab_forma (
    term        TEXT NOT NULL,     -- forma dobrada
    forma       TEXT NOT NULL,     -- forma de superfície real ('sentença', 'Sentença')
    cf          INTEGER NOT NULL,
    PRIMARY KEY (term, forma)
) WITHOUT ROWID;

CREATE TABLE vocab_rev (
    term_rev  TEXT PRIMARY KEY,    -- term invertido: 'ehl-essid' para 'disse-lhe'
    term      TEXT NOT NULL
) WITHOUT ROWID;
```

- `vocab` responde a listas de frequência e ao cálculo de medidas de associação **sem tocar
  no índice**.
- `vocab_forma` guarda as formas de superfície reais por chave dobrada. É o que permite ao
  sistema responder *"quais grafias reais existem sob a chave `sentenca`?"* e alimenta a
  verificação sensível a acento/caixa sem varrer o corpus.
- `vocab_rev` é o **índice de sufixos** ([arquitetura §5](02-arquitetura.md#5-índice-de-sufixos--apoio-a-padrões-morfológicos)):
  como `PRIMARY KEY` em `WITHOUT ROWID` é um B-tree ordenado, `WHERE term_rev >= 'ehl-' AND
  term_rev < 'ehl.'` resolve `*-lhe` por varredura de faixa — a operação que o FTS5 não faz.

### 2.6 `anot_cache` — anotação morfossintática sob demanda

```sql
CREATE TABLE anot_cache (
    seg_id   INTEGER PRIMARY KEY,
    modelo   TEXT NOT NULL,        -- 'pt_core_news_sm-3.8.0'
    z        BLOB NOT NULL         -- zlib(JSON: [[forma, upos, lema, feats], …])
);
```

Anotar não é gratuito (**20.422 tokens/s [medido]**), mas é *idempotente*: a mesma sentença
sempre produz a mesma análise. Guardar em cache torna a segunda consulta sobre o mesmo
material instantânea — e o trabalho de tese revisita o mesmo material muitas vezes.

O campo `modelo` invalida o cache quando o modelo spaCy é atualizado, evitando misturar
anotações de versões diferentes numa mesma contagem.

### 2.7 `shard_info` — cabeçalho do shard

```sql
CREATE TABLE shard_info (
    chave  TEXT PRIMARY KEY,
    valor  TEXT
);
-- shard, versao_corpus, versao_esquema, construido_em, tokenize, versao_segmentador,
-- versao_normalizador, n_docs, n_segs, n_tokens, n_chars, n_arquivos, n_erros
```

`n_tokens` do shard é lido em toda consulta: é o denominador da normalização por milhão de
palavras.

---

## 3. Sharding

**9 shards** = 7 taxonomias, com `wikis` e `datasets_and_other_corpora` divididas por
variante (`pt` / `pt-BR`), espelhando a estrutura física do corpus.

| Motivo | Detalhe |
|---|---|
| **Paralelismo de escrita** | SQLite admite um escritor por banco. 9 bancos = 9 escritores simultâneos, o que transforma horas em dezenas de minutos |
| **Alinhamento com a pesquisa** | "só no jurídico" é um recorte real e frequente; vira `--shards jud`, sem custo de filtragem |
| **Reindexação isolada** | Corrigir o segmentador exige reconstruir só os shards afetados |
| **Tamanho gerenciável** | Nenhum arquivo passa de ~3,5 GB; cópia, backup e envio permanecem práticos |
| **Isolamento de falha** | Um shard corrompido não invalida o índice inteiro |
| **`pt` vs `pt-BR`** | Distinção linguisticamente relevante: um estudo de PB pode querer excluir `pt` europeu. Separar por shard torna isso gratuito |

**Custo:** consultas globais fazem fan-out para 9 bancos e mesclam. Como cada consulta é de
milissegundos e o fan-out é paralelo, o custo é o do shard mais lento, não a soma.

---

## 4. Dimensionamento estimado

Base: 8 GB de texto canônico (estimativa central da faixa 7–9 GB), ~1,46 bilhão de tokens,
~66 milhões de sentenças (assumindo ~120 caracteres/sentença **[a validar]**).

| Estrutura | Cálculo | Estimativa |
|---|---|---:|
| `doctext` (zlib ~3×) | 8 GB ÷ 3 | **~2,7 GB** |
| `fts` contentless, `detail=full` | ~0,45 × texto (extrapolado do 1,48× com conteúdo) | **~3,6 GB** |
| `segments` | 66 M × ~28 B (+ índice) | **~2,4 GB** |
| `docs` | 2,1 M × ~400 B | **~0,9 GB** |
| `vocab` + `vocab_forma` + `vocab_rev` | ~10⁷ formas | **~0,6 GB** |
| **Total** | | **~10,2 GB** |
| `anot_cache` | cresce com o uso | +0,1–1 GB |

Contra **99 GB livres [medido]**: cabe com folga de ~9×. Ainda assim, o comando `indexar`
deve **verificar espaço livre antes de começar** e abortar com mensagem clara se houver
menos de 25 GB — meia hora de construção interrompida por disco cheio é frustração evitável.

> `segments` sendo ~24% do total é o custo direto da decisão de indexar por sentença
> ([ADR-02](07-decisoes-adr.md#adr-02)). É um preço justo: sem ela, 37% do corpus ficaria
> inconsultável para qualquer padrão multipalavra. Se o espaço apertar, a alternativa é
> segmentos maiores (2–3 sentenças), com perda de precisão em `NEAR`.

---

## 5. Manifesto de reprodutibilidade

`manifesto.json`, escrito ao final de cada construção:

```jsonc
{
  "versao_ferramenta": "0.1.0",
  "versao_esquema": 1,
  "corpus": {
    "versao": "2.0.1",
    "nome_versao": "Bea",
    "raiz": "…/CORPUS/Carolina/corpus",
    "commit_git": "36e5972"
  },
  "construido_em": "2026-08-15T02:14:00-03:00",
  "config": {
    "tokenize": "unicode61 remove_diacritics 2 tokenchars '-'",
    "segmentador": "pt-sbd-v1",
    "normalizador": "norm-v1",
    "bloco_chars": 262144,
    "zlib_nivel": 6
  },
  "shards": {
    "jud": {
      "arquivos": 37,
      "sha256": { "judicial_branch/JUDa.xml.gz": "a1b2…", "…": "…" },
      "n_docs": 38187, "n_segs": 4102331,
      "n_tokens": 191204882, "n_chars": 1047842119,
      "erros": [], "docs_vazios": 12,
      "cobertura_meta": { "autor": 0.94, "url": 1.0, "ano": 0.31 },
      "segundos": 812.4
    }
  }
}
```

Três usos:

1. **Incrementalidade** — comparar `sha256` com `corpus/*/checksum.sha256` diz exatamente o
   que reindexar. O corpus **já fornece** esses hashes: nada precisa ser recalculado do zero.
2. **Citação** — a dissertação registra `versao_corpus`, `construido_em` e `config`;
   qualquer pessoa reconstrói o mesmo índice.
3. **Diagnóstico** — `cobertura_meta` e `docs_vazios` expõem limitações dos dados antes que
   virem conclusões erradas. Se `ano` só existe em 31% dos documentos jurídicos, nenhuma
   análise diacrônica desse shard é defensável, e o sistema precisa dizer isso.

---

## 6. *Query card* — consulta reprodutível

`enclise_jud.consulta.toml`:

```toml
[consulta]
padrao  = '[palavra="\w+-(me|te|lhe|se|nos|vos|lhes)"]'
filtro  = 'taxonomia=jud & genero_l1=WRITTEN_TEXT'
shards  = ["jud"]

[opcoes]
sensivel_acento    = true
sensivel_caixa     = false
kwic               = 8
amostra            = 200
semente            = 20260802

[proveniencia]
executado_em    = "2026-08-20T10:02:11-03:00"
versao_corpus   = "2.0.1"
manifesto_hash  = "sha256:7f3a…"
n_ocorrencias   = 14882
por_milhao      = 77.83
```

`csearch repetir enclise_jud.consulta.toml` reexecuta e **avisa se qualquer número divergir**
do registrado. É o mecanismo que permite defender um número em banca meses depois de
tê-lo obtido.

---

## 7. Configuração do SQLite

**Durante a construção** (velocidade; a perda por falha é aceitável, pois se reconstrói):

```sql
PRAGMA journal_mode = OFF;
PRAGMA synchronous  = OFF;
PRAGMA cache_size   = -262144;   -- 256 MB por processo escritor
PRAGMA temp_store   = MEMORY;
PRAGMA page_size    = 8192;      -- definido antes da 1ª escrita
```

Com 4 escritores simultâneos, 256 MB de cache cada = 1 GB, seguro nos 7,8 GB disponíveis.

**Após a construção** (compactação e estatísticas):

```sql
INSERT INTO fts(fts) VALUES('merge', -16);   -- consolida os b-trees do FTS5
PRAGMA optimize;
ANALYZE;
VACUUM;
```

**Em consulta** (somente leitura, seguro):

```sql
PRAGMA query_only  = 1;
PRAGMA journal_mode = WAL;
PRAGMA mmap_size   = 268435456;  -- 256 MB
PRAGMA cache_size  = -65536;     -- 64 MB por shard aberto
```

Com 9 shards abertos a 64 MB, o teto é ~600 MB — confortável.

---

**Anterior:** [02 — Arquitetura](02-arquitetura.md) · **Próximo:** [04 — Linguagem de consulta](04-linguagem-de-consulta.md)
