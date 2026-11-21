from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import pathlib,os,time,json,sys,re,subprocess,struct,socket,tty,signal
from stage8_3_runtime import Lab as Base,wait_for,frame,receive,R
from stage8_3_1_relay import DelayRelay
W=work('gateway_stage8_3_1_ws');O=pathlib.Path(os.environ.get('VEL_STAGE8_3_1_EVIDENCE',R/'evidence/stage8_3_1'));V=sys.executable
import stage8_3_runtime as legacy
legacy.W=W
class Lab(Base):
 def start_slave(self):
  name='slave'+str(len(self.ps.items));self.slave=self.ps.start(name,[W/'slave_build/zephyr/zephyr.exe','-rt','-stop_at=2050']);self.slave_log=self.d/(name+'.log');wait_for(lambda:'MODBUS_INIT rc=0' in self.slave_log.read_text(),10);self.slave_paths=re.findall(r'/dev/pts/\d+',self.slave_log.read_text());self.control=os.open(self.slave_paths[0],os.O_RDWR|os.O_NOCTTY);tty.setraw(self.control)
 def start_gateway(self):
  self.port=json.loads((W/'port.json').read_text())['port'];name='gateway'+str(len(self.ps.items));self.gateway=self.ps.start(name,[W/'gateway_build/zephyr/zephyr.exe','-rt','-stop_at=2050']);self.gateway_log=self.d/(name+'.log');wait_for(lambda:'TCP_READY' in self.gateway_log.read_text(),10);self.gateway_paths=re.findall(r'/dev/pts/\d+',self.gateway_log.read_text())
 def connect_relay(self):self.relay=DelayRelay(self.slave_paths[1],self.gateway_paths[1],self.d)
 def raw(self):
  sock=super().raw();return CapturedSocket(sock,self.d/("raw"+str(len(self.clients))+".jsonl"))
 def sample(self):
  p=pathlib.Path('/proc')/str(self.gateway.pid);status={k:v.strip() for k,v in (l.split(':',1) for l in (p/'status').read_text().splitlines() if l.startswith(('VmRSS:','VmHWM:','VmSize:','Threads:')))};lines=[l for l in self.gateway_log.read_text().splitlines() if l.startswith('GW_STATS')];status.update({k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',lines[-1])} if lines else {});status.update(monotonic=time.monotonic(),pid=self.gateway.pid,fds=len(list((p/'fd').iterdir())));return status
class Raw:
 def __init__(self,port,path):self.s=socket.create_connection(('127.0.0.1',port),timeout=5);self.s.settimeout(5);self.log=path.open('w')
 def txn(self,tid,fc,payload,exception=None):
  req=frame(tid,1,fc,payload);start=time.monotonic();self.s.sendall(req);rtid,unit,pdu=receive(self.s);self.log.write(json.dumps({'start':start,'end':time.monotonic(),'request':req.hex(),'response_tid':rtid,'unit':unit,'pdu':pdu.hex()})+'\n');self.log.flush();assert rtid==tid and unit==1,(rtid,tid,unit)
  if exception is not None:assert pdu==bytes([fc|128,exception]),pdu
  else:assert pdu[0]==fc,pdu
  return pdu
 def close(self):self.s.close();self.log.close()
def record(name,data):
 p=O/(name+'.json');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,indent=2)+'\n')

class CapturedSocket:
 def __init__(self,sock,path):self.sock=sock;self.path=path
 def event(self,direction,data):
  with self.path.open('a') as f:f.write(json.dumps({'monotonic':time.monotonic(),'direction':direction,'bytes':data.hex()})+'\n')
 def sendall(self,data):self.event('send',data);return self.sock.sendall(data)
 def recv(self,n):
  data=self.sock.recv(n);self.event('recv',data);return data
 def __getattr__(self,name):return getattr(self.sock,name)
