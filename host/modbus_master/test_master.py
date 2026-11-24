import os,pathlib,subprocess,time,re,json,tty,signal,sys,serial
def terminated(signum,frame):raise SystemExit(128+signum)
signal.signal(signal.SIGTERM,terminated)
from pymodbus.framer.rtu import FramerRTU
from pty_control import PtySerialClient, wait_rx_ready
ROOT=pathlib.Path(__file__).resolve().parents[2];WS=pathlib.Path(os.environ.get('VEL_WORK_ROOT',ROOT/'build/workspaces'))/'modbus_stage8_2_ws';mode=sys.argv[1] if len(sys.argv)>1 else 'all';d=WS/'runs'/('master-'+str(time.monotonic_ns()));d.mkdir();log=d/'slave.log';f=log.open('w');p=subprocess.Popen([str(WS/'build/zephyr/zephyr.exe'),'-rt','-stop_at=110'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True);transcript=[];cases=[];transactions=0;writes=0;control=None;c=None

def trace(sending,data):transcript.append({'time':time.monotonic(),'direction':'request' if sending else 'response','hex':data.hex()});return data
def wait(pred,timeout=5):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if pred():return
  time.sleep(.01)
 raise TimeoutError(log.read_text()[-2000:])
def call(method,*args,**kw):
 global transactions,writes
 wait_rx_ready(control)
 response=getattr(c,method)(*args,device_id=1,**kw);assert not response.isError(),response;transactions+=1
 if method.startswith('write_'):writes+=1
 return response
def case(name,fn):
 start=time.monotonic();fn();cases.append({'name':name,'status':'PASS','seconds':time.monotonic()-start})
def raw(payload,expect=None,fragment=False,corrupt=False):
 data=payload+FramerRTU.compute_CRC(payload).to_bytes(2,'big')
 if corrupt:data=data[:-1]+bytes([data[-1]^1])
 wait_rx_ready(control)
 c.socket.reset_input_buffer();trace(True,data)
 if fragment:c.socket.write(data[:3]);time.sleep(.0001);c.socket.write(data[3:])
 else:c.socket.write(data)
 time.sleep(.02);response=c.socket.read(256);trace(False,response)
 if expect is None:assert response==b'',response.hex()
 else:
  assert response and FramerRTU.compute_CRC(response[:-2])==int.from_bytes(response[-2:],'big'),response.hex()
  assert response[1:-2]==expect,(response.hex(),expect.hex())
 return response
try:
 wait(lambda:'MODBUS_INIT rc=0' in log.read_text());paths=re.findall(r'/dev/pts/\d+',log.read_text());control=os.open(paths[0],os.O_RDWR|os.O_NOCTTY);tty.setraw(control)
 c=PtySerialClient(paths[1],baudrate=115200,parity='N',stopbits=1,timeout=.15,retries=0,trace_packet=trace);assert c.connect()
 def functions():
  call('write_coil',0,True);assert call('read_coils',0,count=8).bits[:8]==[True]+[False]*7
  bits=[True,False,True,False,False,True,True,False];call('write_coils',0,bits);assert call('read_coils',0,count=8).bits[:8]==bits
  call('write_register',1,20);assert call('read_holding_registers',1,count=1).registers==[20]
  call('write_registers',0,[1,10,500,0x96,100]);assert call('read_holding_registers',0,count=5).registers==[1,10,500,0x96,100]
  assert call('read_input_registers',7,count=1).registers==[0x96]
  for bits in [0,15,5,10,0]:
   before=log.read_text().count('INPUT bits=');os.write(control,bytes([65+bits]));wait(lambda:log.read_text().count('INPUT bits=')>before);assert call('read_discrete_inputs',0,count=4).bits[:4]==[bool(bits&(1<<i)) for i in range(4)];assert call('read_input_registers',6,count=1).registers==[bits]
  os.write(control,b'S');time.sleep(.02);assert 'edges=' in log.read_text()
 case('eight_functions_gpio_and_registers',functions)
 if mode in ['all','protocol']:
  def stress():
   for i in range(250):
    value=i&255;call('write_register',3,value);assert call('read_input_registers',7,count=1).registers==[value];call('write_coil',i%8,True);assert call('read_coils',i%8,count=1).bits[0]
  case('1000_transactions',stress)
 if mode in ['all','fault']:
  def faults():
   before=call('read_holding_registers',0,count=8).registers;coils=call('read_coils',0,count=8).bits[:8]
   raw(bytes.fromhex('010600010000'),corrupt=True);raw(bytes.fromhex('020300000001'));raw(bytes.fromhex('014100000001'),b'\xc1\x01');raw(bytes.fromhex('010300080001'),b'\x83\x02');raw(bytes.fromhex('010600010000'),b'\x86\x03');raw(bytes.fromhex('010300000000'),b'\x83\x03')
   raw(bytes.fromhex('0110000400020400640001'),b'\x90\x02');raw(bytes.fromhex('010f000700020103'),b'\x8f\x02');raw(bytes.fromhex('0110000000020400010000'),b'\x90\x03')
   assert call('read_holding_registers',0,count=8).registers==before;assert call('read_coils',0,count=8).bits[:8]==coils
   wait_rx_ready(control)
   trace(True,bytes.fromhex('010600'));c.socket.write(bytes.fromhex('010600'));time.sleep(.03);dropped=c.socket.read(100);trace(False,dropped);assert dropped==b''
   # Reopen the same PTY after an incomplete transaction; native slave keeps safe state.
   c.close();time.sleep(.02);assert c.connect();assert call('read_holding_registers',0,count=8).registers==before
   raw(bytes.fromhex('010300000001'),b'\x03\x02'+before[0].to_bytes(2,'big'),fragment=True)
  case('fault_matrix_and_atomic_rejection',faults)
 def effects():
  call('write_register',0,0);time.sleep(.03);os.write(control,b'S');time.sleep(.03);text=log.read_text();s0=int(re.findall(r'samples=(\d+)',text)[-1]);time.sleep(.05);os.write(control,b'S');time.sleep(.03);assert int(re.findall(r'samples=(\d+)',log.read_text())[-1])==s0
  call('write_registers',0,[1,1,0]);time.sleep(.06);os.write(control,b'S');time.sleep(.03);assert int(re.findall(r'samples=(\d+)',log.read_text())[-1])>s0;assert call('read_input_registers',0,count=1).registers[0]&256
 case('configuration_applied_to_state_machine',effects)
 assert call('read_holding_registers',5,count=1).registers==[writes],writes
 final={'holding':call('read_holding_registers',0,count=8).registers,'inputs':call('read_input_registers',0,count=8).registers,'coils':call('read_coils',0,count=8).bits[:8]};os.write(control,b'S');time.sleep(.03);statsline=[l for l in log.read_text().splitlines() if l.startswith('STATS')][-1];stats={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',statsline)};assert stats['direction']==1<<17 and stats['de_high']>0 and stats['de_low']>0,stats
 result={'status':'PASS','mode':mode,'cases':cases,'tests':len(cases),'successful_transactions':transactions,'stats':stats,'final':final,'log':str(log),'transcript':str(d/'wire.json'),'host_memory':{k:v.strip() for k,v in (line.split(':',1) for line in pathlib.Path('/proc/'+str(p.pid)+'/status').read_text().splitlines() if line.startswith(('VmRSS:','VmHWM:','VmSize:','Threads:')))},'scope':'Real PTY bytes; parity unsupported physically; official Zephyr RTU plus independent pymodbus'}
finally:
 if c:c.close()
 if control is not None:os.close(control)
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(3)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(3)
 f.close();(d/'wire.json').write_text(json.dumps(transcript,indent=2));(d/'exit.json').write_text(json.dumps({'pid':p.pid,'exit':p.returncode}))
result['process_exit']=p.returncode;out=pathlib.Path(os.environ.get('VEL_STAGE8_2_EVIDENCE',str(ROOT/'evidence/stage8_2')))/mode;out.mkdir(parents=True,exist_ok=True);(out/'acceptance.json').write_text(json.dumps(result,indent=2)+'\n');print('MASTER_PASS',mode,transactions,d)
