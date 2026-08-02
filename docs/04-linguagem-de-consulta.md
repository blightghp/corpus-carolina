# 04 — Linguagem de consulta (CQL-lite)

## 1. Por que uma linguagem, e não só uma caixa de busca

Um sintaticista raramente procura *uma palavra*. Procura **configurações**: um clítico após
verbo finito, um sujeito posposto, uma preposição regendo oração completiva. Uma caixa de
busca simples não expressa isso; escrever Python para cada pergunta é lento e não
reproduzível.

A área já tem um padrão de fato — **CQP** (IMS Corpus Workbench), usado no Sketch Engine,
no CQPweb e no CoRP. A proposta é implementar um **subconjunto compatível**, com apelidos em
português, para que quem já conhece CQP não precise reaprender, e quem não conhece encontre
palavras familiares.

Princípio de projeto: **o caso simples tem que ser simples.** Buscar `casa` deve ser digitar
`casa`. A complexidade só aparece quando a pergunta é complexa.

---

## 2. Sintaxe

### 2.1 Níveis de uso

```
Nível 1 — forma simples
    casa
    "de que"                       frase exata
    casa*                          prefixo

Nível 2 — atributos
    [palavra="casa"]
    [palavra="cas.*"]              regex sobre o token
    [lema="casar"]                 lema (spaCy, sob demanda)
    [pos="VERB"]                   classe UPOS (spaCy, sob demanda)
    [morf="Tense=Fut"]             traços morfológicos

Nível 3 — sequências e lacunas
    [pos="VERB"] [palavra="se"]
    [palavra="que"] []{0,3} [pos="VERB"]
    ([palavra="o"] | [palavra="a"]) [pos="NOUN"]

Nível 4 — fronteiras e filtros
    <s> [pos="VERB"]                       verbo em início de sentença
    [palavra="\w+-se"] within <s>
    … :: taxonomia=jud & ano>=1990
```

### 2.2 Atributos disponíveis

| Atributo | Apelido | Origem | Custo |
|---|---|---|---|
| `palavra` | `word`, `p` | índice | **barato** — resolvido no FTS5 |
| `pos` | `classe` | spaCy `morphologizer` | médio — só sobre candidatos |
| `lema` | `lemma`, `l` | spaCy `lemmatizer` | médio |
| `morf` | `feats`, `m` | spaCy (UD *features*) | médio |
| `forma` | — | `vocab_forma` | barato — grafia de superfície exata, com acento e caixa |

> `palavra` casa contra a **forma de superfície**, respeitando as opções
> `--sensivel-acento` / `--sensivel-caixa`. `forma` casa sempre de modo estrito, sem
> dobramento. Distinção deliberada: `[palavra="esta"]` com `--sensivel-acento` **não** casa
> `está`; `[forma="está"]` casa exatamente `está` e nada mais.

### 2.3 Operadores

| Operador | Significado | Exemplo |
|---|---|---|
| `"…"` | literal (frase, se contiver espaço) | `"por causa de"` |
| `=` / `!=` | casa / não casa | `[pos!="PUNCT"]` |
| `|` | alternativa | `[palavra="me"|"te"|"lhe"]` |
| `&` | conjunção de atributos no mesmo token | `[pos="VERB" & morf="Tense=Fut"]` |
| `[]` | qualquer token | `[] [palavra="que"]` |
| `{n,m}` | repetição | `[]{0,3}`, `[pos="ADJ"]{1,}` |
| `( … )` | agrupamento | `([pos="DET"] [pos="NOUN"])` |
| `<s>` / `</s>` | fronteira de sentença | `<s> [pos="PRON"]` |
| `within <s>` | confina a sequência à sentença | padrão implícito |
| `::` | separa padrão de filtro de metadados | `… :: ano>=2000` |

**Toda consulta é confinada à sentença por padrão.** É a decisão linguisticamente correta —
uma sequência que atravessa fronteira de sentença quase nunca é o objeto de estudo — e
alinha-se ao modelo de dados ([03](03-modelo-de-dados.md)), em que a sentença é a unidade de
indexação.

### 2.4 Filtros de metadados

Após `::`, ou via `--filtro`:

