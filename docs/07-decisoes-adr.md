# 07 — Decisões de arquitetura (ADRs)

Registro das decisões estruturais, com contexto, alternativas consideradas e consequências.
Formato enxuto de *Architecture Decision Record*.

---

## ADR-01 — SQLite FTS5 como motor de índice {#adr-01}

**Status:** proposto
**Contexto:** é preciso indexar ~8 GB de texto em uma máquina com 7,8 GB de RAM e 4 núcleos,
usada por pesquisadores de Letras em Windows, sem administrador de sistemas.

**Decisão:** usar **SQLite FTS5**, da biblioteca-padrão do Python.

**Alternativas:**

| Opção | Descartada porque |
|---|---|
| Whoosh | Python puro; 1–2 ordens de grandeza mais lento — construção de dias |
| Tantivy / PyLucene | Exigem *toolchain* Rust/JVM; barreira real de instalação para o público-alvo |
| Elasticsearch | Servidor + JVM com ≥ 4 GB de *heap* em máquina de 7,8 GB; operação desproporcional |
| DuckDB FTS | Sem busca de frase e `NEAR` maduros — justamente o que a sintaxe exige |
| `ripgrep` sobre texto extraído | Sem metadados, sem ranking, relendo GBs a cada consulta |
| CWB/CQP | Padrão-ouro da área, mas instalação hostil em Windows e exige formato vertical pré-anotado |

**Evidência [medido]:** FTS5 disponível (SQLite 3.45.3); indexação a 33,7 MB/s; consultas de
frase em 4,4 ms e `NEAR` em 0,4 ms sobre 18 MB.

