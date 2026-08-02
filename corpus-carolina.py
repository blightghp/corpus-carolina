# Copyright 2020 The HuggingFace Datasets Authors and the current dataset
# script contributor.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Carolina Corpus"""

from collections import defaultdict
from lxml import etree
import os
import datasets
import gzip


logger = datasets.logging.get_logger(__name__)


_HOMEPAGE = "https://sites.usp.br/corpuscarolina/"


_DESCRIPTION = """
Carolina is an Open Corpus for Linguistics and Artificial Intelligence with a
robust volume of texts of varied typology in contemporary Brazilian Portuguese
(1970-).
"""


_CITATION = r"""
@misc{crespo2023carolina,
    title={Carolina: a General Corpus of Contemporary Brazilian Portuguese with Provenance, Typology and Versioning Information},
    author={Maria Clara Ramos Morales Crespo and
            Maria Lina de Souza Jeannine Rocha and
            Mariana Lourenço Sturzeneker and
            Felipe Ribas Serras and
            Guilherme Lamartine de Mello and
            Aline Silva Costa and
            Mayara Feliciano Palma and
            Renata Morais Mesquita and
            Raquel de Paula Guets and
            Mariana Marques da Silva and
            Marcelo Finger and
            Maria Clara Paixão de Sousa and
            Cristiane Namiuti and
            Vanessa Martins do Monte},
    year={2023},
    eprint={2303.16098},
    archivePrefix={arXiv},
    primaryClass={cs.CL}
}
"""


_LICENSE = """
Carolina: General Corpus of Contemporary Brazilian Portuguese with Provenance and Typology Information, 
was compiled for academic purposes, namely linguistic and computational analysis. 
It is composed of texts assembled in various digital repositories, 
whose licenses are multiple and therefore should be observed when making use of the corpus. 
The Carolina headers are licensed under Creative Commons Attribution 4.0 International.
"""


def _taxonomies():
    """Creates a map between taxonomy code and name

    Returns
    -------
    dict
        The dictionary of codes and names.
    """
    return dict(
        dat="datasets_and_other_corpora",
        jud="judicial_branch",
        leg="legislative_branch",
        pub="public_domain_works",
        soc="social_media",
        uni="university_domains",
        wik="wikis",
    )


_VERSION = "2.0.1"
_CORPUS_URL = "corpus/{tax}/"
_CHECKSUM_FNAME = _CORPUS_URL + "checksum.sha256"


class CarolinaConfig(datasets.BuilderConfig):
    """Carolina Configuration."""
    def __init__(self, taxonomy: str = None, **kwargs):
        """BuilderConfig for Carolina

        Parameters
        ----------
        taxonomy : str
            The taxonomy code (3 letters). The code defines the taxonomy
            to download. If `None`, all taxonomies will be downloaded.
        **kwargs
            Arguments passed to super.
        """
        # validates taxonomy
        if taxonomy is None:
            taxonomy = "all"
        elif taxonomy != "all" and taxonomy not in _taxonomies():
            raise ValueError(f"Invalid taxonomy: {taxonomy}")

        # custom name and description
        description = "Carolina corpus."
        if taxonomy == "all":
            name = "carolina"
            description += " Using all taxonomies."
        else:
            name = _taxonomies()[taxonomy]
            description += f" Using taxonomy {taxonomy}"

        super(CarolinaConfig, self).__init__(
            name=name, description=description, **kwargs)

        # Carolina attributes
        self.taxonomy = taxonomy
        self.version = datasets.Version(_VERSION)


class Carolina(datasets.GeneratorBasedBuilder):
    """Carolina Downloader and Builder"""

    BUILDER_CONFIG_CLASS = CarolinaConfig

    def _info(self):
        features = datasets.Features({
            "meta": datasets.Value("string"),
            "text": datasets.Value("string")
        })

        return datasets.DatasetInfo(
            description=_DESCRIPTION,
            supervised_keys=None,
            homepage=_HOMEPAGE,
            citation=_CITATION,
            features=features,
            license=_LICENSE
        )

    def _split_generators(self, dl_manager):
        # list taxonomies to download
        if self.config.taxonomy == "all":
            taxonomies = _taxonomies().values()
        else:
            taxonomies = [_taxonomies()[self.config.taxonomy]]

        # download checksum files
        checksum_urls = {t: _CHECKSUM_FNAME.format(tax=t) for t in taxonomies}
        checksum_paths = dl_manager.download(checksum_urls)

        # prepare xml file name and zip urls
        gzip_urls = list()
        for tax, cpath in checksum_paths.items():
            tax_path = _CORPUS_URL.format(tax=tax)
            with open(cpath, encoding="utf-8") as cfile:
                for line in cfile:
                    xml_tax_path = line.split()[1]                  # xml file inside taxonomy
                    zip_fname = xml_tax_path + ".gz"                # zip file inside taxonomy
                    zip_fpath = os.path.join(tax_path, zip_fname)   # path inside corpus
                    gzip_urls.append(zip_fpath)

        gzip_files = dl_manager.download(gzip_urls)
        return [
            datasets.SplitGenerator(
                name="corpus",
                gen_kwargs={"filepaths": gzip_files}
            )
        ]

    def _generate_examples(self, filepaths):
        TEI_NS = "{http://www.tei-c.org/ns/1.0}"
        parser_params = dict(
            huge_tree=True,
            encoding="utf-8",
            tag=f"{TEI_NS}TEI"
        )

        _key = 0
        for doc_path in filepaths:
            logger.info("generating examples from = %s", doc_path)
            with gzip.open(open(doc_path, "rb"), "rb") as gzip_file:
                for _, tei in etree.iterparse(gzip_file, **parser_params):
                    header = tei.find(f"{TEI_NS}teiHeader")

                    meta = etree.tostring(
                        header, encoding="utf-8").decode("utf-8")
                    text = ' '.join([e.text
                        for e in tei.findall(f".//{TEI_NS}body/{TEI_NS}p")
                        if e.text is not None
                    ])

                    yield _key, {
                        "meta": meta,
                        "text": text
                    }
                    _key += 1

                gzip_file.close()
