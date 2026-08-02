# 05 — Pipeline de indexação

## 1. Visão geral

```
corpus/**/*.xml.gz  (554 arquivos, somente leitura)
        │
   ┌────▼─────┐
   │ varredor │  enumera · casa com checksum.sha256 · decide o que reindexar
   └────┬─────┘
        │  lista de arquivos → distribuída por shard
   ┌────▼──────────────────────────────────────────────┐
   │ POOL DE 4 PROCESSOS  (CPU-bound)                  │
   │                                                   │
   │  leitor_tei ─▶ extrator_meta ─▶ normalizador      │
   │       │                              │            │
   │       │                        segmentador        │
   │       └──────────────┬───────────────┘            │
   └──────────────────────┼────────────────────────────┘
                          │  lotes (doc + meta + texto + segmentos)
                    ┌─────▼──────┐
                    │  fila por  │
                    │   shard    │
                    └─────┬──────┘
   ┌──────────────────────▼────────────────────────────┐
   │ 9 ESCRITORES  (1 por shard, I/O-bound)            │
   │   docs · doctext(zlib) · segments · fts · vocab   │
   └──────────────────────┬────────────────────────────┘
                          │
                  ┌───────▼────────┐
                  │  finalização   │  merge FTS · optimize · ANALYZE · VACUUM
                  │                │  vocab_rev · manifesto
                  └────────────────┘
```

---

## 2. Etapa 1 — Varredor e incrementalidade

O corpus **já traz** `corpus/<taxonomia>/checksum.sha256`, com o `sha256` do XML
*descomprimido* de cada arquivo. Isso é aproveitado integralmente:

```
para cada arquivo em corpus/**/*.xml.gz:
    sha_corpus  = leitura de checksum.sha256 da taxonomia
    sha_indice  = manifesto.shards[shard].sha256.get(caminho_relativo)

    se sha_indice ausente        → INDEXAR (novo)
    senão se sha ≠ sha_indice    → REINDEXAR (alterado)
    senão se config mudou        → REINDEXAR (tokenizador/segmentador/normalizador)
    senão                        → PULAR
```

