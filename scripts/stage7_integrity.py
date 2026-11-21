"""Compare actual Agent DDS payload writes against independently logged ROS records."""
from stage7_runtime import *
def forwarded(lab):
 result=[]
 for path in lab.d.glob('agent*.log'):
  lines=re.sub(r'\x1b\[[0-9;]*m','',path.read_text()).splitlines()
  for i,line in enumerate(lines[:-1]):
   if 'DataWriter.cpp' in line and 'write' in line and 'len: 28' in line:
    values=re.findall(r'\b[0-9A-Fa-f]{2}\b',lines[i+1])
    if len(values)==28:result.append(struct.unpack('<IIIIIiI',bytes.fromhex(' '.join(values))))
 return result
def compare(lab,expected):
 rows=lab.records();agent=forwarded(lab);fields=['boot_id','session_id','sensor_id','sequence','sample_index','temperature_milli_c','uptime_ms']
 delivered=[tuple(row[k] for k in fields) for row in rows]
 assert len(rows)==len(agent)==expected,(len(rows),len(agent),expected)
 assert set(agent)==set(delivered) and len(set(delivered))==expected
 assert not lab.read()['duplicates'] and not lab.read()['missing'] and not lab.read()['errors'],lab.read()
 return {'agent_forwarded':len(agent),'host_received':len(rows),'duplicates':0,'missing':0,'payloads_equal':True,'record_sha256':__import__('hashlib').sha256((lab.d/'records.jsonl').read_bytes()).hexdigest()}
