#!/usr/bin/env python3
"""Verify pinned hashes and reproduce the official patch sequence without network."""
import hashlib,json,pathlib,subprocess,tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
v=ROOT/'middleware/fatfs'
m=json.loads((v/'PROVENANCE.json').read_text())
for name,expected in m['source_files'].items():
    actual=hashlib.sha256((v/name).read_bytes()).hexdigest()
    if actual!=expected: raise RuntimeError('Vendor file hash mismatch: '+name)
with tempfile.TemporaryDirectory(prefix='vendor-verify-',dir=ROOT/'build') as d:
    target=pathlib.Path(d)/'ff.c'
    target.write_bytes((v/'upstream/original/ff.c').read_bytes())
    for name in ['ff16p1.diff','ff16p2.diff']:
        patch=v/'patches'/name
        entry=next(x for x in m['downloads'] if x['url'].endswith('/'+name))
        if hashlib.sha256(patch.read_bytes()).hexdigest()!=entry['sha256']: raise RuntimeError('Patch hash mismatch')
        subprocess.run(['patch','--batch','--fuzz=0',str(target),str(patch)],check=True,timeout=10)
    if target.read_bytes()!=(v/'upstream/ff.c').read_bytes(): raise RuntimeError('Official patch replay mismatch')
print('FATFS_PROVENANCE_PASS R0.16 patch-1 then patch-2; exact hashes and replay verified')
