# 01 — Análise do corpus

Levantamento empírico realizado em **2026-08-02** diretamente sobre os arquivos deste
repositório. Todos os números marcados **[medido]** foram obtidos por execução real.

---

## 1. Inventário físico

**[medido]** 554 arquivos `.xml.gz`, 2.962,4 MB comprimidos.

| Shard proposto | Código | Arquivos | Comprimido (MB) | Descomprimido est. (GB) |
|---|---|---:|---:|---:|
| `legislative_branch` | `leg` | 161 | 1.115,0 | ~5,2 |
| `wikis/pt` | `wik-pt` | 192 | 1.036,8 | ~4,9 |
| `datasets_and_other_corpora/pt-BR` | `dat-ptbr` | 90 | 474,2 | ~2,2 |
| `judicial_branch` | `jud` | 37 | 237,1 | ~1,1 |
| `datasets_and_other_corpora/pt` | `dat-pt` | 63 | 56,1 | ~0,26 |
| `university_domains` | `uni` | 7 | 31,2 | ~0,15 |
| `social_media` | `soc` | 2 | 9,0 | ~0,04 |
| `wikis/pt-BR` | `wik-ptbr` | 1 | 1,6 | ~0,01 |
| `public_domain_works` | `pub` | 1 | 1,5 | ~0,01 |
| **Total** | | **554** | **2.962,4** | **~13,9** |

> Estimativa de descompressão usa razão **4,8×**, medida em dois arquivos:
> `SOCa.xml.gz` 4,6 MB → 26,1 MB (5,6×) e `JUDa.xml.gz` 6,3 MB → 26,9 MB (4,3×).
> O total resultante (~13,9 GB) é consistente com os 15 GB declarados no `README.md` do corpus.