```
taxonomia = jud
taxonomia in (jud, leg)
genero = NEWS_JOU_W
genero_l1 = TRANSCRIBED_SPEECH        -- todo o ramo da fala transcrita
genero_l2 != JURIDICAL_W
lang = pt-BR
ano >= 1990 & ano < 2000
autor ~ "Machado"                     -- contém, sem acento e sem caixa
url ~ "gov.br"
n_tokens > 500
originalidade >= 80                   -- exclui material majoritariamente duplicado
```

Combináveis com `&`, `|`, `!` e parênteses. Compilam diretamente para `WHERE` sobre `docs`,
aproveitando os índices declarados.

---

## 3. Exemplos para sintaxe do português brasileiro

Os casos abaixo são a validação real do desenho: se a linguagem não os expressa
confortavelmente, ela falhou.

### 3.1 Colocação pronominal

```bash
# Ênclise — clítico posposto, ligado por hífen
[palavra="\w+-(me|te|lhe|se|nos|vos|lhes)"]

# Mesóclise — clítico infixado em futuro/condicional
[palavra="\w+-(me|te|lhe|se|nos|vos|lhes)-(ei|ás|á|emos|eis|ão|ia|ias|íamos|iam)"]

# Próclise após advérbio de negação
[palavra="não"|"nunca"|"jamais"] [palavra="me"|"te"|"se"|"lhe"|"nos"|"lhes"] [pos="VERB"]

# Próclise em início absoluto de sentença (estigmatizada na norma, corrente no PB falado)
<s> [palavra="me"|"te"|"se"|"lhe"] [pos="VERB"]

# Contraste de modalidade sobre o mesmo padrão
[palavra="\w+-se"] :: genero_l1=WRITTEN_TEXT
[palavra="\w+-se"] :: genero_l1=TRANSCRIBED_SPEECH
```

