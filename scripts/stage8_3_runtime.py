from vel_env import work, tool_environment
import pathlib,os,json,subprocess,socket,time,signal,re,sys,tempfile,tty
from stage6_arm_runtime import Processes,wait_for
from stage8_3_pty_relay import Relay
R=pathlib.Path(__file__).resolve().parents[1];W=work('gateway_stage8_3_ws');O=pathlib.Path(os.environ.get('VEL_STAGE8_3_EVIDENCE',str(R/'evidence/stage8_3')));V=sys.executable
sys.path.insert(0,str(R/'host/modbus_tcp_master'));from client import Master
class Lab:
 def __init__(self,name):
  (W/'runs').mkdir(parents=True,exist_ok=True);self.d=pathlib.Path(tempfile.mkdtemp(prefix=name+'-',dir=W/'runs'));self.ps=Processes(self.d,tool_environment());self.port=json.loads((W/'port.json').read_text())['port'];self.relay=None;self.control=None;self.clients=[];
  try:self.start_slave();self.start_gateway();self.connect_relay()
  except BaseException:self.close();raise
 def start_slave(self):
  self.slave=self.ps.start('slave'+str(len(self.ps.items)),[work('modbus_stage8_2_ws')/'build/zephyr/zephyr.exe','-rt','-stop_at=115']);self.slave_log=self.d/('slave'+str(len(self.ps.items)-1)+'.log');wait_for(lambda:'MODBUS_INIT rc=0' in self.slave_log.read_text(),8);self.slave_paths=re.findall(r'/dev/pts/\d+',self.slave_log.read_text());self.control=os.open(self.slave_paths[0],os.O_RDWR|os.O_NOCTTY);tty.setraw(self.control)
 def start_gateway(self):
  name='gateway'+str(len(self.ps.items));self.gateway=self.ps.start(name,[W/'build/zephyr/zephyr.exe','-rt','-stop_at=180']);self.gateway_log=self.d/(name+'.log');wait_for(lambda:'TCP_READY' in self.gateway_log.read_text(),8);self.gateway_paths=re.findall(r'/dev/pts/\d+',self.gateway_log.read_text())
 def connect_relay(self):self.relay=Relay(self.slave_paths[1],self.gateway_paths[1],self.d)
 def master(self,base=0):m=Master(self.port,base);self.clients.append(m);return m
 def raw(self):s=socket.create_connection(('127.0.0.1',self.port),timeout=3);s.settimeout(12);self.clients.append(s);return s
 def close(self):
  for c in self.clients:
   try:c.close()
   except Exception:pass
  if self.relay:self.relay.close()
  if self.control is not None:os.close(self.control)
  self.ps.close();(self.d/'process_exits.json').write_text(json.dumps([{'pid':p.pid,'exit':p.returncode} for p,f in self.ps.items],indent=2))
 def proof(self):
  text=self.gateway_log.read_text();assert 'FATAL' not in text and 'ASSERTION FAIL' not in text
  return {'logs':str(self.d),'gateway_log':str(self.gateway_log),'slave_log':str(self.slave_log),'relay_bytes':self.relay.counts if self.relay else None,'gateway_pid':self.gateway.pid,'slave_pid':self.slave.pid,'host_memory':{k:v.strip() for k,v in (line.split(':',1) for line in pathlib.Path('/proc/'+str(self.gateway.pid)+'/status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:','VmSize:','Threads:')))},'process_exits':str(self.d/'process_exits.json')}
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
def record(name,data):
 p=O/(name+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n')
def frame(tid,unit,fc,data=b''):return __import__('struct').pack('>HHHBB',tid,0,len(data)+2,unit,fc)+data
def receive(sock):
 import struct
 def exact(n):
  b=b''
  while len(b)<n:
   chunk=sock.recv(n-len(b));assert chunk,'TCP closed';b+=chunk
  return b
 h=exact(7);tid,proto,length,unit=struct.unpack('>HHHB',h);assert proto==0;return tid,unit,exact(length-1)