**Observação estrutural:** apenas `wikis` e `datasets_and_other_corpora` têm subdivisão por
variante linguística (`pt` / `pt-BR`); as demais taxonomias são planas. Isso justifica
9 shards em vez de 7 — ver [ADR-04](07-decisoes-adr.md#adr-04).

**Desequilíbrio extremo:** `pub` tem 1,5 MB e `leg` tem 1.115 MB — uma razão de **743×**.
Qualquer contagem comparativa entre subcorpora **precisa ser normalizada** (ocorrências por
milhão de palavras). Ver [06](06-analise-linguistica.md).

---

## 2. Estrutura XML

Cada arquivo é um `<teiCorpus>` no *namespace* `http://www.tei-c.org/ns/1.0`, contendo:

```
<teiCorpus>
  <teiHeader>            ← cabeçalho global: declara a taxonomia completa (109 categorias)
    ...<classDecl><taxonomy xml:id="Source_typology">...
  </teiHeader>
  <TEI>                  ← 1 documento
    <teiHeader>...</teiHeader>
    <text><body><p>...</p><p>...</p></body></text>
  </TEI>
  <TEI>...</TEI>         ← N documentos por arquivo
</teiCorpus>
```

**[medido]** Documentos por arquivo: `PUBa` = 26, `JUDa` = 1.391, `SOCa` = 4.811.
**[medido]** Relação `<text><body>` por `<TEI>` = **1 para 1** em `SOCa` e `JUDa` — cada
documento tem um único corpo de texto.

**[medido]** Codificação: **UTF-8 limpo**. Zero ocorrências de `U+FFFD` em amostras de
todas as 6 taxonomias inspecionadas (18,9 M caracteres em `leg`, 3,7 M em `pub`, etc.).
Nenhuma correção de *mojibake* é necessária.

> ⚠️ **Armadilha operacional (Windows):** o console pode renderizar UTF-8 como cp1252,
> exibindo `Vit�ria` no lugar de `Vitória`. É defeito de *terminal*, não de dado.
> Mitigação: `PYTHONIOENCODING=utf-8` e uso de `rich` para saída. Ver [08](08-riscos-e-desempenho.md).

---

## 3. Achado crítico ⚠️ — `<p>` no ramo legislativo é uma linha, não um parágrafo

**[medido]** em `legislative_branch/LEGa.xml.gz`:

| Métrica | Valor |
|---|---|
| `<p>` por documento (mediana) | **6.651** |
| `<p>` por documento (máximo) | **366.411** |
| Caracteres por `<p>` — mediana | **47** |
| Caracteres por `<p>` — p99 | 66 |
| Caracteres por documento — mediana | 88.220 |
| Caracteres por documento — p90 | 1.624.472 |
| Caracteres por documento — **máximo** | **16.140.061** (16 MB) |

Amostra literal de `<p>` consecutivos (documento de tipo
`#PROCEEDINGS_OF_THE_CONSTITUTIONAL_CONVENTIONS_LEG_M`):

```
'IX — os bens que atualmente lhe pertencem ou'
'que vierem a ser atribuídos à União por tratados'
'internacionais.'
'Parágrafo único — É considerada indispensável'
'à defesa das fronteiras a faixa interna de cem'
'quilômetros de largura, paralela à linha divisória'
```

São **linhas tipográficas de OCR**, com quebra a ~47 caracteres. Uma única sentença atravessa
3–6 elementos `<p>`.

### Consequência arquitetural

Indexar em nível de `<p>` faria **toda consulta multipalavra falhar silenciosamente** em
5,2 GB do corpus (37% do total). A busca por `"atribuídos à União"` não retornaria nada, e o
pesquisador concluiria — erradamente — que a construção não ocorre nas Atas Constituintes.

Esse é o pior tipo de defeito: **falso negativo sem sinal de erro.**

**Solução adotada:** juntar todos os `<p>` do documento, normalizar, e **re-segmentar em
sentenças**. Ver [ADR-02](07-decisoes-adr.md#adr-02) e [05](05-pipeline-de-indexacao.md).

### Granularidade nas demais taxonomias (para contraste)

**[medido]**

| Taxonomia | `<p>`/doc (mediana) | chars/`<p>` (mediana) | chars/doc (mediana) | Natureza do `<p>` |
|---|---:|---:|---:|---|
| `leg` | 6.651 | 47 | 88.220 | **linha de OCR** |
| `wik/pt-BR` | 18 | 51 | 1.886 | parágrafo curto / item de lista |
| `uni` | 16 | 352 | 6.480 | **parágrafo real** |
| `jud` | — | — | 12.793 (média) | parágrafo real |

A heterogeneidade confirma: **nenhuma regra baseada em `<p>` serve para todo o corpus.**
A re-segmentação em sentenças é a única unidade uniforme.

---

## 4. Metadados disponíveis no `teiHeader`

Este é o achado mais **subaproveitado** do corpus: a API oficial devolve o `teiHeader` como
string XML crua, deixando toda a extração a cargo do usuário. Na prática, quase ninguém usa.

Campos extraíveis por documento (caminhos relativos a `TEI/teiHeader`):

### 4.1 Identificação e proveniência Carolina

| Campo | Caminho | Exemplo |
|---|---|---|
| ID Carolina | `fileDesc/titleStmt/title` | `PUB000000001a` |
| Tokens (declarado) | `fileDesc/extent/measure[@unit='tokens']/@quantity` | `3115` |
| Originalidade (%) | `fileDesc/extent/measure[@type='originality']/@quantity` | `89` |
| Data de download | `fileDesc/publicationStmt/date[@type='Download']` | `2021-05-10` |
| Data de extração | `fileDesc/publicationStmt/date[@type='Extraction']` | `2022-12-01` |
| Licença Carolina | `fileDesc/publicationStmt/availability/license` | `CC BY-SA 4.0` |
| Taxonomia Carolina | `profileDesc/textClass/catRef/@target` | `#PUBLIC_DOMAIN_WORKS` |

### 4.2 Proveniência da fonte original (`fileDesc/sourceDesc/biblFull/`)

| Campo | Caminho (dentro de `biblFull`) | Exemplo |
|---|---|---|
| Título original | `fileDesc/titleStmt/title/name` | `7 Canções (poesia)` |
| **Autor** | `fileDesc/titleStmt/author` | `Salomão Rovedo` |
| **URL de origem** | `fileDesc/titleStmt/title/media/@url` | `http://www.dominiopublico.gov.br/...` |
| MIME / arquivo-fonte | `media/@mimeType`, `@source` | `application/pdf`, `ea000019.pdf` |
| Patrocinador | `fileDesc/titleStmt/sponsor` | `Governo Federal do Brasil` |
| Autoridade | `fileDesc/publicationStmt/authority` | `Domínio Público` |
| **Data original** | `fileDesc/publicationStmt/date` | `1987`, `2015-11-13 - 2015-12-07` |
| Licença original | `fileDesc/publicationStmt/availability/license` | `CC BY-SA 2.5 Brazil` |
| Bytes / tokens / páginas | `fileDesc/extent/measure[@unit=…]` | `85457`, `1234`, `1` |
| Série | `fileDesc/seriesStmt/title` | `Fatos E curiosidades De Harry Potter` |
| **Gênero textual** | `profileDesc/textClass/catRef/@target` | `#POETRY_LIT_W` |
| **Variante linguística** | `profileDesc/langUsage/language/@ident` | `pt-BR` |
| Modo (escrito/falado) | `profileDesc/textDesc/channel/@mode` | `w` |
| Constituição | `profileDesc/textDesc/constitution/@type` | `composite` |
| Domínio | `profileDesc/textDesc/domain` | `Literary` |
| Preparação | `profileDesc/textDesc/preparedness/@type` | `monitored` |

**Implicação:** com esses campos indexados como colunas relacionais, um sintaticista pode
escrever filtros como `genero = POETRY_LIT_W & ano < 1990 & lang = pt-BR` — algo hoje
impossível sem escrever um parser XML próprio.

> ⚠️ Muitos elementos aparecem **vazios** (`<editor role="translator" />`, `<publisher />`,
> `<date />`). O extrator deve tratar campo vazio como `NULL`, nunca como string vazia, e
> contabilizar taxas de preenchimento por shard no manifesto. **[a validar]** na Fase 0:
> qual a cobertura real de `author`, `date` e `url` por taxonomia.

---

## 5. Taxonomia de gêneros textuais

**[medido]** O `teiHeader` global declara **109 categorias** em hierarquia de 3 níveis,
com `catDesc` bilíngue (en/pt). Estrutura resumida:

```
WRITTEN_TEXT (Texto escrito)
├── ACADEMIC_W ......... ARTICLE_ACA_W, DISSERTATION_ACA_W, ESSAY_ACA_W,
│                        MONOGRAPH_ACA_W, THESIS_ACA_W, ORGANIZATION_OF_STUDY_…
├── COMMERCIAL_W ....... PRODUCT_REVIEW_COM_W, PROMOTIONAL_COM_W
├── ENTERTAINMENT_W
├── INSTRUCTIONAL_W .... DIDACTIC_INS_W, EDUCATIONAL_RESOURCES_INS_W,
│                        HELP_DOCUMENTATION_INS_W, TRAVEL_GUIDE_INS_W, VOCABULARY_ENTRY_INS_W
├── JOURNALISTIC_W ..... ARTICLE_JOU_W, NEWS_JOU_W, OPINION_JOU_W, FEATURE_JOU_W,
│                        JOURNALISTIC_BLOG_JOU_W, PODCAST_JOU_W, READER_SPACE_JOU_W,
│                        REGIONAL_EDITION_JOU_W, SECTION_JOU_W, SCIENTIFIC_NEWS_JOU_W,
│                        COURSES_JOU_W, USP_JOURNAL_JOU_W, USP_RADIO_JOU_W, USP_TV_JOU_W
├── JURIDICAL_W ........ APPELLATE_DECISION_RECORDS_JUR_W, PRECEDENTS_BULLETIN_JUR_W,
│                        CONSTITUTION_ANNOTATED_JUR_W, RESOLUTION_JUR_W, TREATY_JUR_W, …
├── LEGISLATIVE_W
├── LITERARY_W ......... POETRY_LIT_W, NOVEL_LIT_W, SHORT_STORY_LIT_W, CRONICA_LIT_W,
│                        CORDEL_LIT_W, FABLE_LIT_W, CHILDRENS_AND_YOUNG_ADULT_LITERATURE_LIT_W,
│                        ORIGINAL_STORY_LIT_W, QUARTET_LIT_W
├── PEDAGOGICAL_W
└── VIRTUAL_FORUM_W .... BLOG_POST_VIR_W, PERSONAL_BLOG_VIR_W, TWEET_VIR_W,
                         DISCUSSION_VIR_W, FAQ_VIR_W, USER_PAGE_VIR_W, …

TRANSCRIBED_SPEECH (Fala transcrita)
├── ACADEMIC_S ......... NEUROPSYCHOLOGICAL_TESTING_ANSWERS_ACA_S
├── ENTERTAINMENT_S .... SUBTITLE_ENT_S
├── JURIDICAL_S ........ SPEECH_JUR_S
└── COMMERCIAL_S, INSTRUCTIONAL_S, JOURNALISTIC_S, LEGISLATIVE_S, LITERARY_S,
    PEDAGOGICAL_S, VIRTUAL_FORUM_S

MIXED (Misto)
├── JURIDICAL_M ........ OPEN_COURT_HEARING_JUR_M
├── LEGISLATIVE_M ...... JOURNAL_OF_THE_CHAMBER_OF_DEPUTIES_LEG_M,
│                        PROCEEDINGS_OF_THE_CONSTITUTIONAL_CONVENTIONS_LEG_M,
│                        PROCEEDINGS_OF_THE_REPUBLIC_LEG_M
└── ACADEMIC_M, COMMERCIAL_M, ENTERTAINMENT_M, INSTRUCTIONAL_M, JOURNALISTIC_M,
    LITERARY_M, PEDAGOGICAL_M, VIRTUAL_FORUM_M

+ taxonomia Carolina (nível de coleta): DATASETS_AND_OTHER_CORPORA, JOURNALISTIC_TEXTS,
  JUDICIAL_BRANCH, LEGISLATIVE_BRANCH, PUBLIC_DOMAIN_WORKS, SOCIAL_MEDIA,
  UNIVERSITY_DOMAINS, WIKIS
```

**Relevância sintática direta:** o eixo `WRITTEN_TEXT` / `TRANSCRIBED_SPEECH` / `MIXED` é
exatamente a variável de **modalidade** que condiciona colocação pronominal, ordem
SV/VS e concordância variável no PB. Ter isso como filtro de primeira classe é o maior
diferencial deste sistema frente a um `grep`.

A hierarquia deve ser materializada em uma tabela de dimensão (`generos`), permitindo
consultar por nó pai (`genero_l1 = 'TRANSCRIBED_SPEECH'`) e não só pela folha.

---

## 6. Medições de desempenho (base para as estimativas)

Todas **[medido]** neste ambiente (i5-10300H, 7,8 GB RAM, Python 3.13.1, disco C:).

### 6.1 Parsing XML — `xml.etree.ElementTree.iterparse` da stdlib

| Arquivo | Descomprimido | Tempo | Vazão |
|---|---:|---:|---:|
| `SOCa.xml.gz` | 26,1 MB | 0,74 s | **35,4 MB/s** |
| `JUDa.xml.gz` | 26,9 MB | 0,75 s | **36,1 MB/s** |

→ ~35 MB/s por núcleo, incluindo descompressão gzip e extração de texto.
**`lxml` não é necessário** (e não está instalado). Ver [ADR-11](07-decisoes-adr.md#adr-11).

### 6.2 Indexação FTS5

Teste: 1.391 documentos jurídicos, 18,1 MB de texto, `tokenize="unicode61 remove_diacritics 2"`,
`detail=full`, `journal_mode=OFF`, `synchronous=OFF`.

| Métrica | Valor |
|---|---:|
| Tempo de inserção + commit | 0,54 s |
| Vazão | **33,7 MB de texto/s** |
| Tamanho do `.db` (índice + conteúdo armazenado) | 26,8 MB |
| Razão `.db` / texto | **1,48×** |

Consultas sobre esse índice:

| Consulta | Ocorrências | Tempo |
|---|---:|---:|
| `"de que"` (frase) | 996 | 4,4 ms |
| `sentenca` (termo, sem acento) | 461 | 0,4 ms |
| `NEAR(recurso provido, 5)` | 208 | 0,4 ms |

> Confirmações: (a) FTS5 **está disponível** — SQLite 3.45.3; (b) `remove_diacritics 2`
> funciona — `sentenca` casou com `sentença`; (c) busca de frase e `NEAR` funcionam, que são
> os operadores de que a sintaxe precisa.

### 6.3 Anotação com spaCy `pt_core_news_sm`

Amostra: 300 documentos de `university_domains`, 2,14 MB, 390.488 tokens.

| Configuração | Vazão | Uso previsto |
|---|---:|---|
| `tok2vec` + `morphologizer` (POS/morfologia) | **20.422 tokens/s** | anotação sob demanda |
| `+ parser + lemmatizer + attribute_ruler` | **14.865 tokens/s** | lema; dependências opcionais |

**[medido]** Densidade: **5,48 caracteres por token**.

### 6.4 Extrapolações **[estimado]**

Base: ~13,9 GB de XML → texto puro estimado em **7–9 GB** (fração de texto medida:
40% em `SOCa`, 66% em `JUDa`) → **~1,3–1,6 bilhão de tokens** (a 5,48 chars/token).

| Operação | Cálculo | Estimativa |
|---|---|---|
| Parsing de todo o XML, 1 núcleo | 13.900 MB ÷ 35 MB/s | ~6,6 min |
| Parsing, 4 processos | | **~2–3 min** |
| Indexação FTS5 de 8 GB, vazão ideal | 8.000 MB ÷ 33,7 MB/s | ~4 min |
| Indexação FTS5 real (degradação de B-tree em escala, I/O de disco) | fator 5–15× | **1,5–4 h** |
| Anotação POS de **todo** o corpus, 1 núcleo | 1,45e9 ÷ 20.422 tok/s | **~20 h** |
| Anotação POS de todo o corpus, 4 processos | | ~5 h |
| Anotação POS de `pub`+`soc`+`uni` (215 MB), 4 processos | 39 M tokens | **~10 min** |
| Anotação POS de **5.000 linhas de concordância** | ~110 k tokens | **~5,4 s** |

> A última linha é a justificativa quantitativa de [ADR-07](07-decisoes-adr.md#adr-07):
> anotar sob demanda é **~13.000× mais barato** que anotar tudo, para o uso real.

---

## 7. Ambiente: capacidades e limitações verificadas

| Item | Estado | Consequência |
|---|---|---|
| SQLite | 3.45.3, **FTS5 disponível** | motor de índice viável sem dependência externa |
| `contentless_delete` (FTS5) | requer ≥ 3.43 → **disponível** | permite índice sem conteúdo com remoção |
| `load_extension` | **desabilitado** (`OperationalError`) | ❌ sem tokenizador FTS5 customizado em C; radicalização vai para a camada Python |
| `spacy` + `pt_core_news_sm` | 3.8.14, **instalados** | anotação sob demanda pronta para uso |
| `pandas`, `pyarrow`, `numpy`, `regex`, `rich`, `typer`, `tqdm`, `nltk` | instalados | exportação e CLI sem dependências novas |
| `lxml` | **ausente** | `corpus-carolina.py` depende dele; nosso pipeline usa a stdlib e não precisa |
| `duckdb`, `whoosh`, `tantivy`, `zstandard`, `orjson` | ausentes | evitados pelo desenho; compressão via `zlib` da stdlib |
| RAM | 7,8 GB | pipeline obrigatoriamente *streaming* |
| CPU | 4 núcleos físicos / 8 lógicos | pool de ingestão de 4 processos |
| Disco C: | 476 GB, **99 GB livres (80% usado)** | índice de ~9 GB cabe; monitorar |
| Localização do repositório | **dentro do OneDrive** | ⚠️ índice deve ficar fora — [ADR-08](07-decisoes-adr.md#adr-08) |

---

## 8. Recursos existentes reaproveitáveis

| Arquivo | Uso no novo sistema |
|---|---|
| `corpus/*/checksum.sha256` | **Verificação de integridade e reindexação incremental** — o corpus já traz o `sha256` do XML *descomprimido* de cada arquivo. Reaproveitado no manifesto. |
| `corpus/schema.rng` | Esquema RelaxNG (64 KB) — referência normativa para os caminhos de extração de metadados |
| `corpus-carolina.py` | Referência de como o projeto oficial extrai `meta`/`text`; nosso extrator é um superconjunto |
| `corpus/hash.py` | Lógica de varredura recursiva de `*.xml.gz` já escrita; reaproveitável |
| `README.md` (raiz) | Contagens oficiais por taxonomia, para conferência cruzada com o manifesto |

---

## 9. Questões em aberto **[a validar]** na Fase 0

1. **Hifenização de quebra de linha em `leg`.** Nas amostras inspecionadas, as quebras
   ocorreram em fronteira de palavra. É preciso confirmar em volume se existem palavras
   partidas com hífen no fim da linha (`estabele-` / `cido`) — se existirem, o normalizador
   precisa de regra de rejunção.
2. **Ruído recorrente em `leg`.** Atas de OCR costumam repetir cabeçalho/rodapé/número de
   página a cada N linhas. Medir a incidência e decidir se são removidos (com registro) ou
   preservados.
3. **Cobertura real de metadados.** Percentual de documentos com `author`, `date` e `url`
   preenchidos, por shard.
4. **Formato do campo `date` original.** Foram observados `1987` e `2015-11-13 - 2015-12-07`.
   Levantar o conjunto de formatos para escrever o normalizador de `ano`.
5. **Efeito do hífen na tokenização.** Medir quantas ocorrências de ênclise/mesóclise são
   perdidas ou ganhas com `tokenchars '-'`. Decisão em [ADR-05](07-decisoes-adr.md#adr-05).
6. **Fração real de texto sobre XML.** Medida em 2 arquivos (40% e 66%); refinar com uma
   varredura completa barata para dimensionar o índice com precisão.
7. **Duplicatas.** O campo `originality` (%) sugere que o corpus tem sobreposição conhecida.
   Avaliar se convém marcar documentos de baixa originalidade para exclusão opcional em
   contagens de frequência.

---

**Anterior:** [00 — Visão geral](00-visao-geral.md) · **Próximo:** [02 — Arquitetura](02-arquitetura.md)
