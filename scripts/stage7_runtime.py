from stage7_support import *
from stage6_arm_runtime import Processes,freeport,wait_for,Relay as BaseRelay
import socket,pty,tty,threading,select,random,sys,re,struct
class Relay(BaseRelay):
 def __init__(self,port,d):self.cut=False;self.dropped=0;super().__init__(port,d)
 def run(self):
  sock=None
  try:
   deadline=time.monotonic()+8
   while time.monotonic()<deadline and not self.stop.is_set():
    try:sock=socket.create_connection(('127.0.0.1',self.port),timeout=.2);break
    except OSError:time.sleep(.05)
   assert sock is not None;sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
   with (self.d/'uart_mcu.bin').open('wb') as tx,(self.d/'uart_agent.bin').open('wb') as rx:
    while not self.stop.is_set():
     ready,_,_=select.select([sock,self.master],[],[],.05)
     for src in ready:
      chunk=sock.recv(4096) if src is sock else os.read(self.master,4096)
      if not chunk:return
      if self.cut:self.dropped+=len(chunk);continue
      if src is sock:
       tx.write(chunk);tx.flush();self.counts['mcu_to_agent']+=len(chunk);offset=0
       while offset<len(chunk):offset+=os.write(self.master,chunk[offset:])
      else:rx.write(chunk);rx.flush();self.counts['agent_to_mcu']+=len(chunk);sock.sendall(chunk)
  except Exception as e:
   if not self.stop.is_set():self.error=repr(e)
  finally:
   if sock:sock.close()
class Lab:
 def __init__(self,name,optimized=False,paused=False):
  self.optimized=optimized;self.d=pathlib.Path(tempfile.mkdtemp(prefix=name+'-',dir=WS/'runs'));env=rosenv();env.update(ROS_DOMAIN_ID=str(random.SystemRandom().randrange(100,200)),ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',ROS_LOG_DIR=str(self.d/'ros_logs'),RMW_IMPLEMENTATION='rmw_fastrtps_cpp',LD_LIBRARY_PATH=str(OLD/'agent_install/lib')+':'+str(OLD/'host_install/lib')+':'+env.get('LD_LIBRARY_PATH',''));env['XRCE_DOMAIN_ID_OVERRIDE']=env['ROS_DOMAIN_ID']
  p=subprocess.run(['bash','-c','source '+str(WS/'host_install/setup.bash')+"; /usr/bin/python3 -c 'import json,os;print(json.dumps(dict(os.environ)))'"],env=env,capture_output=True,text=True,timeout=15,check=True);self.env=json.loads(p.stdout);self.ps=Processes(self.d,self.env);self.port=freeport();self.request=0;self.agent=None;self.boot=None
  elf=WS/('optimized_build' if optimized else 'baseline_build')/'zephyr/zephyr.elf';cmd=['qemu-system-arm','-M','mps2-an385','-cpu','cortex-m3','-display','none','-monitor','none','-serial','stdio','-chardev',f'socket,id=xrce,host=127.0.0.1,port={self.port},server=on,wait=off,nodelay=on','-serial','chardev:xrce','-kernel',str(elf)]
  self.stub=freeport()
  if paused:cmd+=['-S','-gdb',f'tcp:127.0.0.1:{self.stub}']
  self.qemu=self.ps.start('qemu',cmd);self.pid=self.qemu.pid;self.relay=Relay(self.port,self.d);self.peer=self.ps.start('peer',['/usr/bin/python3',ROOT/'scripts/stage7_peer.py',self.d]);self.commands=[]
 def start_agent(self):
  self.agent=self.ps.start('agent'+str(len(self.ps.items)),[OLD/'host_install/lib/micro_ros_agent/micro_ros_agent','serial','--dev',self.relay.device,'-b','115200','-v','6']);return self.agent
 def read(self):
  p=self.d/'peer.json';return json.loads(p.read_text()) if p.exists() else {'latest':{},'acks':[],'sessions':{},'received':0}
 def connected(self,epoch=0,boot=0,timeout=20):
  wait_for(lambda:self.read()['latest'].get('session_id',0)>epoch and self.read()['latest'].get('boot_id',0)>=boot and self.read()['latest'].get('state')==3,timeout);return self.read()['latest']
 def command(self,op,period=0,count=128,repeat=False,expect=0,target=None,timeout=5):
  if not repeat:self.request+=1
  latest=target or self.read()['latest'];message={'boot_id':latest['boot_id'],'session_id':latest['session_id'],'request_id':self.request,'opcode':op,'period_ms':period,'count_per_sensor':count};before=len(self.read()['acks'])
  with (self.d/'commands.jsonl').open('a') as f:f.write(json.dumps(message)+'\n')
  self.commands.append(message)
  wait_for(lambda:any(p['request_id']==self.request and p['opcode']==op for p in self.read()['acks'][before:]),timeout)
  ack=next(p for p in self.read()['acks'][before:] if p['request_id']==self.request and p['opcode']==op);assert ack['result']==expect,ack;return ack
 def records(self):
  p=self.d/'records.jsonl';return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []
 def stop_agent(self):
  os.killpg(self.agent.pid,signal.SIGTERM);self.agent.wait(4)
 def assert_same_mcu(self):assert self.qemu.pid==self.pid and self.qemu.poll() is None
 def close(self):
  if self.peer.poll() is None:os.killpg(self.peer.pid,signal.SIGCONT)
  (self.d/'peer.stop').touch();self.ps.close();self.relay.close()
  (self.d/'process_exits.json').write_text(json.dumps([{'pid':p.pid,'exit':p.returncode} for p,f in self.ps.items],indent=2))
 def __enter__(self):return self
 def __exit__(self,*a):self.close()
 def proof(self):
  from stage7_integrity import forwarded
  data=self.read();agent_records=forwarded(self);log=(self.d/'qemu.log').read_text();assert 'HardFault' not in log and 'FATAL' not in log and 'FAULT' not in log
  assert self.qemu.poll() is None and self.peer.poll() is None
  if self.optimized:assert '[REC] HEAP_BOUND capacity=8192 overflow_rejected=1' in log
  mem=[dict((k,int(v)) for k,v in re.findall(r'(boot|session|live|arena_peak|unused|sampled|published|errors|cleanup_errors)=(\d+)',line)) for line in log.splitlines() if '[REC] MEMORY' in line]
  clean=[p for p,line in zip(mem,[l for l in log.splitlines() if '[REC] MEMORY' in l]) if 'phase=cleaned' in line]
  assert all(p['live']==0 and p['cleanup_errors']==0 for p in clean),clean
  assert all(p['unused']>0 for p in mem)
  return {'status':'PASS','external_logs':str(self.d),'process_exit_log':str(self.d/'process_exits.json'),'qemu_pid':self.pid,'boot_count':log.count('[REC] BOOT'),'peer':data,'memory':mem,'cleaned':clean,'agent_forwarded_records':len(agent_records),'host_received_records':data.get('received',0),'mcu_sampled_by_boot':{str(b):max(m['sampled'] for m in mem if m['boot']==b) for b in set(m['boot'] for m in mem)},'mcu_published_by_boot':{str(b):max(m['published'] for m in mem if m['boot']==b) for b in set(m['boot'] for m in mem)},'relay_dropped_bytes':self.relay.dropped,'processes':[{'pid':p.pid,'exit_at_checkpoint':p.poll()} for p,f in self.ps.items]}