**Consequências:**
- ✅ Zero instalação; um arquivo por shard, copiável e compartilhável
- ✅ Frase, `NEAR`, prefixo e BM25 nativos
- ⚠️ Um escritor por banco → mitigado pelo sharding ([ADR-04](#adr-04))
- ⚠️ Sem *stemming* de português → tratado na camada de aplicação ([ADR-05](#adr-05))

---

## ADR-02 — Segmento de indexação = sentença {#adr-02}

**Status:** proposto
**Contexto:** três granularidades possíveis — documento, `<p>` ou sentença.

**Evidência [medido]** em `legislative_branch` (5,2 GB, 37% do corpus):
- até **366.411** elementos `<p>` por documento, com mediana de **47 caracteres**;
- documentos de até **16 MB**;
- `<p>` é uma **linha tipográfica de OCR**, não um parágrafo:
  `'IX — os bens que atualmente lhe pertencem ou'` / `'que vierem a ser atribuídos à União por tratados'` / `'internacionais.'`

**Decisão:** juntar todos os `<p>`, normalizar e **re-segmentar em sentenças**; indexar a
sentença.

**Por que não `<p>`:** toda consulta multipalavra falharia em 37% do corpus, **sem erro
visível**. Buscar `"atribuídos à União"` retornaria zero, e o pesquisador concluiria que a
construção não ocorre nas Atas Constituintes. Falso negativo silencioso é o pior modo de
falha possível numa ferramenta de pesquisa.

**Por que não documento:** KWIC em documento de 16 MB é impraticável; `NEAR` perde sentido
linguístico se a proximidade atravessa páginas; contagens por documento seriam grosseiras.

**Consequências:**
- ✅ Unidade uniforme em todo o corpus, apesar da heterogeneidade de origem
- ✅ `NEAR` e sequências ganham fronteira linguisticamente correta
- ✅ KWIC direto por deslocamentos
- ⚠️ ~66 M de linhas em `segments` (~2,4 GB, 24% do índice) — preço aceitável
- ⚠️ Depende da qualidade do segmentador → validação obrigatória na Fase 0
- ⚠️ Padrões que atravessam sentenças não são expressáveis (não é objetivo)

**Teste de regressão obrigatório:** a frase `"atribuídos à União por tratados internacionais"`
tem que ser encontrada em `leg`. Falha aí = alguém voltou a indexar por `<p>`.

---

## ADR-03 — Armazenamento em dois níveis: texto comprimido + índice sem conteúdo {#adr-03}

**Status:** proposto

**Decisão:** texto canônico em `doctext` (blocos de 256 KB, `zlib`), `segments` guardando
apenas deslocamentos, e `fts` como tabela **contentless** (`content=''`).

**Alternativas:**
- Texto dentro do FTS5 → duplicação; ~+3 GB
- Texto em `segments` → duplicação e perda de contexto entre sentenças
- Sem armazenar texto (reler o XML) → KWIC exigiria descomprimir e reparsear um `.xml.gz` por
  linha exibida: inviável

**Blocagem de 256 KB:** com documento de 16 MB, exibir 200 caracteres de KWIC descomprimiria
16 MB. Com blocos, descomprime-se 256 KB — **64× menos trabalho**.

**Consequências:**
- ✅ Uma única cópia do texto, comprimida (~3×)
- ✅ Janela de KWIC arbitrária, sem as limitações de `snippet()`
- ✅ Contexto além da sentença sai de graça (mesmo bloco)
- ⚠️ Perde `snippet()`/`highlight()` do FTS5 — irrelevante, o KWIC é próprio
- ⚠️ `contentless_delete=1` exige SQLite ≥ 3.43 — **temos 3.45.3 [medido]**

---

## ADR-04 — Sharding por taxonomia e variante linguística {#adr-04}

**Status:** proposto
**Decisão:** 9 shards — `leg`, `jud`, `pub`, `soc`, `uni`, `wik-pt`, `wik-ptbr`, `dat-pt`,
`dat-ptbr`.

**Justificativa:**

| Motivo | Efeito |
|---|---|
| SQLite tem 1 escritor por banco | 9 escritores paralelos → horas viram dezenas de minutos |
| "só no jurídico" é recorte real | vira `--shards jud`, sem custo de filtragem |
| Iteração no pipeline | reconstruir só os shards afetados |
| Tamanho máximo ~3,5 GB | cópia, backup e compartilhamento continuam práticos |
| Isolamento de falha | um shard corrompido não invalida o índice |
| `pt` vs. `pt-BR` | separação gratuita de uma distinção linguisticamente relevante |

**Consequências:**
- ✅ Construção paralela; recortes comuns ficam gratuitos
- ⚠️ Consultas globais exigem fan-out e merge → custo do shard mais lento, não a soma
- ⚠️ Estatísticas globais (`vocab`) precisam de agregação entre shards → tabela de totais no
  manifesto

---

## ADR-05 — Política de tokenização: hífen preservado, acento dobrado {#adr-05}

**Status:** proposto — ⚠️ **a decisão de maior impacto linguístico**
**Contexto:** `load_extension` está desabilitado **[medido]**, logo não há tokenizador FTS5
customizado em C. Resta configurar o `unicode61`.

**Decisão:** `tokenize = "unicode61 remove_diacritics 2 tokenchars '-'"`.

### Por que preservar o hífen

O `unicode61` padrão trata `-` como separador: `disse-me` viraria `disse` + `me`. Isso
apagaria do índice a distinção entre:

| Forma | Fenômeno | Sem `tokenchars` |
|---|---|---|
| `disse-me` | ênclise | indistinguível de `disse me` |
| `dar-lhe-ia` | **mesóclise** | destruída em 3 tokens |
| `guarda-chuva` | composto | virava dois tokens |

Colocação pronominal é **objeto central** da sintaxe do PB. Sem o hífen, a persona primária
do sistema fica sem seu principal objeto de estudo.

### Contrapartida honesta

Com `tokenchars '-'`, buscar `disse` **não** encontra `disse-me`. Mitigações:

1. Expansão de consulta: `[palavra="disse"]` gera `disse OR disse-*` no pré-filtro;
2. `vocab_rev` resolve padrões de sufixo (`*-lhe`) por varredura de faixa;
3. A verificação em Python aplica a semântica exata que o usuário pediu.

**[a validar]** na Fase 0: medir, em `jud` e `soc`, quantas ocorrências cada política
encontra e perde. Se a expansão se mostrar insuficiente, a alternativa é uma segunda coluna
FTS com tokenização padrão (custo: ~+40% de índice).

### Por que dobrar o acento no índice

`remove_diacritics 2` faz `sentenca` casar com `sentença` **[medido]**. O índice é
deliberadamente tolerante (**recall**); a sensibilidade a acento é reposta na verificação, e
vem **ligada por padrão** — para linguística do português, `esta`/`está` e `pais`/`país` são
pares distintos. Quem quiser tolerância desliga explicitamente.

**Consequências:**
- ✅ Clíticos, mesóclise e compostos consultáveis
- ✅ Precisão de acento/caixa alternável sem reconstruir o índice
- ⚠️ Alterar esta configuração invalida o índice → registrada no manifesto
- ⚠️ Índice e verificação **têm** que usar o mesmo tokenizador; divergência gera falsos
  negativos silenciosos

---

## ADR-06 — Linguagem de consulta CQL-lite {#adr-06}

**Status:** proposto
**Decisão:** subconjunto compatível com CQP, com apelidos em português, e parser próprio de
descida recursiva (sem dependências).

**Alternativas:** só caixa de busca (não expressa sintaxe); só API Python (exclui quem não
programa); linguagem inteiramente nova (descarta o conhecimento prévio da área); CQP completo
(inclui relações de dependência, inviáveis aqui).

**Consequências:**
- ✅ Quem conhece Sketch Engine/CQPweb não reaprende
- ✅ Sem dependência de gerador de parser
- ✅ Casos simples continuam simples (`casa` é uma consulta válida)
- ⚠️ Compatibilidade parcial precisa ser documentada explicitamente
- ⚠️ Mensagens de erro de parser exigem cuidado — o usuário não é programador

---

## ADR-07 — Anotação morfossintática sob demanda {#adr-07}

**Status:** proposto — **é a resposta ao requisito "mesmo não sendo anotado"**

**Decisão:** rodar spaCy `pt_core_news_sm` **apenas sobre as sentenças recuperadas**, com
cache persistente. Pré-anotação completa disponível como opção para os shards pequenos.

**Evidência [medido]:** 20.422 tokens/s (POS) e 14.865 tokens/s (com parser e lema).

| Estratégia | Custo | Cobertura |
|---|---|---|
| Anotar todo o corpus | ~20 h (1 núcleo) / ~5 h (4 proc.) + dezenas de GB | total |
| **Anotar sob demanda** | **5,4 s por 5.000 linhas** | o que foi recuperado |
| Pré-anotar `pub`+`soc`+`uni` | ~10 min | 215 MB |

Diferença de ~13.000× para o uso real.

**Consequências:**
- ✅ Consultas com POS/lema funcionam desde o primeiro dia, sem espera
- ✅ Cache torna a reanálise do mesmo material instantânea
- ✅ Trocar o modelo spaCy não exige reconstruir o índice (invalida só o cache)
- ⚠️ Consultas **sem âncora lexical** exigem varredura → tratadas por [ADR-09](#adr-09)
- ⚠️ Alinhamento entre as duas tokenizações é obrigatório
  ([06 §6](06-analise-linguistica.md#alinhamento-de-tokenização-️))
- ⚠️ `pt_core_news_sm` é o modelo pequeno; sua acurácia limita as consultas por POS. Documentar,
  e permitir `pt_core_news_lg` se instalado

---

## ADR-08 — Índice fora do OneDrive {#adr-08}

**Status:** proposto — **risco operacional mais severo do projeto**

**Contexto:** o repositório está em
`C:\Users\Administrador\OneDrive\Documentos\PÓS-GRADUAÇÃO\MESTRADO\CORPUS\Carolina`.

**Decisão:** o índice vive em `%LOCALAPPDATA%\carolina-search\index\` por padrão. Na
inicialização, o sistema **verifica se o caminho do índice está sob uma pasta sincronizada e
recusa-se a prosseguir**, salvo `--permitir-nuvem`.

**Por quê:** um SQLite multi-GB em escrita constante dentro do OneDrive causa:

1. **Sincronização contínua** de arquivos de vários GB a cada `COMMIT`;
2. **Bloqueio de arquivo** pelo cliente de sincronização durante a escrita → `database is locked`;
3. **Corrupção real** — SQLite exige semântica de arquivo que sincronizadores não garantem;
4. **Estouro de cota** — ~10 GB de índice consumindo o plano do OneDrive;
5. **Arquivos sob demanda** — o Windows pode marcar o `.db` como *online-only*, e cada leitura
   dispara download.

O risco 3 é o pior: corrupção silenciosa produz resultados errados sem mensagem de erro.

**Consequências:**
- ✅ Índice em disco local rápido, sem sincronização
- ✅ `.gitignore` fica trivial (o índice nem está na árvore)
- ⚠️ Índice não é sincronizado entre máquinas → compartilhamento explícito por cópia do `.db`
- ⚠️ Reinstalação do sistema exige reconstruir (1,5–3,5 h) ou restaurar de backup

---

## ADR-09 — Consultas sem âncora exigem confirmação explícita {#adr-09}

**Status:** proposto

**Contexto:** `[pos="VERB"] [pos="PRON"]` não tem termo lexical; exigiria anotar 66 M de
sentenças (~25–40 min).

**Decisão:** o planejador detecta a ausência de âncora e **para**, mostrando o custo estimado
e as opções: restringir por metadados, restringir por shard, adicionar âncora lexical, ou
`--modo-varredura` com barra de progresso e cancelamento.

**Alternativas:** executar em silêncio (usuário acha que travou e mata o processo — e talvez
o índice em construção); recusar sempre (impede pesquisas legítimas); limitar a N resultados
(gera contagens erradas, o pior desfecho para trabalho quantitativo).

**Consequências:**
- ✅ Nenhuma espera inexplicada
- ✅ O usuário aprende a formular consultas eficientes pela própria mensagem
- ✅ Consultas caras continuam possíveis, com consentimento
- ⚠️ Um passo a mais em casos legítimos → mitigado pela pré-anotação dos shards pequenos

---

## ADR-10 — Índice de sufixos (`vocab_rev`) {#adr-10}

**Status:** proposto

**Contexto:** o FTS5 tem prefixo (`palav*`) mas **não** sufixo. Em português, o sufixo é
frequentemente o que importa: `-se`, `-lhe`, `-ria`, `-mente`, `-ção`, `-inho`, `-íssimo`.

**Decisão:** manter `vocab_rev` com as formas invertidas, como `PRIMARY KEY` em tabela
`WITHOUT ROWID` (B-tree ordenado). `*-lhe` vira varredura de faixa por `'ehl-'`, resolvendo
para as formas reais que alimentam o pré-filtro do FTS5.

**Consequências:**
- ✅ Padrões morfológicos ganham âncora e deixam de ser varredura
- ✅ Custo baixo: ~10⁷ formas contra 8 GB de texto
- ✅ Serve também a listas do tipo "todos os advérbios em `-mente`"
- ⚠️ Sufixos muito produtivos (`-se`) ainda geram disjunções grandes → limitar por `df` e
  avisar

---

## ADR-11 — `xml.etree` da stdlib em vez de `lxml` {#adr-11}

**Status:** proposto

**Contexto:** `lxml` **não está instalado** neste ambiente **[medido]** — o próprio
`corpus-carolina.py` do repositório depende dele.

**Decisão:** usar `xml.etree.ElementTree.iterparse` da biblioteca-padrão. Usar `lxml`
automaticamente **se** estiver disponível, como otimização opcional.

**Evidência [medido]:** 35–36 MB/s por núcleo com a stdlib, incluindo gzip — suficiente para
processar todo o corpus em ~2–3 min com 4 processos.

**Consequências:**
- ✅ Zero dependências para a etapa mais pesada
- ✅ Instalação sem compilador em Windows
- ⚠️ Sem `huge_tree`/`recover` do `lxml` → tratamento de erro próprio, por arquivo
- ⚠️ `el.clear()` é obrigatório e mais delicado que no `lxml`

---

## ADR-12 — Reprodutibilidade como requisito de primeira classe {#adr-12}

**Status:** proposto

**Contexto:** trata-se de pesquisa de mestrado. Números que aparecem numa dissertação
precisam ser defensáveis e reproduzíveis meses depois.

**Decisão:** três mecanismos obrigatórios —

1. **`manifesto.json`** — versão do corpus, `sha256` por arquivo, configuração de
   tokenizador/segmentador/normalizador, contagens, erros, cobertura de metadados;
2. ***Query card* (`.consulta.toml`)** — a consulta, as opções, a semente da amostra e os
   números obtidos, com `csearch repetir` conferindo divergências;
3. **Proveniência por linha** — todo resultado carrega `carolina_id`, gênero, licença e URL.

**Consequências:**
- ✅ Apêndice metodológico da dissertação sai pronto do sistema
- ✅ Divergências entre execuções são detectadas, não descobertas em banca
- ✅ Reindexação incremental sai de graça do mesmo mecanismo
- ⚠️ Alterar segmentador/normalizador **tem que** invalidar shards; disciplina de versionamento
  é obrigatória

---

## Resumo

| ADR | Decisão | Risco se ignorada |
|---|---|---|
| 01 | SQLite FTS5 | Ferramenta que ninguém consegue instalar |
| **02** | **Segmento = sentença** | **37% do corpus com falsos negativos silenciosos** |
| 03 | Texto comprimido em blocos + FTS sem conteúdo | Índice 40% maior; KWIC lento |
| 04 | 9 shards | Construção serial de muitas horas |
| **05** | **Hífen preservado, acento dobrado** | **Colocação pronominal inconsultável** |
| 06 | CQL-lite | Sintaticista dependente de programador |
| **07** | **Anotação sob demanda** | **20 h de espera antes da 1ª consulta** |
| **08** | **Índice fora do OneDrive** | **Corrupção silenciosa do índice** |
| 09 | Confirmação em consulta sem âncora | Usuário mata processo achando que travou |
| 10 | Índice de sufixos | Padrões morfológicos viram varredura |
| 11 | stdlib em vez de `lxml` | Dependência ausente bloqueia a instalação |
| 12 | Reprodutibilidade | Números indefensáveis em banca |

Em negrito, as quatro decisões cuja reversão comprometeria o projeto.

---

**Anterior:** [06 — Análise linguística](06-analise-linguistica.md) · **Próximo:** [08 — Riscos e desempenho](08-riscos-e-desempenho.md)
