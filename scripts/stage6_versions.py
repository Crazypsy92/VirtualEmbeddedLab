#!/usr/bin/env python3
from stage6_support import *
import tarfile,hashlib,sys
identity();lock=json.loads((ROOT/'micro_ros/dependencies.lock.json').read_text());proof=[]
for name,item in lock.items():
 archives=list((WS/'downloads').glob(name+'-'+item['commit']+'*.tar.gz'))
 assert len(archives)==1,(name,archives)
 archive=archives[0];assert hashlib.sha256(archive.read_bytes()).hexdigest()==item['archive_sha256']
 source=WS/'sources'/('newlib-private' if name=='newlib' else name);assert source.is_dir()
 checked=0
 with tarfile.open(archive) as tar:
  for entry in tar.getmembers():
   if not entry.isfile():continue
   rel=pathlib.PurePosixPath(entry.name);path=pathlib.Path(*rel.parts[1:])
   if path.suffix not in ['.c','.h','.cpp','.hpp','.cmake','.in','.msg','.py'] and path.name not in ['CMakeLists.txt','package.xml','configure']:continue
   target=source/path;assert target.is_file(),str(target)
   expected=tar.extractfile(entry).read();assert hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(expected).digest(),'modified upstream source '+str(target)
   checked+=1
 proof.append({'name':name,'commit':item['commit'],'archive_sha256':item['archive_sha256'],'upstream_source_files_unchanged':checked})
assert sys.executable=='/usr/bin/python3'
record('versions',{'status':'PASS','dependencies':proof,'user':pwd.getpwuid(os.getuid()).pw_name,'system_python':sys.executable,'private_newlib':True,'no_upstream_algorithm_patches':True})
print('STAGE6_VERSIONS_PASS',len(proof))
