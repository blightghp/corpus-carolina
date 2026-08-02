# Plano de Arquitetura — Sistema de Busca Interna do Corpus Carolina

**Status:** proposta de arquitetura (documentação apenas — nenhum código implementado)
**Data:** 2026-08-02
**Corpus alvo:** Carolina v2.0.1 "Bea" — 554 arquivos TEI/XML, ~2,1 milhões de documentos
**Contexto:** pesquisa de mestrado em Linguística de Corpus; público-alvo primário são sintaticistas

---

## O problema em uma frase

O Corpus Carolina tem ~14 GB de português brasileiro contemporâneo em TEI/XML comprimido,
**sem anotação linguística**, distribuído em 554 arquivos `.xml.gz`. Hoje, responder a uma
pergunta como *"quantas ocorrências de ênclise em futuro do presente existem no corpus
jurídico?"* exige descomprimir e varrer tudo — dezenas de minutos por consulta, sem
metadados, sem concordância, sem reprodutibilidade.

Este plano descreve um sistema em Python que reduz isso a **milissegundos**, preservando
precisão linguística e rastreabilidade de citação.

---

## A ideia central

> **Não anotar 14 GB. Anotar as 2.000 linhas que você efetivamente recuperou.**

O sistema se organiza em três estágios:

| Estágio | Ferramenta | Escala | Custo |
|---|---|---|---|
| **1. Filtrar** | SQLite FTS5 (índice invertido) | 14 GB → milhares de candidatos | ~ms |
| **2. Verificar** | regex/autômato em Python sobre tokens | milhares → dezenas/centenas | ~ms–s |
| **3. Enriquecer** | spaCy `pt_core_news_sm` sob demanda | só os resultados | ~s |

Isso resolve o requisito *"mesmo não sendo anotado"*: a anotação morfossintática é
calculada **no momento da consulta**, apenas sobre o que foi recuperado. Medido neste
ambiente: anotar 5.000 linhas de concordância leva **~5 s**; anotar o corpus inteiro
levaria **~20 h de CPU**.

---

## Índice dos documentos

| # | Documento | Conteúdo |
|---|---|---|
| 00 | [Visão geral](00-visao-geral.md) | Objetivos, escopo, não-objetivos, personas, critérios de sucesso |
| 01 | [Análise do corpus](01-analise-do-corpus.md) | Levantamento empírico: estrutura TEI, metadados, granularidade, achados críticos |
| 02 | [Arquitetura](02-arquitetura.md) | Camadas, componentes, fluxo de dados, estrutura de pacotes |
| 03 | [Modelo de dados](03-modelo-de-dados.md) | Esquema SQLite, sharding, armazenamento de texto, dimensionamento |
| 04 | [Linguagem de consulta](04-linguagem-de-consulta.md) | CQL-lite: sintaxe, exemplos de sintaxe portuguesa, compilação |
| 05 | [Pipeline de indexação](05-pipeline-de-indexacao.md) | Ingestão, normalização, segmentação, escrita, incrementalidade |
| 06 | [Análise linguística](06-analise-linguistica.md) | KWIC, frequências, colocações, distribuições, exportação |
| 07 | [Decisões de arquitetura (ADRs)](07-decisoes-adr.md) | 12 decisões registradas com alternativas e justificativas |
| 08 | [Riscos e desempenho](08-riscos-e-desempenho.md) | Medições, estimativas, riscos e mitigações |
| 09 | [Roadmap](09-roadmap.md) | Seis fases, entregáveis, critérios de aceite |

**Leitura mínima para decidir:** [00](00-visao-geral.md) → [01](01-analise-do-corpus.md) →
[07](07-decisoes-adr.md) → [09](09-roadmap.md).

---

## Achados que mudaram o desenho

Quatro descobertas da inspeção do corpus (documento [01](01-analise-do-corpus.md)) são
responsáveis pela forma final da arquitetura:

1. **`<p>` no ramo legislativo é uma *linha tipográfica*, não um parágrafo.** Documentos de
   até 16 MB com 366.411 elementos `<p>` de ~47 caracteres cada, quebrando sentenças no
   meio. Indexar por `<p>` faria toda consulta multipalavra falhar silenciosamente em
   5,2 GB do corpus. → [ADR-02](07-decisoes-adr.md#adr-02)

2. **O `teiHeader` é muito mais rico do que a API oficial expõe.** Gênero textual em
   taxonomia de 3 níveis (109 categorias), autor, URL de origem, licença, data original,
   contagem de tokens, índice de originalidade. → [modelo de dados](03-modelo-de-dados.md)

3. **`load_extension` está desabilitado no Python deste ambiente.** Não há como instalar um
   tokenizador FTS5 customizado em C; radicalização/lematização precisa viver na camada de
   aplicação. → [ADR-05](07-decisoes-adr.md#adr-05)

4. **O repositório está dentro do OneDrive.** Um índice SQLite multi-GB em escrita constante
   dentro de pasta sincronizada é receita para corrupção e estouro de cota. O índice deve
   viver fora. → [ADR-08](07-decisoes-adr.md#adr-08)

---

## Ambiente medido

| Recurso | Valor | Implicação |
|---|---|---|
| Python | 3.13.1 | `sqlite3` 3.45.3 com **FTS5 disponível** (verificado) |
| CPU | i5-10300H — 4 núcleos / 8 threads | paralelismo de ingestão limitado a ~4 processos |
| RAM | 7,8 GB | pipeline deve ser 100% *streaming*; nada de carregar documento inteiro sem liberar |
| Disco | 476 GB, **99 GB livres** | índice estimado em ~9 GB cabe, mas com margem a monitorar |
| Já instalado | `spacy` 3.8.14 + `pt_core_news_sm`, `pandas`, `pyarrow`, `numpy`, `regex`, `rich`, `typer`, `tqdm` | quase nenhuma dependência nova é necessária |
| **Ausente** | `lxml`, `duckdb`, `zstandard` | usar `xml.etree` da stdlib (medido: 35 MB/s) e `zlib` da stdlib |

---

## O que este plano *não* propõe

- Não substitui o carregador oficial `corpus-carolina.py` (HuggingFace `datasets`) — os dois
  coexistem, com propósitos distintos.
- Não modifica nem reescreve os arquivos do corpus. O sistema é **estritamente somente-leitura**
  sobre `corpus/`.
- Não faz *parsing* sintático de dependências de todo o corpus (inviável no hardware
  disponível — ver [08](08-riscos-e-desempenho.md)).
- Não é um serviço web público. É uma ferramenta local, com opção de interface web local
  na Fase 5.

---

## Convenções destes documentos

- Números marcados **[medido]** vêm de execução real neste ambiente em 2026-08-02.
- Números marcados **[estimado]** são extrapolações a partir de medições, com a base explicitada.
- Pontos marcados **[a validar]** são hipóteses que a Fase 0 deve confirmar antes de escalar.
