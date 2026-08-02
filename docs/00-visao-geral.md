# 00 — Visão geral

## 1. Objetivo

Construir um **sistema de busca interna em Python** sobre o Corpus Carolina v2.0.1 que
permita a pesquisadores de Linguística de Corpus — em especial **sintaticistas** —
formular consultas sobre formas do português brasileiro e obter, em segundos:

1. **concordâncias KWIC** (palavra-chave em contexto) com janela configurável;
2. **contagens e distribuições** por taxonomia, gênero textual, ano e documento;
3. **metadados completos de proveniência** para cada ocorrência (documento, URL de origem,
   licença, gênero), prontos para citação em dissertação;
4. **exportação** para CSV/TSV/JSONL, para análise estatística posterior em R ou Python.

O sistema deve operar **sem exigir que o corpus seja previamente anotado**, e sem exigir
servidor, GPU ou infraestrutura de nuvem.

## 2. Por que isso é necessário

O corpus é distribuído em 554 arquivos `.xml.gz` (~14 GB descomprimidos). As formas atuais
de acesso são:

| Forma atual | Limitação para pesquisa sintática |
|---|---|
| `datasets.load_dataset("carolina-c4ai/corpus-carolina")` | Itera sequencialmente; sem busca, sem índice; `meta` vem como string XML crua a ser parseada pelo usuário; exige RAM/disco para cache do Arrow |
| `gzip -dc \| grep` | Varre 14 GB a cada consulta; sem metadados; sem KWIC; sem contagem por subcorpus; sem tratamento de acento/caixa |
| Ler o XML manualmente | Inviável em escala |

Uma consulta típica de tese — *"todas as ocorrências de próclise em oração principal
com verbo no futuro"* — hoje é impraticável. O objetivo é torná-la rotineira.

## 3. Personas e casos de uso

### P1 — Sintaticista (persona primária)

Estuda colocação pronominal, ordem de constituintes, regência, concordância. Precisa de:

- busca por **sequências de tokens** com lacunas (`[]{0,3}`) e alternativas;
- busca por **padrão morfológico via regex** (ex.: `\w+-(me|te|lhe|se|nos|vos|lhes)\b` para
  ênclise; `\w+-[a-z]+-(ia|á|ei)\w*` para mesóclise);
- **sensibilidade opcional a acento e caixa** — `está` ≠ `esta`, `Ele` ≠ `ele` importam;
- **filtragem por gênero textual** — a colocação pronominal varia drasticamente entre
  jurídico formal e mídia social;
- **amostragem aleatória reprodutível** de N ocorrências para anotação manual;
- **contagem normalizada** (ocorrências por milhão de palavras) para comparar subcorpora
  de tamanhos muito diferentes.

**Caso de uso canônico:** *"Compare a frequência de ênclise a verbo finito em início de
oração entre `jud` (jurídico) e `soc` (mídia social), normalizada por milhão de palavras,
e me dê 200 ocorrências aleatórias de cada para checagem manual."*

### P2 — Lexicógrafo / pesquisador de fraseologia

Precisa de listas de frequência, n-gramas, colocações com medidas de associação
(MI, escore-t, log-verossimilhança, log-Dice), e de *keyness* contra um subcorpus de
referência.

### P3 — Orientador / banca

Precisa de **reprodutibilidade**: dado o texto de uma consulta em um apêndice de
dissertação, deve ser possível reexecutá-la e obter exatamente os mesmos números,
identificando a versão do corpus e do índice.

## 4. Escopo

### Dentro do escopo

- Indexação completa das 7 taxonomias (9 *shards*, contando as divisões `pt` / `pt-BR`).
- Extração e indexação dos metadados do `teiHeader` (~15 campos por documento).
- Segmentação em sentenças e indexação em nível de sentença.
- Linguagem de consulta "CQL-lite" inspirada em CQP/Sketch Engine.
- Anotação morfossintática **sob demanda** com spaCy `pt_core_news_sm`.
- CLI com `typer` + `rich`; saída legível no terminal e exportável.
- Manifesto de reprodutibilidade e reindexação incremental.

