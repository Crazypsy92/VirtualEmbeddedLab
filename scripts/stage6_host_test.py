#!/usr/bin/env python3
from stage6_support import *
import socket,random,sys
identity();d=pathlib.Path(tempfile.mkdtemp(prefix='host-session-',dir=WS/'runs'));env=rosenv()
# The Host binary uses XRCE RMW, the separate ordinary ROS node uses Fast DDS RMW.
r=subprocess.run(['bash','-c','source '+str(WS/'host_install/local_setup.bash')+"; /usr/bin/python3 -c 'import json,os;print(json.dumps(dict(os.environ)))'"],env=env,capture_output=True,text=True,check=True,timeout=10);env=json.loads(r.stdout)
env.update(CMAKE_PREFIX_PATH=str(WS/'agent_install')+':'+env.get('CMAKE_PREFIX_PATH',''),LD_LIBRARY_PATH=str(WS/'agent_install/lib')+':'+env.get('LD_LIBRARY_PATH',''),ROS_DOMAIN_ID=str(random.SystemRandom().randrange(100,200)),ROS_LOG_DIR=str(d/'ros_logs'),ROS_AUTOMATIC_DISCOVERY_RANGE='LOCALHOST',RMW_IMPLEMENTATION='rmw_fastrtps_cpp')
for name,cmd in [('host_app_configure',['cmake','-S',ROOT/'micro_ros/host_client','-B',WS/'host_app_build','-G','Ninja','-DPython3_EXECUTABLE=/usr/bin/python3']),('host_app_build',['cmake','--build',WS/'host_app_build','-j','4'])]:
 rc,path=run(name,cmd,env)
 assert rc==0,str(path)
with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
rc,adapterlog=run('agent_loopback_adapter',['gcc','-std=c11','-Wall','-Wextra','-Werror','-fPIC','-shared',ROOT/'micro_ros/host_client/agent_loopback_bind.c','-o',WS/'agent_loopback_bind.so','-ldl'],env,30);assert rc==0
items=[]
def start(name,cmd,e):
 f=(d/(name+'.log')).open('w');p=subprocess.Popen(list(map(str,cmd)),env=e,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);items.append((p,f));return p
def wait(predicate,timeout=20):
 deadline=time.monotonic()+timeout
 while time.monotonic()<deadline:
  if predicate():return
  time.sleep(.1)
 raise TimeoutError('Host session checkpoint')
try:
 agent_env=env.copy();agent_env.update(LD_PRELOAD=str(WS/'agent_loopback_bind.so'),VEL_AGENT_UDP_PORT=str(port))
 agent=start('agent',[WS/'host_install/lib/micro_ros_agent/micro_ros_agent','udp4','-p',port,'-v','6'],agent_env)
 time.sleep(1);assert agent.poll() is None
 assert 'VEL_AGENT_LOOPBACK_BOUND' in (d/'agent.log').read_text()
 matching=[line for line in pathlib.Path('/proc/net/udp').read_text().splitlines()[1:] if int(line.split()[1].split(':')[1],16)==port];assert matching and all(line.split()[1].startswith('0100007F:') for line in matching),matching
 ce=env.copy();ce['RMW_IMPLEMENTATION']='rmw_microxrcedds'
 client=start('client',[WS/'host_app_build/vel_micro_ros_host',port,env['ROS_DOMAIN_ID']],ce)
 peer=start('ros_peer',['/usr/bin/python3',ROOT/'scripts/stage6_host_peer.py',d/'peer.json'],env)
 wait(lambda:(d/'peer.json').exists());assert peer.wait(5)==0;assert client.poll() is None
 data=json.loads((d/'peer.json').read_text());assert data['rmw']=='rmw_fastrtps_cpp'
 assert '/vel/micro_ros/host/test' in [p[0] for p in data['topics']]
 agent_log=(d/'agent.log').read_text();assert 'create_client' in agent_log and 'establish_session' in agent_log,agent_log[-3000:]
 rss=next(p for p in pathlib.Path('/proc/'+str(agent.pid)+'/status').read_text().splitlines() if p.startswith('VmRSS:'))
 os.killpg(agent.pid,signal.SIGTERM);agent.wait(5)
 wait(lambda:client.poll() is not None,12);assert client.returncode==0,(d/'client.log').read_text()
 text=(d/'client.log').read_text();assert 'HOST_FINI' in text and 'lost=1' in text and 'HOST_COMMAND 42' in text
 record('stage6_1/host_gate',{'status':'PASS','classification':'REAL Linux C micro-ROS Client; NOT ARM','client_agent_session':True,'agent_xrce_udp_bind':'127.0.0.1 verified via /proc/net/udp','endpoint_adapter':'process-local bind address selection only; no protocol/core changes','ordinary_ros_rmw':data['rmw'],'values':data['values'],'commands_acknowledged':data['acks'],'domain':env['ROS_DOMAIN_ID'],'agent_rss':rss,'agent_exit_detected':True,'client_fini_exit':client.returncode,'external_logs':str(d)})
 print('STAGE6_1_HOST_SESSION_PASS',str(d),flush=True)
finally:
 for p,f in reversed(items):
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(3)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(3)
  f.close()
