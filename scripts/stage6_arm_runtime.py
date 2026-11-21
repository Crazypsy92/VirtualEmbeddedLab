#!/usr/bin/env python3
from stage6_support import *
import socket,pty,tty,threading,select,random,errno
ELF=WS/'firmware_build/zephyr/zephyr.elf'
def freeport():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def qemu(port):return ['qemu-system-arm','-M','mps2-an385','-cpu','cortex-m3','-display','none','-monitor','none','-serial','stdio','-chardev',f'socket,id=xrce,host=127.0.0.1,port={port},server=on,wait=off,nodelay=on','-serial','chardev:xrce','-kernel',str(ELF)]
class Relay:
 def __init__(self,port,d):
  self.port=port;self.d=d;self.master,self.slave=pty.openpty();tty.setraw(self.master);tty.setraw(self.slave);self.device=os.ttyname(self.slave);self.stop=threading.Event();self.counts={'mcu_to_agent':0,'agent_to_mcu':0};self.error=None;self.thread=threading.Thread(target=self.run);self.thread.start()
 def run(self):
  sock=None
  try:
   deadline=time.monotonic()+8
   while time.monotonic()<deadline and not self.stop.is_set():
    try:sock=socket.create_connection(('127.0.0.1',self.port),timeout=.2);break
    except OSError:time.sleep(.1)
   if sock is None:raise TimeoutError('UART TCP endpoint')
   sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1);sock.setblocking(True)
   with (self.d/'uart_mcu.bin').open('wb') as tx,(self.d/'uart_agent.bin').open('wb') as rx:
    while not self.stop.is_set():
     ready,_,_=select.select([sock,self.master],[],[],.1)
     for src in ready:
      if src is sock:
       chunk=sock.recv(4096)
       if not chunk:return
       tx.write(chunk);tx.flush();self.counts['mcu_to_agent']+=len(chunk);offset=0
       while offset<len(chunk):offset+=os.write(self.master,chunk[offset:])
      else:
       chunk=os.read(self.master,4096)
       if not chunk:return
       rx.write(chunk);rx.flush();self.counts['agent_to_mcu']+=len(chunk);sock.sendall(chunk)
  except Exception as e:
   if not self.stop.is_set():self.error=repr(e)
  finally:
   if sock:sock.close()
 def close(self):
  self.stop.set();self.thread.join(3);assert not self.thread.is_alive();os.close(self.master);os.close(self.slave)
def runtime_env(d):
 env=rosenv();env.update(ROS_DOMAIN_ID=str(random.SystemRandom().randrange(100,200)),ROS_LOG_DIR=str(d/'ros_logs'),ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',RMW_IMPLEMENTATION='rmw_fastrtps_cpp',LD_LIBRARY_PATH=str(WS/'agent_install/lib')+':'+str(WS/'host_install/lib')+':'+env.get('LD_LIBRARY_PATH',''))
 env['XRCE_DOMAIN_ID_OVERRIDE']=env['ROS_DOMAIN_ID'];return env
def wait_for(predicate,timeout=20):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if predicate():return
  time.sleep(.1)
 raise TimeoutError('ARM runtime checkpoint')
class Processes:
 def __init__(self,d,env):self.d=d;self.env=env;self.items=[]
 def start(self,name,cmd):
  f=(self.d/(name+'.log')).open('w');p=subprocess.Popen(list(map(str,cmd)),stdout=f,stderr=subprocess.STDOUT,env=self.env,start_new_session=True);self.items.append((p,f));return p
 def close(self):
  for p,f in reversed(self.items):
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(3)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(3)
   f.close()
def main():
 identity();assert json.loads((OUT/'stage6_2/firmware_build.json').read_text())['status']=='PASS'
 d=pathlib.Path(tempfile.mkdtemp(prefix='arm-topic-',dir=WS/'runs'));env=runtime_env(d);port=freeport();ps=Processes(d,env);relay=None
 try:
  q=ps.start('qemu',qemu(port));relay=Relay(port,d)
  agent=ps.start('agent',[WS/'host_install/lib/micro_ros_agent/micro_ros_agent','serial','--dev',relay.device,'-b','115200','-v','6'])
  peer=ps.start('ros_peer',['/usr/bin/python3',ROOT/'scripts/stage6_arm_peer.py',d/'peer.json'])
  wait_for(lambda:(d/'peer.json').exists(),30);assert peer.wait(5)==0
  wait_for(lambda:'COMMAND 42' in (d/'qemu.log').read_text(),5)
  assert q.poll() is None and agent.poll() is None and relay.error is None
  logs=(d/'qemu.log').read_text();assert '[UROS] SESSION READY' in logs and 'FATAL' not in logs and 'HardFault' not in logs and '[UROS] ERROR' not in logs
  assert 'establish_session' in (d/'agent.log').read_text()
  assert all(n>0 for n in relay.counts.values())
  record('stage6_2/runtime_gate',{'status':'PASS','classification':'REAL Cortex-M3 Zephyr4.4.2 micro-ROS Client through Serial PTY Agent','values':json.loads((d/'peer.json').read_text())['values'],'mcu_subscriber_command':42,'uart_bytes':relay.counts,'transparent_relay':'bytes only; no COBS or application framing','domain':env['ROS_DOMAIN_ID'],'external_logs':str(d),'gdb':'required separate gate'})
  print('ARM_MICROROS_BIDIRECTIONAL_PASS',d,flush=True)
 except Exception:
  print('Runtime logs:',d,flush=True)
  for name in ['qemu.log','agent.log','ros_peer.log']:
   p=d/name
   if p.exists():print(name,p.read_text()[-2500:])
  raise
 finally:
  ps.close()
  if relay:relay.close()
if __name__=='__main__':main()
