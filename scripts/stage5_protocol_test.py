#!/usr/bin/env python3
from stage5_support import *
import sys,struct,zlib
sys.path.insert(0,str(ROOT/'ros2/vel_ros_bridge'))
from vel_ros_bridge.wire import *
d=pathlib.Path(tempfile.mkdtemp(prefix='protocol-',dir=WS/'runs'));env=os.environ.copy()
cmd=['gcc','-std=c11','-Wall','-Wextra','-Werror','-Wconversion','-fsanitize=address,undefined','-fno-sanitize-recover=all','-Iprotocol/include','protocol/src/vel_wire.c','protocol/tests/wire_test.c','-o',str(d/'wire_test')]
r=run_command(cmd,env);(d/'build.log').write_text(r.stdout);assert r.returncode==0,r.stdout
r=run_command([d/'wire_test'],env);(d/'run.log').write_text(r.stdout);assert r.returncode==0,r.stdout
r=run_command([d/'wire_test','golden'],env);gold=r.stdout.strip();assert bytes.fromhex(gold)==encode('HELLO',1)
assert decode(bytes.fromhex(gold)[:-1])['type']=='HELLO'
cases=[]
for n in [0,1,8,32,64]:
    frame=encode('HELLO',17,bytes((i*17)&255 for i in range(n)))
    r=run_command([d/'wire_test','decode',frame[:-1].hex()],env);assert r.returncode==0,r.stdout
    parser=Parser();received=[]
    for b in frame:received.extend(parser.feed(bytes([b])))
    assert len(received)==1 and not parser.errors;cases.append('cross-language length '+str(n))
frames=[encode('HELLO',3),encode('GET_STATUS',4)];parser=Parser();assert len(parser.feed(b''.join(frames)))==2;cases.append('merged')
raw=bytearray(uncobs(frames[0][:-1]));raw[-1]^=1
bad_crc=cobs(raw)+b'\0';parser=Parser();assert not parser.feed(bad_crc) and parser.errors==1
r=run_command([d/'wire_test','decode',bad_crc[:-1].hex()],env);assert r.returncode==2
raw=bytearray(uncobs(frames[0][:-1]));raw[8]=65;raw[-4:]=struct.pack('<I',zlib.crc32(raw[:-4]));bad_len=cobs(raw)+b'\0'
for bad in [bad_len,encode('HELLO',1,version=2),b'\xff\x01\x00',b'\x01'*100+b'\x00']:
    parser=Parser();assert not parser.feed(bad) and parser.errors>0
    assert len(parser.feed(frames[0]))==1
parser=Parser();parser.feed(b'\x03\x01');parser.last-=1;parser.expire();assert parser.errors==1 and len(parser.feed(frames[0]))==1
record('stage5_2/protocol_gate',{'status':'PASS','golden_hex':gold,'cross_language_lengths':[0,1,8,32,64],'c_sanitizers':'ASan+UBSan 10000 bounded malformed inputs','python_cases':['fragmented','merged','CRC','length','version','malformed COBS','oversize','partial timeout','resynchronization'],'external_logs':str(d)})
print('PROTOCOL_C_PYTHON_PASS',gold)
