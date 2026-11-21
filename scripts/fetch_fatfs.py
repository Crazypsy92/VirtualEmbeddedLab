#!/usr/bin/env python3
"""Fetch or verify the three official pinned inputs; never rewrites vendor sources."""
import hashlib,json,pathlib,urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'middleware/fatfs/PROVENANCE.json').read_text())
cache=ROOT/'build/downloads'; cache.mkdir(parents=True,exist_ok=True)
for item in manifest['downloads']:
    path=cache/item['url'].rsplit('/',1)[1]
    data=path.read_bytes() if path.exists() else urllib.request.urlopen(item['url'],timeout=45).read()
    digest=hashlib.sha256(data).hexdigest()
    if digest!=item['sha256']: raise RuntimeError('Upstream input hash mismatch: '+str(path))
    if not path.exists(): path.write_bytes(data)
    print(item['url']+' SHA256='+digest)
