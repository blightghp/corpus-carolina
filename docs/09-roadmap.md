# 09 — Roadmap

## Princípio

**Cada fase termina com algo utilizável.** Não há fase que exista apenas para preparar a
seguinte. Se o projeto parar na Fase 2, o pesquisador já terá uma ferramenta que responde
perguntas reais — o que importa quando o cronograma é o de um mestrado, não o de um produto.

As estimativas assumem trabalho em tempo parcial e são de esforço, não de calendário.

---

## Fase 0 — Prova de conceito e validação de decisões

**Objetivo:** fechar os quatro riscos críticos ([08](08-riscos-e-desempenho.md#3-registro-de-riscos))
antes de investir em escala.
**Escopo:** `pub` + `soc` + `uni` — 215 MB, ~35 mil documentos. Indexação em **< 5 min**,
permitindo várias iterações por hora.
**Esforço:** 2–3 dias.

### Entregáveis

1. Pipeline mínimo ponta a ponta: TEI → normalização → segmentação → SQLite/FTS5 → KWIC.
2. CLI com dois comandos: `indexar` e `buscar`.
3. **Relatório de validação** — o produto mais importante desta fase.

### Perguntas que a fase precisa responder

| # | Questão | Decisão que destrava |
|---|---|---|
| 1 | Acurácia do segmentador — 200 sentenças por taxonomia, anotadas à mão | [ADR-02](07-decisoes-adr.md#adr-02); meta ≥ 95% |
| 2 | `tokenchars '-'`: quantas ocorrências cada política encontra/perde | [ADR-05](07-decisoes-adr.md#adr-05) |
| 3 | Pico de RSS ao indexar o maior documento de `leg` | [R-04](08-riscos-e-desempenho.md#r-04--estouro-de-memória-durante-a-construção--a) |
| 4 | Existe hifenização de quebra de linha em `leg`? | regra de rejunção ([05 §5.2](05-pipeline-de-indexacao.md#52-rejunção-de-hífen-a-validar)) |
| 5 | Incidência de ruído recorrente (cabeçalho/rodapé) em `leg` | remoção de ruído: ligar ou não |
| 6 | Cobertura real de `autor`, `url`, `ano` por shard | avisos de [06 §9](06-analise-linguistica.md#9-diagnósticos-e-honestidade-metodológica) |
| 7 | Formatos observados do campo `date` | normalizador de `ano` |
| 8 | Caracteres/sentença reais → nº de sentenças do corpus | dimensionamento ([03 §4](03-modelo-de-dados.md#4-dimensionamento-estimado)) |
| 9 | Fração real texto/XML | dimensionamento |
| 10 | `zlib` níveis 1/6/9: tempo × tamanho | parâmetro de `doctext` |

> Um documento de `leg` deve ser incluído na amostra desta fase mesmo com o shard fora do
> escopo — as questões 3, 4 e 5 dependem dele.

### Critério de saída

Todas as 10 questões respondidas com número; nenhuma decisão de ADR pendente; KWIC correto
sobre `pub`.

---

## Fase 1 — Índice completo

**Objetivo:** os 9 shards construídos, consultáveis e verificados.
**Esforço:** 1 semana (+ 1,5–3,5 h de máquina para a construção).

### Entregáveis

1. `csearch indexar` com paralelismo (4 processos, 9 escritores) e incrementalidade por `sha256`.
2. Extração completa dos ~20 campos de metadados; `taxonomia.json` com as 109 categorias.
3. `manifesto.json` com contagens, erros, cobertura e tempos.
4. `csearch validar` e `csearch info`.
5. Filtros de metadados na busca; KWIC com proveniência; exportação CSV/TSV/JSONL.
6. `vocab`, `vocab_forma`, `vocab_rev`.

### Ordem recomendada

Construir **`jud` primeiro** (1,1 GB, 37 arquivos): grande o bastante para expor problemas de
escala, pequeno o bastante para reconstruir em ~15 min. Só depois `leg` e `wik-pt`.

### Critério de saída

- Todos os testes de integridade passam ([08 §5](08-riscos-e-desempenho.md#5-estratégia-de-validação));
- contagem de documentos dentro de 1% do `README.md` do corpus;
- teste de regressão do `<p>`-como-linha passa em `leg`;
- p95 de consulta ancorada < 2 s.

**Neste ponto o sistema já é útil**: busca por forma, filtro por gênero, KWIC com citação e
exportação — a maior parte do trabalho diário de corpus.

---

## Fase 2 — Linguagem de consulta

**Objetivo:** sair da busca por forma para a busca por padrão.
**Esforço:** 1 semana.

### Entregáveis

1. Lexer + parser CQL-lite (descida recursiva, sem dependências).
2. Planejador com derivação de âncora por menor `df` e estimativa de custo.
3. Verificador (autômato sobre tokens) com sensibilidade a acento e caixa.
4. Sequências, lacunas `[]{n,m}`, alternativas, regex por token, `<s>`.
5. Aviso de consulta sem âncora + `--modo-varredura` ([ADR-09](07-decisoes-adr.md#adr-09)).
6. Resolução de sufixos via `vocab_rev`.
7. Mensagens de erro de parser legíveis para quem não programa.

### Critério de saída

Todos os exemplos de [04 §3](04-linguagem-de-consulta.md#3-exemplos-para-sintaxe-do-português-brasileiro)
executam e retornam resultados plausíveis — exceto os que dependem de POS (Fase 3).

**Neste ponto a persona primária está atendida** para tudo que não exige anotação.

---

## Fase 3 — Camada linguística

**Objetivo:** POS, lema e morfologia — o requisito "mesmo não sendo anotado".
**Esforço:** 1 semana.

### Entregáveis

1. Anotador spaCy sob demanda com `anot_cache`.
2. **Alinhamento de tokenização** entre o nosso tokenizador e o do spaCy
   ([06 §6](06-analise-linguistica.md#alinhamento-de-tokenização-️)) — a parte tecnicamente
   mais delicada da fase.
3. Atributos `pos`, `lema`, `morf` na linguagem de consulta.
4. `csearch anotar --shards pub,soc,uni` (pré-anotação, ~10 min).
5. Avisos de custo antes de anotar grandes volumes.

### Critério de saída

- `[pos="VERB"] [palavra="se"]` funciona em qualquer shard;
- `disse-me` é reconhecido como VERB pelo alinhamento;
- consulta puramente por POS funciona nos shards pré-anotados;
- segunda execução da mesma consulta é ≥ 10× mais rápida (cache).

---

## Fase 4 — Análise quantitativa

**Objetivo:** transformar ocorrências em evidência publicável.
**Esforço:** 1 semana.

### Entregáveis

1. `csearch freq` com normalização por milhão e agregação por 11 eixos.
2. Métricas de dispersão (DP, *range*) e alertas de concentração.
3. `csearch colocar` com MI, MI³, escore-t, LL e log-Dice.
4. `csearch ngramas` e `csearch keyness`.
5. Amostragem aleatória reprodutível, com estratificação e planilha de anotação.
6. *Query cards* + `csearch repetir` com conferência de divergências.
7. `para_dataframe()` na API Python.

### Critério de saída

O fluxo completo de [06 §10](06-analise-linguistica.md#10-fluxo-completo-de-um-estudo) executa
de ponta a ponta, e `csearch repetir` detecta divergência quando o índice muda.

**Neste ponto o sistema cobre todos os objetivos declarados em [00](00-visao-geral.md).**

---

## Fase 5 — Interface e distribuição *(opcional)*

**Objetivo:** abrir o sistema para quem não usa terminal.
**Esforço:** 1–2 semanas.

### Entregáveis

1. Interface web local (FastAPI + HTMX, ou Streamlit) — formulário de consulta, KWIC
   ordenável por clique, gráficos de distribuição, exportação.
2. `pyproject.toml`, instalação por `pip install -e .`, entry point `csearch`.
3. Documentação de usuário em português, com receituário por tipo de pergunta sintática.
4. Empacotamento do índice para compartilhamento com o laboratório (shards individuais,
   com nota de licença — as licenças do Carolina são múltiplas e devem ser observadas).

### Nota

Só faz sentido se houver demanda real de colegas. Um sintaticista que trabalha sozinho é bem
servido pelo CLI.

---

## Fase 6 — Extensões *(especulativo)*

Ideias registradas, sem compromisso, ordenadas por relação valor/custo:

| Ideia | Valor | Custo |
|---|---|---|
| Pré-anotação POS do corpus completo (~5 h em 4 processos) | consultas por POS sem âncora, em qualquer shard | 5 h + ~15 GB |
| Perfil de colocados por lema (estilo *word sketch*), a partir de janelas | resumo distribucional por verbo | médio |
| Detecção de duplicatas via `originality` + *shingling* | contagens de frequência mais defensáveis | médio |
| Adaptador para outros corpora (NURC, C-ORAL-BRASIL) | comparação entre corpora | alto |
| Análise de dependências sob demanda (spaCy `parser` só sobre resultados) | consultas sintáticas de verdade, sem anotar tudo | médio — **candidato natural à Fase 6** |
| Exportação para formato CWB/vertical | interoperabilidade com CQPweb | médio |

A última linha da tabela merece destaque: aplicar o `parser` do spaCy (14.865 tokens/s
**[medido]**) apenas às sentenças recuperadas estende o princípio de
[ADR-07](07-decisoes-adr.md#adr-07) da morfologia para a sintaxe — permitindo consultas por
relação de dependência sem pagar as ~27 h de anotação completa. É a evolução mais natural do
sistema para a persona primária.

---

## Cronograma consolidado

```
Fase 0  ██                    2–3 dias    validação das decisões
Fase 1  ███████               1 semana    índice completo + busca por forma  ← já útil
Fase 2  ███████               1 semana    linguagem de consulta              ← persona atendida
Fase 3  ███████               1 semana    POS / lema / morfologia
Fase 4  ███████               1 semana    análise quantitativa               ← objetivos cumpridos
─────────────────────────────────────────────────────────────────────────
Fase 5  ██████████████        1–2 sem.    interface web            (opcional)
Fase 6  ?                     —           extensões                (especulativo)
```

**Núcleo: ~4,5 semanas de esforço** para um sistema que cobre integralmente os objetivos.

---

## Pontos de decisão

| Momento | Decisão | Se der errado |
|---|---|---|
| Fim da Fase 0 | Segmentador atinge 95%? | Ajustar regras; considerar `senter` do spaCy em amostra |
| Fim da Fase 0 | Política de hífen confirmada? | Avaliar segunda coluna FTS (+40% de índice) |
| Fim da Fase 0 | Pico de RSS < 3 GB? | Reduzir para 2 processos; limpar irmãos no elemento-raiz |
| Durante a Fase 1 | `jud` indexa em tempo aceitável? | Ajustar `detail`, `page_size`, tamanho de lote **antes** de rodar `leg` |
| Fim da Fase 1 | Índice cabe em disco? | Construção parcial por shard; `detail=column` |
| Fim da Fase 2 | Consultas sem âncora são frequentes? | Antecipar a pré-anotação da Fase 3 |
| Fim da Fase 4 | Há demanda de colegas? | Decide se a Fase 5 acontece |

---

## Primeiro passo concreto

Ao aprovar este plano, o trabalho começa por:

1. Criar `carolina_search/` com `config.py` — incluindo a **verificação anti-OneDrive**, que
   é o primeiro código a escrever, porque protege tudo o que vem depois.
2. Implementar `ingestao/leitor_tei.py` e `ingestao/extrator_meta.py`.
3. Construir o corpus-fixture de ~2 MB a partir de `pub` e `soc`, para que a suíte de testes
   rode em segundos desde o primeiro dia.
4. Rodar as 10 medições da Fase 0 e escrever o relatório de validação.

---

**Anterior:** [08 — Riscos e desempenho](08-riscos-e-desempenho.md) · **Índice:** [README](README.md)
