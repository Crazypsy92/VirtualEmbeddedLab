from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage8_1_support import *
import re,tty,select

gate();env=tool_environment();env.update(ZEPHYR_BASE=str(zephyr_base()),ZEPHYR_TOOLCHAIN_VARIANT='host',PATH=str(Z/'.venv/bin')+':'+os.environ['PATH'])
results=[]
for name,source in [('hello',zephyr_base()/'samples/hello_world'),('smoke',ROOT/'zephyr/apps/backend_smoke/native_sim')]:
 b=WS/('native_'+name);p=run('native_build_'+name,[sys.executable,'-m','west','build','-b','native_sim/native/64',source,'-d',b,'--','-DDTC='+str(Path(tool('dtc')))],300,env,zephyr_base());results.append(p)
 if p['exit']:record('native_sim/acceptance',{'status':'FAIL','steps':results});raise SystemExit(1)
 if name=='hello':
  p=run('native_hello',[b/'zephyr/zephyr.exe','-stop_at=1'],20,env);results.append(p);assert 'Hello World!' in pathlib.Path(p['log']).read_text()
# Linux process with real PTY, separate host test client (this process).
log=WS/'runs'/('native_uart-'+str(time.monotonic_ns())+'.log');f=log.open('w');p=subprocess.Popen([str(WS/'native_smoke/zephyr/zephyr.exe'),'-rt','-stop_at=5'],env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);fd=None;received=bytearray();transcript=[]
def wait(pred,seconds=10):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if pred():return
  time.sleep(.02)
 raise TimeoutError('native UART checkpoint '+str(log))
def expect(data):
 transcript.append({'expected_response':data.decode()});end=time.monotonic()+3
 while time.monotonic()<end:
  if data in received:
   i=received.index(data);del received[:i+len(data)];return
  if select.select([fd],[],[],.05)[0]:received.extend(os.read(fd,4096))
 raise AssertionError((data,received))
try:
 wait(lambda:'UART_READY' in log.read_text());paths=re.findall(r'/dev/pts/\d+',log.read_text());assert paths,log.read_text();device=paths[-1];fd=os.open(device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);tty.setraw(fd)
 for i in range(100):
  data=('record-%03d'%i).encode();os.write(fd,data[:3]);time.sleep(.002);os.write(fd,data[3:]+b'\n');expect(b'ACK '+data+b'\n')
 os.write(fd,b'incomplete');expect(b'ERR timeout\n')
 os.write(fd,b'x'*128+b'\n');expect(b'ERR overflow\n')
 os.close(fd);fd=None;time.sleep(.1);fd=os.open(device,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK);tty.setraw(fd);os.write(fd,b'reconnected\n');expect(b'ACK reconnected\n');os.write(fd,b'QUIT\n');wait(lambda:'DONE' in log.read_text());assert p.wait(5)==0
 text=log.read_text();assert 'GPIO outputs=8 inputs=4 toggles=1000 edges=100 PASS' in text and 'CAN sent=1000 received=1000 exact=1000 PASS' in text and 'frames=101 timeouts=1 overflows=1 DONE' in text,text
 record('native_sim/acceptance',{'status':'PASS','tests':4,'steps':results,'target':'native_sim/native/64','architecture':'Linux x86_64 POSIX','executable':str(WS/'native_smoke/zephyr/zephyr.exe'),'uart_log':str(log),'process_exit':p.returncode,'gpio_outputs':8,'gpio_inputs':4,'gpio_toggles':1000,'input_edges':100,'can_sent':1000,'can_received':1000,'uart_frames':101,'uart_transcript':transcript,'socketcan':'BLOCKED: CAP_NET_ADMIN absent; no interface created','scope':'Software API emulators, not STM32 hardware'})
finally:
 if fd is not None:os.close(fd)
 if p.poll() is None:
  os.killpg(p.pid,signal.SIGTERM)
  try:p.wait(3)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait(3)
 f.close()
