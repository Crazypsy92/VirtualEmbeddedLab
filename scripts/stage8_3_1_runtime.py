from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
import pathlib,os,time,json,sys,re,subprocess,struct,socket,tty,signal
from stage8_3_runtime import Lab as Base,wait_for,frame,receive,R
from stage8_3_1_relay import DelayRelay
from vel_transport import TcpConfig, TcpTransport
W=work('gateway_stage8_3_1_ws');O=pathlib.Path(os.environ.get('VEL_STAGE8_3_1_EVIDENCE',R/'evidence/stage8_3_1'));V=sys.executable
import stage8_3_runtime as legacy
legacy.W=W
class Lab(Base):
 def start_slave(self):
  name='slave'+str(len(self.ps.items));self.slave=self.ps.start(name,[W/'slave_build/zephyr/zephyr.exe','-rt','-stop_at=2050']);self.slave_log=self.d/(name+'.log');wait_for(lambda:'MODBUS_INIT rc=0' in self.slave_log.read_text(),10);self.slave_paths=re.findall(r'/dev/pts/\d+',self.slave_log.read_text());self.control=os.open(self.slave_paths[0],os.O_RDWR|os.O_NOCTTY);tty.setraw(self.control)
 def start_gateway(self):
  self.port=json.loads((W/'port.json').read_text())['port'];name='gateway'+str(len(self.ps.items));self.gateway=self.ps.start(name,[W/'gateway_build/zephyr/zephyr.exe','-rt','-stop_at=2050']);self.gateway_log=self.d/(name+'.log');wait_for(lambda:'TCP_READY' in self.gateway_log.read_text(),10);self.gateway_paths=re.findall(r'/dev/pts/\d+',self.gateway_log.read_text())
 @staticmethod
 def pty_identity(path):
  try:
   entry = os.stat(path)
  except FileNotFoundError:
   return None
  return entry.st_dev, entry.st_ino, entry.st_ctime_ns

 def connect_relay(self):
  self.relay=DelayRelay(self.slave_paths[1],self.gateway_paths[1],self.d)
  if not hasattr(self, 'endpoint_versions'):
   self.endpoint_versions = {}
  for path in [*self.slave_paths, *self.gateway_paths]:
   identity = self.pty_identity(path)
   if identity:
    self.endpoint_versions.setdefault(path, set()).add(identity)
 def restart(self, target):
  self.relay.close()
  self.relay = None
  proc = getattr(self, target)
  if target == 'slave':
   os.close(self.control)
   self.control = None
  proc.terminate()
  proc.wait(timeout=4)
  assert proc.returncode == 0
  getattr(self, 'start_' + target)()
  self.connect_relay()
  return {'old_pid': proc.pid, 'new_pid': getattr(self, target).pid, 'old_exit': proc.returncode}

 def close(self):
  if hasattr(self, 'slave') and self.slave.poll() is None:
   try:os.killpg(self.slave.pid, signal.SIGCONT)
   except ProcessLookupError:pass
  if self.relay:
   self.relay.close()
   self.relay = None
  super().close()
  owned = [p.pid for p, _ in self.ps.items]
  endpoints = getattr(self, 'endpoint_versions', {})
  current = {path: self.pty_identity(path) for path in endpoints}
  alive = [path for path, identity in current.items() if identity in endpoints[path]]
  reused = [path for path, identity in current.items() if identity and path not in alive]
  cleanup = {'pids': owned, 'pids_absent': all(not Path(f'/proc/{p}').exists() for p in owned),
             'ptys': sorted(endpoints), 'ptys_absent': not alive,
             'pty_paths_reused': sorted(reused), 'pty_instances_still_present': sorted(alive)}
  (self.d/'cleanup.json').write_text(json.dumps(cleanup, indent=2))
  assert cleanup['pids_absent'] and cleanup['ptys_absent'], cleanup

 def raw(self):
  sock=super().raw();return CapturedSocket(sock,self.d/("raw"+str(len(self.clients))+".jsonl"))
 def sample(self):
  p=pathlib.Path('/proc')/str(self.gateway.pid);status={k:v.strip() for k,v in (l.split(':',1) for l in (p/'status').read_text().splitlines() if l.startswith(('VmRSS:','VmHWM:','VmSize:','Threads:')))};lines=[l for l in self.gateway_log.read_text().splitlines() if l.startswith('GW_STATS')];status.update({k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',lines[-1])} if lines else {});status.update(monotonic=time.monotonic(),pid=self.gateway.pid,fds=len(list((p/'fd').iterdir())),relay_alive=self.relay.thread.is_alive() if self.relay else False);return status
class Raw:
 def __init__(self,port,path):self.s=TcpTransport(TcpConfig('127.0.0.1',port,5,5,5)).open();self.log=path.open('w');self.path=path
 def txn(self,tid,fc,payload,exception=None):
  req=frame(tid,1,fc,payload);start=time.monotonic();self.s.sendall(req);rtid,unit,pdu=receive(self.s);self.log.write(json.dumps({'start':start,'end':time.monotonic(),'request':req.hex(),'request_tid':tid,'response_tid':rtid,'request_unit':1,'unit':unit,'request_fc':fc,'response_fc':pdu[0],'backend':self.s.backend,'pdu':pdu.hex()})+'\n');self.log.flush();assert rtid==tid and unit==1,(rtid,tid,unit)
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
