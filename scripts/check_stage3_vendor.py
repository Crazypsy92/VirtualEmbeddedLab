#!/usr/bin/env python3
import pathlib,json,hashlib
root=pathlib.Path(__file__).resolve().parents[1]
m=json.loads((root/'os/freertos/PROVENANCE.json').read_text())
for name,want in m['files'].items():
    if hashlib.sha256((root/'os/freertos/upstream'/name).read_bytes()).hexdigest()!=want: raise RuntimeError(name)
print('OFFICIAL_FREERTOS_PIN_VERIFIED '+m['tag']+' '+m['commit'])
