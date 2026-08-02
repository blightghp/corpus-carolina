import sys
import gc
import gzip
import hashlib

from io import BytesIO
from pathlib import Path

from lxml import etree
from tqdm import tqdm

TEI_NS = "{http://www.tei-c.org/ns/1.0}"


def taxonomies(root):
    return [c for c in root.iterdir() if c.is_dir()]

def allfiles(root):
    files = []
    visited = set()
    search = [root]
    while search:
        r = search.pop()
        if r in visited: continue
        visited.add(r)
        for c in r.iterdir():
            if c.is_dir():
                search.append(c)
            elif c.name.endswith('.xml.gz'):
                    files.append(c)
    return files


def sha256(xml_gz):
    h = hashlib.new('sha256')
    with xml_gz.open("rb") as gzip_file:
        compressed = gzip_file.read()
        content = gzip.decompress(compressed)
        h.update(content)

    return h.hexdigest()


if __name__ == '__main__': 
    root = Path(sys.argv[1])
    tax = taxonomies(root)

    for t in tax:
        print("Working on", t)
        s = ""
        for f in tqdm(allfiles(t)):
            sha = sha256(f)
            s += f"{sha}\t{str(f.relative_to(t))[:-3]}\n"
        with (t / 'checksum.sha256').open('w') as chk: 
            chk.write(s)
