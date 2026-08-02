---
annotations_creators:
- no-annotation
language_creators:
- crowdsourced
language:
- pt
license: cc-by-4.0
multilinguality:
- monolingual
size_categories:
- 1B<n<10B
source_datasets:
- original
task_categories:
- fill-mask
- text-generation
task_ids:
- masked-language-modeling
- language-modeling
pretty_name: Carolina
language_bcp47:
- pt-BR
---

# Dataset Card for Corpus Carolina


## Table of Contents
- [Table of Contents](#table-of-contents)
- [Dataset Description](#dataset-description)
  - [Dataset Summary](#dataset-summary)
  - [Supported Tasks](#supported-tasks)
  - [Languages](#languages)
- [Dataset Structure](#dataset-structure)
  - [Data Instances](#data-instances)
  - [Data Fields](#data-fields)
  - [Data Splits](#data-splits)
- [Additional Information](#additional-information)
  - [Dataset Curators](#dataset-curators)
  - [Licensing Information](#licensing-information)
  - [Citation Information](#citation-information)


## Dataset Description

- **Homepage:** [sites.usp.br/corpuscarolina](https://sites.usp.br/corpuscarolina/)
- **Current Version:** 2.0.1 (Bea)
- **Point of Contact:** [LaViHD](mailto:lavihd@usp.br)


### Dataset Summary

Carolina is an Open Corpus for Linguistics and Artificial Intelligence with a
robust volume of texts of varied typology in contemporary Brazilian Portuguese
(1970-). This corpus contains documents and texts extracted from the web
and includes information (metadata) about its provenance and tipology.

The documents are clustered into taxonomies and the corpus can be loaded in complete or taxonomy modes. To load a single taxonomy, it is possible to pass a code as a parameter to the loading script (see the example bellow). Codes are 3-letters string and possible values are:

- `dat` : datasets and other corpora;
- `jud` : judicial branch;
- `leg` : legislative branch;
- `pub` : public domain works;
- `soc` : social media;
- `uni` : university domains;
- `wik` : wikis.

Dataset Vesioning:

The Carolina Corpus is under continuous development resulting in multiple vesions. The current version is v2.0.1, but v2.0, v1.3, v1.2, and v1.1 are also available. You can access diferent vesions of the corpus using the `revision` parameter on `load_dataset`.

Usage Example:

```python
from datasets import load_dataset

# to load all taxonomies
corpus_carolina = load_dataset("carolina-c4ai/corpus-carolina")

# to load social media documents
social_media = load_dataset("carolina-c4ai/corpus-carolina", taxonomy="soc")

# to load previous version
corpus_carolina = load_dataset("carolina-c4ai/corpus-carolina", revision="v1.1")
```

### Supported Tasks

Carolina corpus was compiled for academic purposes,
namely linguistic and computational analysis.


### Languages

Contemporary Brazilian Portuguese (1970-).

## Dataset Structure

Files are stored inside `corpus` folder with a subfolder
for each taxonomy. Every file folows a XML structure
(TEI P5) and contains multiple extracted documents. For
each document, the text and metadata are exposed as
`text` and `meta` features, respectively.

### Data Instances

Every instance have the following structure.

```
{
    "meta": datasets.Value("string"),
    "text": datasets.Value("string")
}
```

| Code | Taxonomy                   | Instances |  Size  |
|:----:|:---------------------------|----------:|-------:|
|      | **Total**                  |   2108999 |  15 GB |
| wik  | Wikis                      |    957501 | 5.3 GB |
| dat  | Datasets and other Corpora |   1074032 | 4.3 GB |
| leg  | Legislative Branch         |      3982 | 4.2 GB |
| jud  | Judicial Branch            |     38187 |   1 GB |
| uni  | University Domains         |     26409 | 162 MB |
| soc  | Social Media               |      8862 |  49 MB |
| pub  | Public Domain Works        |        26 | 4.5 MB |


### Data Fields

- `meta`: a XML string with a TEI conformant `teiHeader` tag. It is exposed as text and needs to be parsed in order to access the actual metada;
- `text`: a string containing the extracted document.

### Data Splits

As a general corpus, Carolina does not have splits. In order to load the dataset, it is used `corpus` as its single split.


## Additional Information


### Dataset Curators

The Corpus Carolina is developed by a multidisciplinary
team of linguists and computer scientists, members of the
Virtual Laboratory of Digital Humanities - LaViHD and the Artificial Intelligence Center of the University of São Paulo - C4AI.


### Licensing Information

Carolina: General Corpus of Contemporary Brazilian Portuguese with Provenance and Typology Information, was compiled for academic purposes, namely linguistic and computational analysis. It is composed of texts assembled in various digital repositories, whose licenses are multiple and therefore should be observed when making use of the corpus. The Carolina headers are licensed under Creative Commons Attribution 4.0 International.


### Citation Information

```
@misc{crespo2023carolina,
      title={Carolina: a General Corpus of Contemporary Brazilian Portuguese with Provenance, Typology and Versioning Information}, 
      author={Maria Clara Ramos Morales Crespo and Maria Lina de Souza Jeannine Rocha and Mariana Lourenço Sturzeneker and Felipe Ribas Serras and Guilherme Lamartine de Mello and Aline Silva Costa and Mayara Feliciano Palma and Renata Morais Mesquita and Raquel de Paula Guets and Mariana Marques da Silva and Marcelo Finger and Maria Clara Paixão de Sousa and Cristiane Namiuti and Vanessa Martins do Monte},
      year={2023},
      eprint={2303.16098},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
```