A reindexação de um arquivo apaga seus documentos via
`DELETE FROM fts WHERE rowid IN (…)` — viabilizado por `contentless_delete=1`
([03 §2.4](03-modelo-de-dados.md#24-fts--índice-invertido)) — e reinsere.

**Ganho:** trocar o segmentador e reconstruir só `pub`+`soc`+`uni` custa minutos, não horas.
Como a Fase 0 existe justamente para iterar nessas decisões, a incrementalidade não é
otimização tardia — é pré-requisito do roadmap.

`csearch validar` roda essa comparação sem indexar, reportando divergências entre índice e
corpus.

---

## 3. Etapa 2 — Leitura TEI

```python
NS = "{http://www.tei-c.org/ns/1.0}"

with gzip.open(caminho, "rb") as f:
    for _, el in ET.iterparse(f, events=("end",)):
        if el.tag == NS + "TEI":
            header = el.find(NS + "teiHeader")
            paragrafos = [e.text for e in el.iterfind(f".//{NS}body/{NS}p") if e.text]
            yield header, paragrafos
            el.clear()          # ← obrigatório: sem isso, o processo estoura a RAM
```

**Medido: ~35 MB/s por núcleo**, incluindo descompressão gzip
([01 §6.1](01-analise-do-corpus.md#61-parsing-xml--xmletreeelementtreeiterparse-da-stdlib)).
Usa apenas a stdlib — `lxml` não está instalado e não é necessário
([ADR-11](07-decisoes-adr.md#adr-11)).

⚠️ **`el.clear()` é crítico.** Documentos legislativos têm até 366.411 elementos `<p>`
([01 §3](01-analise-do-corpus.md#3-achado-crítico----p-no-ramo-legislativo-é-uma-linha-não-um-parágrafo)).
Sem liberar a árvore a cada `<TEI>`, um arquivo de 7 MB comprimido consome vários GB de RAM
— fatal com 7,8 GB disponíveis. **[a validar]** na Fase 0: `clear()` no `<TEI>` deixa
referências pendentes no elemento-raiz; se o pico de memória crescer ao longo do arquivo,
adotar também a limpeza de irmãos anteriores (`del raiz[0]`).

---

## 4. Etapa 3 — Extração de metadados

Mapeamento declarativo (não código imperativo), para que a lista de campos seja legível e
auditável:

```python
CAMPOS = {
  "carolina_id":  "fileDesc/titleStmt/title",
  "tei_tokens":   ("fileDesc/extent/measure[@unit='tokens']", "quantity"),
  "originalidade":("fileDesc/extent/measure[@type='originality']", "quantity"),
  "data_download":"fileDesc/publicationStmt/date[@type='Download']",
  "data_extracao":"fileDesc/publicationStmt/date[@type='Extraction']",
  "licenca":      "fileDesc/publicationStmt/availability/license",
  "licenca_url":  ("fileDesc/publicationStmt/availability/license", "target"),
  "taxonomia_tei":("profileDesc/textClass/catRef", "target"),

  # fonte original — prefixo B = fileDesc/sourceDesc/biblFull
  "titulo":       "B/fileDesc/titleStmt/title/name",
  "autor":        "B/fileDesc/titleStmt/author",
  "url":          ("B/fileDesc/titleStmt/title/media", "url"),
  "mime":         ("B/fileDesc/titleStmt/title/media", "mimeType"),
  "fonte_arquivo":("B/fileDesc/titleStmt/title/media", "source"),
  "patrocinador": "B/fileDesc/titleStmt/sponsor",
  "autoridade":   "B/fileDesc/publicationStmt/authority",
  "data_orig":    "B/fileDesc/publicationStmt/date",
  "serie":        "B/fileDesc/seriesStmt/title",
  "genero":       ("B/profileDesc/textClass/catRef", "target"),
  "lang":         ("B/profileDesc/langUsage/language", "ident"),
  "dominio":      "B/profileDesc/textDesc/domain",
  "modo":         ("B/profileDesc/textDesc/channel", "mode"),
  "constituicao": ("B/profileDesc/textDesc/constitution", "type"),
  "preparacao":   ("B/profileDesc/textDesc/preparedness", "type"),
}
```

Regras de tratamento:

1. **Vazio é `NULL`.** `<publisher />` e `<date />` são frequentes
   ([01 §4](01-analise-do-corpus.md#4-metadados-disponíveis-no-teiheader)). String vazia
   contaminaria filtros e contagens.
2. **Ausência é contabilizada**, por campo e por shard, e vai para `cobertura_meta` no
   manifesto. Se `ano` só existe em 31% de um shard, nenhuma análise diacrônica desse shard
   se sustenta — e o sistema precisa dizer isso antes que vire conclusão.
3. **`genero` → `genero_l2` → `genero_l1`** por consulta a `taxonomia.json`, extraído uma
   única vez do `teiHeader` global do primeiro arquivo.
4. **Normalização de `ano`**: extrai o primeiro `\b(1[89]\d\d|20\d\d)\b` de `data_orig`;
   `NULL` se não houver. Formatos observados: `1987`, `2015-11-13 - 2015-12-07`, vazio.
   **[a validar]** — levantar o conjunto completo de formatos na Fase 0.
5. **Nunca falhar por metadado.** Erro de extração vira aviso no manifesto; o documento é
   indexado com os campos que houver. Perder texto por causa de um cabeçalho malformado
   seria o pior desfecho possível.

---

## 5. Etapa 4 — Normalização (a etapa mais delicada)

Produz o **texto canônico**: a cadeia de caracteres à qual todos os deslocamentos se referem.
Uma vez indexado, alterar o normalizador invalida o shard.

```
paragrafos: list[str]
        │
 (1) junção        →  " ".join(p.strip() for p in paragrafos)
 (2) NFC           →  unicodedata.normalize("NFC", texto)
 (3) rejunção      →  religa palavras partidas por hífen de fim de linha  [a validar]
 (4) espaços       →  colapsa \s+ em " "; remove controles exceto \n
 (5) aspas/traços  →  normaliza «» “” ‘’ e – — para formas canônicas
 (6) ruído         →  remove cabeçalho/rodapé/número de página recorrentes  [opcional]
        │
   texto canônico  +  registro do que foi alterado
```

### 5.1 Junção de parágrafos

Sempre `" "` (espaço), nunca `"\n"`. O motivo é o achado central: em `leg`, os `<p>` são
linhas tipográficas, e uma sentença atravessa 3–6 deles. Juntar com espaço é o que reconstrói
`"IX — os bens que atualmente lhe pertencem ou que vierem a ser atribuídos à União por
tratados internacionais."` a partir de três `<p>` separados.

Guarda-se `n_p_orig` em `docs` como diagnóstico permanente da fragmentação.

### 5.2 Rejunção de hífen **[a validar]**

Nas amostras inspecionadas, as quebras de `leg` caíram em fronteira de palavra. Mas OCR de
atas costuma produzir `estabele-` / `cido`. Regra proposta, a ser habilitada só se a Fase 0
confirmar o fenômeno:

```
se linha termina em "-" e a seguinte começa em minúscula:
    candidato = fim_da_linha_sem_hífen + início_da_seguinte
    se candidato ∈ vocab (frequência ≥ limiar) e o composto com hífen ∉ vocab:
        religa
    senão:
        preserva o hífen
```

A checagem contra o vocabulário evita destruir compostos legítimos (`guarda-chuva`,
`primeiro-ministro`) e clíticos (`disse-me`) — exatamente as formas que a persona primária
estuda. **Na dúvida, preservar.** Um hífen espúrio é ruído; um clítico destruído é dado
perdido.

Isso torna a normalização um processo de **dois passos**: uma primeira varredura constrói o
vocabulário do shard; a segunda aplica a rejunção informada. Custo: dobra o parsing (~6 min
adicionais no total, com 4 processos). Aceitável.

### 5.3 Remoção de ruído — **desligada por padrão**

Atas de OCR repetem cabeçalhos, rodapés e números de página. Isso infla contagens de
frequência e polui o KWIC.

Deliberadamente **opcional** (`--remover-ruido`): remoção automática pode apagar texto
legítimo, e num corpus de pesquisa **fidelidade ao original vence limpeza**. Quando ligada,
registra em `docs.n_chars_removidos` quanto foi retirado, tornando o efeito auditável.

**[a validar]** na Fase 0: medir a incidência real em `leg` antes de decidir.

### 5.4 Preservação de deslocamentos

Os deslocamentos referem-se ao **texto canônico**, não ao XML original. A normalização
ocorre uma única vez, antes da segmentação, e o resultado é o que se armazena. Não há
necessidade de mapear de volta ao XML — a proveniência é garantida por
`(arquivo, ord_arquivo, carolina_id)`, que identifica o `<TEI>` de origem sem ambiguidade.

Simplificação relevante: mapeamento de deslocamentos entre texto normalizado e original é
uma fonte clássica de bugs sutis, e aqui é dispensável.

---

## 6. Etapa 5 — Segmentação em sentenças

Divide o texto canônico em sentenças, devolvendo `(cstart, cend)` de cada uma.

**Não usar o `senter` do spaCy nesta etapa.** A 20.000 tokens/s, segmentar 1,46 bilhão de
tokens custaria ~20 h de CPU **[medido/estimado]** — mais que todo o resto do pipeline
somado. Um segmentador baseado em regras roda uma ou duas ordens de grandeza mais rápido e é
suficiente para o propósito.

Regra proposta (`pt-sbd-v1`), específica para português:

```
Fronteira em [.!?…] seguido de espaço e maiúscula/aspa/travessão, EXCETO quando:

  • o token anterior é abreviatura conhecida
      Sr. Sra. Dr. Dra. Prof. Exmo. Ilmo. art. arts. inc. § pág. p. fls. n. nº
      Min. Des. Rel. Ac. Proc. CF. LTDA. S.A. etc. cf. ex. v.g. i.e.
      jan. fev. mar. abr. jun. jul. ago. set. out. nov. dez.
  • está entre dígitos              (1.500 · 3.2 · art. 5.º)
  • é ordinal                       (1.º · 2.ª)
  • é sigla pontuada                (O.N.U. · E.U.A.)
  • está dentro de aspas/parênteses não fechados
  • a "sentença" resultante teria < 2 tokens  → funde com a anterior
```

A lista de abreviaturas **jurídicas e legislativas** (`art.`, `inc.`, `§`, `fls.`, `Min.`,
`Des.`, `Rel.`) não é ornamento: `leg` + `jud` somam 6,3 GB — 45% do corpus — e sem elas a
segmentação fragmenta massivamente justo onde o volume está.

Limite de segurança: sentença acima de 5.000 caracteres é dividida à força em fronteira de
espaço, evitando patologias de OCR sem quebrar o modelo de dados.

**[a validar]** na Fase 0: avaliar em 200 sentenças anotadas manualmente por taxonomia; meta
de acurácia de fronteira ≥ 95%. Comparar com o `senter` do spaCy num subconjunto, para
quantificar o que se perde pela escolha do desempenho.

---

## 7. Etapa 6 — Escrita

Um processo escritor por shard, consumindo de uma fila:

```python
PRAGMA journal_mode = OFF;  synchronous = OFF;
PRAGMA cache_size = -262144;  temp_store = MEMORY;  page_size = 8192;

por lote de ~2.000 documentos:
    executemany  INSERT INTO docs      …
    executemany  INSERT INTO doctext   …    # blocos de 256 KB, zlib nível 6
    executemany  INSERT INTO segments  …
    executemany  INSERT INTO fts(rowid, txt) VALUES (?, ?)
    atualiza vocab/vocab_forma em dicionário na memória
    COMMIT
```

**`vocab` em memória durante a construção**, gravado ao final. Um `UPDATE` por token seria
proibitivo; um `dict` Python com ~10⁷ entradas ocupa ~1–2 GB — dentro do orçamento se apenas
um escritor grande estiver ativo. Salvaguarda: ao ultrapassar N entradas, despeja
parcialmente em tabela temporária e agrega no final.

**Vazão medida: 33,7 MB de texto/s** em escala pequena
([01 §6.2](01-analise-do-corpus.md#62-indexação-fts5)). Em escala real, a degradação de
B-tree e o I/O de disco devem reduzir isso em 5–15× → **estimativa de 1,5–4 h** para o
corpus completo, com os 9 escritores em paralelo.

### Ordem de execução

Shards grandes primeiro (`leg`, `wik-pt`, `dat-ptbr`), pequenos ao final. Os pequenos
preenchem lacunas de I/O na cauda, encurtando o tempo de parede total.

---

## 8. Etapa 7 — Finalização

Por shard, após a última inserção:

```sql
INSERT INTO fts(fts) VALUES('merge', -16);   -- consolida os b-trees do FTS5
PRAGMA optimize;
ANALYZE;
VACUUM;
```

Depois: construção de `vocab_rev` (inversão de cada termo de `vocab` — operação de segundos)
e escrita do `manifesto.json`.

`VACUUM` exige espaço temporário equivalente ao tamanho do banco. Para `leg` (~3,5 GB
estimados), são ~7 GB transitórios — confortável nos 99 GB livres, mas o verificador de
espaço deve considerá-lo.

---

## 9. Tratamento de erros

| Situação | Conduta |
|---|---|
| XML malformado | Registra `(arquivo, ord)` e o erro; **continua o arquivo**; conta no manifesto |
| `<TEI>` sem texto | Indexa metadados, `n_segs=0`; incrementa `docs_vazios` |
| Metadado ausente | `NULL`; conta em `cobertura_meta` |
| `carolina_id` duplicado | Mantém o primeiro; registra aviso |
| Documento > 20 MB | Processa em fatias; registra aviso |
| Falha de escritor | Marca o shard como incompleto no manifesto; consultas **avisam** |
| Disco cheio | Aborta com mensagem clara; shards concluídos permanecem válidos |

**Nenhum erro é silencioso.** Ao final, o resumo é impresso *e* gravado; um índice construído
com 5.000 falhas de parsing precisa declará-lo, sob pena de produzir contagens erradas que
ninguém consegue explicar depois.

---

## 10. Orçamento de tempo **[estimado]**

| Etapa | 1 núcleo | 4 processos |
|---|---:|---:|
| Varredura + checksums | 2 min | 2 min |
| Passo 1 — parsing p/ vocabulário (se a rejunção for necessária) | 7 min | ~3 min |
| Passo 2 — parsing + normalização + segmentação | 25–40 min | **8–12 min** |
| Escrita FTS5 + tabelas | 1,5–4 h | **35 min – 2 h** (9 escritores) |
| Finalização (merge, VACUUM, vocab_rev) | 20–40 min | 20–40 min |
| **Total** | | **~1,5 – 3,5 h** |

Para `pub` + `soc` + `uni` (215 MB — o alvo da Fase 0): **< 5 min**, o que permite iterar
sobre segmentador e normalizador várias vezes por hora.

---

## 11. Validação pós-construção

`csearch validar --profundo` executa:

| Verificação | Critério |
|---|---|
| Contagem de documentos vs. `README.md` do corpus | divergência < 1% |
| `n_tokens` (nosso) vs. `tei_tokens` (declarado) | correlação > 0,95; divergências agregadas reportadas |
| Amostra de 100 sentenças: deslocamentos → texto | fatia corresponde ao esperado |
| Ida e volta pelo índice | 1.000 termos amostrados de `vocab` retornam ≥ 1 ocorrência no FTS5 |
| Fronteiras de sentença | ≥ 95% de acerto em amostra anotada manualmente |
| **Regressão do `<p>`-como-linha** | a frase `"atribuídos à União por tratados internacionais"` **tem que** ser encontrada em `leg` |
| Integridade de `sha256` | manifesto vs. `checksum.sha256` do corpus |

A penúltima é o teste de regressão mais importante do projeto. Ela falha exatamente se
alguém, no futuro, "simplificar" o pipeline voltando a indexar por `<p>` — o defeito que
mais custaria caro, porque não produz erro, apenas resultados silenciosamente incompletos.

---

**Anterior:** [04 — Linguagem de consulta](04-linguagem-de-consulta.md) · **Próximo:** [06 — Análise linguística](06-analise-linguistica.md)
