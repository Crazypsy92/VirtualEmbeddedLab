#!/usr/bin/env python3
from stage6_arm_runtime import *
import sys,re,struct
identity();assert json.loads((OUT/'stage6_2/gdb_gate.json').read_text())['status']=='PASS';assert json.loads((OUT/'stage6_3/firmware_build.json').read_text())['status']=='PASS'
def run_case(mode='normal',lag=0):
 import stage6_arm_runtime as runtime
 runtime.ELF=WS/'acquisition_build/zephyr/zephyr.elf'
 d=pathlib.Path(tempfile.mkdtemp(prefix='acquisition-'+mode+'-',dir=WS/'runs'));env=runtime_env(d)
 r=subprocess.run(['bash','-c','source '+str(WS/'ros_interfaces_install/setup.bash')+"; /usr/bin/python3 -c 'import json,os;print(json.dumps(dict(os.environ)))'"],env=env,capture_output=True,text=True,timeout=15,check=True);env=json.loads(r.stdout)
 ps=Processes(d,env);relay=None;port=freeport()
 try:
  q=ps.start('qemu',runtime.qemu(port));relay=Relay(port,d)
  agent=None
  if mode!='no_agent':agent=ps.start('agent',[WS/'host_install/lib/micro_ros_agent/micro_ros_agent','serial','--dev',relay.device,'-b','115200','-v','6'])
  peer_mode='no_agent' if mode=='no_agent' else 'cutoff' if mode in ['agent_exit','uart_disconnect','mcu_restart','command_timeout'] else 'normal'
  peer=ps.start('ros_peer',['/usr/bin/python3',ROOT/'scripts/stage6_acquisition_peer.py','--directory',d,'--mode',peer_mode,'--lag',lag])
  if peer_mode=='cutoff':
   wait_for(lambda:(d/'streaming.checkpoint').exists(),35)
   if mode=='agent_exit':os.killpg(agent.pid,signal.SIGTERM);agent.wait(5)
   elif mode=='uart_disconnect':relay.close();relay=None
   elif mode=='mcu_restart':os.killpg(q.pid,signal.SIGKILL);q.wait(5)
   elif mode=='command_timeout':os.killpg(q.pid,signal.SIGSTOP)
   (d/'cutoff.done').write_text('done')
  wait_for(lambda:peer.poll() is not None,70);assert peer.returncode==0,(d/'ros_peer.log').read_text()
  data=json.loads((d/'peer.json').read_text());assert data['status']=='PASS'
  if mode=='command_timeout':os.killpg(q.pid,signal.SIGCONT)
  if mode in ['normal','slow','recovery']:
   wait_for(lambda:'ACQUISITION FINI' in (d/'qemu.log').read_text(),8)
   assert relay.error is None and agent.poll() is None
   log=(d/'agent.log').read_text();assert 'establish_session' in log and 'create_datawriter' in log and 'create_datareader' in log
   qlog=(d/'qemu.log').read_text();assert 'HardFault' not in qlog and 'FATAL' not in qlog and '[UROS] ERROR' not in qlog
   data['resources']=re.findall(r'\[UROS\] RESOURCE (.*)',qlog);assert data['resources']
   data['agent_established_session']=True
   clean=re.sub(r'\x1b\[[0-9;]*[mK]','',log);lines=clean.splitlines();observed=[]
   for i,line in enumerate(lines):
    if 'DataWriter.cpp' in line and '| write ' in line and 'len: 16,' in line:
     payload=bytes.fromhex(lines[i+1].split(':',1)[1]);assert len(payload)==16
     sid,sequence,temp,uptime=struct.unpack('<B3xIiI',payload);observed.append({'sensor_id':sid,'sequence':sequence,'temperature_milli_c':temp,'uptime_ms':uptime})
   records=json.loads((d/'records.json').read_text());expected=[{k:p[k] for k in ['sensor_id','sequence','temperature_milli_c','uptime_ms']} for p in records]
   key=lambda p:(p['sensor_id'],p['sequence'])
   assert len(observed)==256 and len({key(p) for p in observed})==256 and sorted(observed,key=key)==sorted(expected,key=key),'Agent DDS writer payloads differ from Host records'
   data['agent_observed_data_samples']=len(observed);data['agent_payloads_match_host_records']=True
   data['agent_rss']=next(line for line in pathlib.Path('/proc/'+str(agent.pid)+'/status').read_text().splitlines() if line.startswith('VmRSS:'))
  elif mode=='no_agent':wait_for(lambda:'DISCONNECTED NO_AGENT' in (d/'qemu.log').read_text(),10)
  elif mode in ['agent_exit','uart_disconnect']:wait_for(lambda:'DISCONNECTED' in (d/'qemu.log').read_text(),10)
  data.update(mode=mode,external_logs=str(d),uart_bytes=relay.counts.copy() if relay else 'relay intentionally disconnected',qemu_returncode=q.poll(),processes_reaped=True)
  print('ACQUISITION_CASE_PASS',mode,d,flush=True);return data
 except Exception:
  print('Failed case logs:',d,flush=True)
  for name in ['qemu.log','ros_peer.log']:
   p=d/name
   if p.exists():print(name,p.read_text()[-3000:])
  raise
 finally:
  if mode=='command_timeout' and q.poll() is None:
   try:os.killpg(q.pid,signal.SIGCONT)
   except ProcessLookupError:pass
  ps.close()
  if relay:relay.close()
if __name__=='__main__':
 data=run_case('normal');record('stage6_3/e2e_gate',data)