> A quarta consulta só funciona porque o índice preserva o hífen
> ([ADR-05](07-decisoes-adr.md#adr-05)); a quinta e a sexta só funcionam porque o gênero
> textual do `teiHeader` foi extraído para coluna ([01 §4](01-analise-do-corpus.md#4-metadados-disponíveis-no-teiheader)).

### 3.2 Ordem de constituintes

```bash
# Sujeito posposto a verbo inacusativo
<s> [lema="chegar"|"surgir"|"aparecer"|"existir"] [pos="DET"]{0,1} [pos="NOUN"]

# Objeto direto anteposto (topicalização)
<s> [pos="DET"] [pos="NOUN"] [pos="PRON"] [pos="VERB"]

# Adjetivo antes vs. depois do nome
[pos="ADJ"] [pos="NOUN"]
[pos="NOUN"] [pos="ADJ"]
```

### 3.3 Complementação e regência

```bash
# "de que" completivo vs. "de que" relativo — desambiguado por contexto à esquerda
[pos="NOUN"] [palavra="de"] [palavra="que"]
[pos="VERB"] [palavra="de"] [palavra="que"]

# Queísmo (supressão da preposição)
[lema="gostar"|"precisar"|"lembrar"] [palavra="que"]

# Dequeísmo (preposição não licenciada)
[lema="dizer"|"achar"|"pensar"] [palavra="de"] [palavra="que"]
```

### 3.4 Concordância variável

```bash
# Sintagma nominal plural com marcação apenas no determinante
[palavra="os"|"as"] [palavra=".*[^s]"] [pos="NOUN"]

# "a gente" com verbo em 1ª pessoa do plural
[palavra="a"] [palavra="gente"] [pos="VERB" & morf="Person=1|Number=Plur"]
```

### 3.5 Construções com "que"

```bash
# "que" a até 3 tokens de um verbo
[palavra="que"] []{0,3} [pos="VERB"]

# Relativa cortadora (sem preposição retomada)
[pos="NOUN"] [palavra="que"] [pos="PRON"] [pos="VERB"]
```

---

## 4. Compilação: do padrão ao plano de execução

```
    texto da consulta
          │
       ┌──▼──┐
       │lexer│  tokens: LITERAL, COLCHETE, ATRIBUTO, REGEX, QUANT, ALT, LIMITE, FILTRO
       └──┬──┘
       ┌──▼───┐
       │parser│  descida recursiva → AST
       └──┬───┘
          │   Seq[ Tok(attr,regex), Lacuna(0,3), Tok(...) ]  +  FiltroMeta
       ┌──▼────────┐
       │planejador │
       └──┬────────┘
          ├─▶ (a) predicado SQL sobre docs
          ├─▶ (b) expressão MATCH do FTS5  ← derivada dos literais/regex ancoráveis
          ├─▶ (c) autômato de verificação
          └─▶ (d) estimativa de custo → aviso ou recusa
```

### 4.1 Derivação da âncora — o coração do planejador

O planejador percorre o AST buscando o que puder virar um termo do FTS5:

| Elemento do padrão | Âncora derivada | Seletividade |
|---|---|---|
| `[palavra="casa"]` | `casa` | alta |
| `"de que"` | `"de que"` (frase) | média |
| `[palavra="cas.*"]` | `cas*` (prefixo nativo do FTS5) | média |
| `[palavra="\w+-lhe"]` | via `vocab_rev`: `*-lhe` → disjunção de formas reais | alta |
| `[palavra="a"\|"o"]` | `a OR o` | **péssima** (palavras funcionais) |
| `[pos="VERB"]` | nenhuma | — |
| `[]` | nenhuma | — |

Regras:

1. Se houver ≥ 1 âncora, escolhe-se a de **menor `df`** (consultado em `vocab` — grátis). É a
   otimização mais rentável do sistema: em `[palavra="que"] []{0,3} [lema="proferir"]`,
   ancorar por `proferir` em vez de `que` reduz os candidatos em várias ordens de grandeza.
2. Havendo múltiplas âncoras obrigatórias em sequência, combinam-se com `NEAR(a b, k)`,
   onde `k` deriva das lacunas — usando um operador nativo e barato do FTS5 **[medido: 0,4 ms]**.
3. Se **não houver âncora** (ex.: só `[pos=…]`), o planejador exige uma decisão explícita:

```
⚠  A consulta não tem âncora lexical.
   Seria necessário varrer 66.000.000 de sentenças (~8 GB).
   Estimativa: 25–40 min com anotação morfossintática.

   Opções:
     1) restringir por metadados     :: taxonomia=pub
     2) restringir por shard          --shards soc,uni,pub
     3) adicionar uma âncora lexical  [pos="VERB"] [palavra="se"]
     4) executar mesmo assim          --modo-varredura

   Nenhuma ação tomada.
```

Isso é engenharia honesta: em vez de travar por 40 minutos sem explicação, o sistema informa
o custo e devolve o controle. Um pesquisador que aceita esperar 40 min digita
`--modo-varredura`; os outros — a maioria — descobrem que restringir a `pub` responde à
pergunta em 3 segundos.

### 4.2 Verificação

Sobre cada sentença candidata:

1. Recupera-se o texto por deslocamentos (`doctext` → fatia).
2. Tokeniza-se com o **mesmo tokenizador usado na indexação** — requisito absoluto de
   consistência; divergência aqui produz falsos negativos silenciosos.
3. Se o padrão exige `pos`/`lema`/`morf`, consulta-se `anot_cache`; havendo falha,
   anota-se com spaCy e grava-se no cache.
4. Casa-se o AST contra a sequência de tokens (autômato guloso com retrocesso; padrões
   são curtos, o custo é desprezível).
5. Devolve-se `(seg_id, tok_ini, tok_fim)` por ocorrência — **incluindo múltiplas
   ocorrências na mesma sentença**, que precisam ser contadas separadamente.

### 4.3 Sensibilidade a acento e caixa

| Opção | Padrão | Efeito |
|---|---|---|
| `--sensivel-acento` | **ligado** | `[palavra="esta"]` não casa `está` |
| `--sensivel-caixa` | desligado | `[palavra="ele"]` casa `Ele` e `ele` |

Ambas atuam **apenas na verificação** — o índice permanece sempre dobrado. Consequência: são
gratuitas, alternáveis por consulta, e não exigem reconstruir nada.

O padrão de acento **ligado** é deliberado e contrário ao de motores de busca genéricos:
para linguística do português, `e`/`é`, `esta`/`está`, `pais`/`país`, `secretaria`/`secretária`
são pares distintos, e confundi-los invalida contagens. Quem quiser tolerância desliga
explicitamente.

---

## 5. Interface de linha de comando

```bash
# Construção do índice
csearch indexar                          # tudo
csearch indexar --shards pub,soc,uni     # só os pequenos (Fase 0)
csearch indexar --forcar                 # ignora incrementalidade
csearch validar                          # confere manifesto x checksums do corpus

# Busca
csearch buscar 'PADRÃO' [opções]
  --filtro TEXTO           filtro de metadados
  --shards LISTA           padrão: todos
  --kwic N                 janela em tokens (padrão: 7)
  --contexto-sentenca      inclui a sentença anterior e a seguinte
  --sensivel-acento/-nao   padrão: sensível
  --sensivel-caixa/-nao    padrão: insensível
  --limite N               máximo de linhas exibidas (padrão: 50)
  --amostra N --semente S  amostra aleatória reprodutível
  --ordenar esq|dir|freq|aleatorio
  --exportar ARQ.csv|.tsv|.jsonl
  --salvar ARQ.consulta.toml
  --modo-varredura         aceita consulta sem âncora

# Análise
csearch freq 'PADRÃO' --por genero|taxonomia|ano|doc --por-milhao
csearch colocar 'PADRÃO' --janela 5 --medida ll|mi|t|dice --min-freq 5
csearch ngramas 3 --shards soc --top 100
csearch keyness --alvo jud --referencia wik --medida ll
csearch distribuicao 'PADRÃO' --por genero_l1

# Utilidades
csearch info                       # shards, tamanhos, datas, cobertura de metadados
csearch generos                    # árvore das 109 categorias com contagens
csearch formas 'sentenca'          # grafias de superfície reais sob a chave dobrada
csearch repetir ARQ.consulta.toml  # reexecuta e confere os números
```

### Exemplo de saída KWIC

```
csearch buscar '[palavra="\w+-lhe"]' --filtro 'taxonomia=jud' --kwic 6 --limite 3

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ contexto esquerdo           ┃ chave     ┃ contexto direito            ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ o relator , em seu voto ,   │ coube-lhe │ apreciar a matéria de fundo │
│ a decisão recorrida negou   │ dando-lhe │ provimento parcial ao apelo │
│ o magistrado , ao sentenciar│ impôs-lhe │ a pena de reclusão em regime│
└─────────────────────────────┴───────────┴─────────────────────────────┘

3 de 14.882 ocorrências · 9.431 documentos · 77,83 por milhão de palavras · 412 ms

[1] JUD000004821a · APPELLATE_DECISION_RECORDS_JUR_W · WRITTEN_TEXT · CC BY 4.0
    https://…
```

Cada linha é rastreável até documento, gênero, licença e URL — o requisito de citação da
persona P3, satisfeito por construção e não como recurso à parte.

---

## 6. API Python

Para quem prefere script a CLI (P2, análises estatísticas):

```python
from carolina_search import Corpus

c = Corpus()                                   # descobre o índice; valida localização

r = c.buscar(r'[palavra="\w+-(me|te|lhe|se)"]',
             filtro='taxonomia=jud & genero_l1=WRITTEN_TEXT',
             kwic=8)

print(r.total, r.por_milhao)
df = r.para_dataframe()                        # pandas, já instalado
df.to_csv('enclise.csv', index=False, encoding='utf-8-sig')

col = c.colocacoes(r, janela=5, medida='ll', min_freq=5)
dist = c.distribuicao(r, por='genero_l2', normalizar=True)

for oc in r.amostra(200, semente=20260802):
    print(oc.esquerdo, '|', oc.chave, '|', oc.direito, '|', oc.doc.url)
```

`para_dataframe()` devolve `pandas.DataFrame` (versão 3.0.5 já instalada), fechando o ciclo
com o ferramental estatístico usual da área.

---

## 7. Fora do escopo da linguagem (não-objetivos)

| Recurso CQP | Situação |
|---|---|
| Relações de dependência (`>`, `<`) | Exigiria *parsing* de todo o corpus (~27 h + dezenas de GB). Ver [08](08-riscos-e-desempenho.md) |
| Alinhamento paralelo | Corpus monolíngue |
| Subcorpora nomeados persistentes | Fase 5, se houver demanda; o filtro de metadados já cobre o caso comum |
| Estruturas aninhadas (`<p>`, `<div>`) | A fragmentação de `<p>` em `leg` torna a marcação de parágrafo pouco confiável ([01 §3](01-analise-do-corpus.md#3-achado-crítico----p-no-ramo-legislativo-é-uma-linha-não-um-parágrafo)); só `<s>` é exposto |

---

**Anterior:** [03 — Modelo de dados](03-modelo-de-dados.md) · **Próximo:** [05 — Pipeline de indexação](05-pipeline-de-indexacao.md)