### Fora do escopo (não-objetivos)

| Não-objetivo | Razão |
|---|---|
| Substituir o carregador HuggingFace | Propósitos diferentes: treino de modelos vs. consulta linguística |
| Escrever no corpus / corrigir os arquivos-fonte | O corpus é dado imutável; qualquer normalização vive no índice |
| *Parsing* de dependências de todo o corpus | ~27 h de CPU + dezenas de GB; ver [08](08-riscos-e-desempenho.md) |
| Interface web pública / multiusuário | Ferramenta local de pesquisa; interface web local é opcional (Fase 5) |
| Busca semântica / *embeddings* | Sintaticistas precisam de forma exata, não de similaridade distribucional |
| Suporte a outros corpora | Possível depois via camada de adaptadores; não é meta inicial |

## 5. Requisitos não-funcionais

| Requisito | Meta | Verificação |
|---|---|---|
| **Latência de consulta ancorada** | p95 < 2 s no corpus completo | consulta com literal (ex.: `"que"`) em todos os shards |
| **Latência de consulta em subcorpus** | p95 < 300 ms | consulta restrita a um shard |
| **Tempo de construção do índice** | < 6 h para o corpus completo, em uma execução noturna | medição na Fase 1 |
| **Reconstrução incremental** | só reindexa arquivos com `sha256` alterado | manifesto |
| **Consumo de RAM** | pico < 3 GB por processo | pipeline puramente *streaming* |
| **Tamanho do índice** | < 12 GB total | ver [03](03-modelo-de-dados.md) |
| **Dependências** | apenas stdlib + `spacy`, `typer`, `rich`, `regex` (já instalados) | `pyproject.toml` |
| **Portabilidade** | Windows como plataforma primária; Linux/macOS sem alterações | CI opcional |
| **Reprodutibilidade** | consulta idêntica → resultado idêntico, com identificação de versão | manifesto + *query cards* |

## 6. Critérios de sucesso

O projeto é bem-sucedido se, ao final da Fase 4:

1. Uma consulta por forma simples no corpus completo retorna em **menos de 2 segundos**
   [meta], contra dezenas de minutos hoje.
2. Um sintaticista consegue formular uma consulta de colocação pronominal **sem escrever
   código Python**.
3. Cada linha de concordância exportada carrega identificador de documento, gênero, URL e
   licença — suficiente para citação direta.
4. Uma consulta salva pode ser reexecutada meses depois com resultado idêntico e
   verificável.
5. O índice completo cabe em disco com folga e pode ser **copiado e compartilhado** com o
   laboratório como arquivo único por shard.

## 7. Princípios de projeto

1. **Somente-leitura sobre o corpus.** Nenhuma operação escreve em `corpus/`.
2. **Streaming por padrão.** Nada que dependa de caber na RAM. Documentos de 16 MB existem.
3. **Recall no índice, precisão na verificação.** O índice é tolerante (sem acento, sem
   caixa); a precisão linguística é aplicada depois, em Python.
4. **Honestidade sobre custo.** Consultas caras (sem âncora literal) devem avisar o usuário
   e estimar o tempo, nunca travar silenciosamente.
5. **Proveniência sempre.** Nenhum resultado sem identificação de origem.
6. **Dependências mínimas.** Um pesquisador deve conseguir instalar e rodar sem
   *toolchain* de compilação.
7. **Falha explícita.** Erros de parsing, documentos vazios e metadados ausentes são
   contabilizados e reportados, nunca ignorados em silêncio.

## 8. Nomenclatura proposta

- Pacote Python: `carolina_search`
- CLI: `csearch`
- Diretório de índice (padrão): `%LOCALAPPDATA%\carolina-search\index\` — **fora do OneDrive**
- Formato de consulta salva: `*.consulta.toml` ("*query card*")

---

**Próximo:** [01 — Análise do corpus](01-analise-do-corpus.md)
