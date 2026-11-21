from stage8_1_support import *
import socket,re,threading

gate();install=json.loads((OUT/'renode/install.json').read_text());exe=pathlib.Path(install['executable']);d=pathlib.Path(tempfile.mkdtemp(prefix='renode-',dir=WS/'runs'));source=ROOT/'simulation/renode/firmware';elf=d/'stm32f103.elf'
build=run('renode_arm_build',['arm-none-eabi-gcc','-mcpu=cortex-m3','-mthumb','-std=c11','-g3','-Og','-Wall','-Wextra','-Werror','-ffreestanding','-nostdlib','-Wl,-Map,'+str(d/'firmware.map'),'-T',source/'link.ld',source/'main.c','-o',elf],60);assert build['exit']==0
with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
with socket.socket() as s:s.bind(('127.0.0.1',0));stub=s.getsockname()[1]
official_platform=next(exe.parent.rglob('platforms/cpus/stm32f103.repl'))
description=official_platform.read_text()
assert 'can:' not in description.lower()
# The official description fetches display-only register names at load time.
# Use its local model and RCC tag without that otherwise unbounded network call.
platform=d/'stm32f103-offline.repl'
platform.write_text(''.join(line for line in description.splitlines(keepends=True)
                            if not line.lstrip().startswith('ApplySVD @https://')))
script=d/'test.resc';script.write_text(f'mach create\nmachine LoadPlatformDescription @{platform}\nmachine LoadPlatformDescriptionFromString "button: Miscellaneous.Button @ gpioPortC 13 {{ IRQ -> gpioPortC@13 }}"\nsysbus LoadELF @{elf}\nemulation CreateServerSocketTerminal {port} "hostuart" false\nconnector Connect sysbus.usart2 hostuart\nmachine StartGdbServer {stub}\n')
log=d/'monitor.log';f=log.open('w');p=subprocess.Popen([str(exe),'--disable-xwt','--console',str(script)],stdin=subprocess.PIPE,stdout=f,stderr=subprocess.STDOUT,start_new_session=True,text=True)
def command(s):p.stdin.write(s+'\n');p.stdin.flush()
def wait(pred,timeout=30):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if pred():return
  if p.poll() is not None:raise RuntimeError(log.read_text()[-4000:])
  time.sleep(.05)
 raise TimeoutError(log.read_text()[-4000:])
def receive_until(marker, data=b'', timeout=6):
 end=time.monotonic()+timeout
 while marker not in data:
  remaining=end-time.monotonic()
  if remaining<=0:raise TimeoutError(f"Renode UART missing {marker!r}")
  sock.settimeout(remaining)
  chunk=sock.recv(4096)
  if not chunk:raise ConnectionError("Renode UART closed")
  data+=chunk
 return data.split(marker,1)[1]
sock=None
try:
 wait(lambda:'GDB' in log.read_text() or 'gdb' in log.read_text());sock=socket.create_connection(('127.0.0.1',port),timeout=5);sock.settimeout(5)
 command('emulation RunFor "0.1"');time.sleep(.5)
 for i in range(5):command('sysbus.gpioPortC.button Press');command('emulation RunFor "0.01"');command('sysbus.gpioPortC.button Release');command('emulation RunFor "0.01"')
 nm=subprocess.check_output(['arm-none-eabi-nm',elf],text=True);symbols={l.split()[2]:int(l.split()[0],16) for l in nm.splitlines() if len(l.split())==3}
 command('sysbus ReadDoubleWord '+hex(symbols['exti_count']));command('sysbus ReadDoubleWord 0x4001080c');command('start');time.sleep(.5)
 data=b''
 for i in range(20):
  msg=('frame%02d'%i).encode();sock.sendall(msg+b'\n');expected=b'ACK '+msg+b'\n'
  data=receive_until(expected,data)
 sock.sendall(b'x'*100+b'\n')
 data=receive_until(b'ERR overflow\n',data)
 data=b'';sock.sendall(b'partial')
 receive_until(b'ERR timeout\n',data)
 # Actual GDB stops, register inspection, GPIO/TX/EXTI handler code and stepping.
 command('pause');time.sleep(.2);command('machine Reset');command('sysbus LoadELF @'+str(elf));time.sleep(.3)
 gdb=d/'checks.gdb';gdb.write_text(f'set pagination off\nset confirm off\ntarget remote :{stub}\ninfo registers\nbreak gpio_marker\ncontinue\nstepi\ninfo registers\ndelete breakpoints\nbreak tx\ncontinue\nbt\ndelete breakpoints\nbreak EXTI15_10_IRQHandler\ncontinue\nbt\nstepi\ninfo registers\ndetach\nquit\n')
 def trigger():
  time.sleep(3);command('sysbus.gpioPortC.button Press')
 sender=threading.Thread(target=trigger);sender.start();debug=run('renode_gdb',['gdb-multiarch','-q','-nx','-batch',elf,'-x',gdb],30);sender.join(5);assert debug['exit']==0
 command('pause');time.sleep(.2)
 text=log.read_text();assert '0x0000000A' in text or '0xA' in text,text[-4000:]
 assert '0x00000007' in text,text[-4000:]
 record('renode/acceptance',{'status':'PASS','tests':3,'target':'STM32F103 Cortex-M3 bare metal','elf':str(elf),'platform':str(platform),'official_platform':str(official_platform),'remote_svd_skipped':True,'build':build,'log':str(log),'gdb':debug,'uart_frames':20,'exti_edges':10,'memory_scope':'Official broad memory mappings; firmware linked to 64KiB/20KiB Blue Pill budget, not ZET6 validation','can':'UNSUPPORTED: no bxCAN platform instance'})
finally:
 if sock:sock.close()
 try:
  if p.poll() is None:
   try:command('quit')
   except (OSError,ValueError):pass
   try:p.wait(5)
   except subprocess.TimeoutExpired:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(5)
    except subprocess.TimeoutExpired:
     os.killpg(p.pid,signal.SIGKILL)
     p.wait(5)
 finally:
  f.close()
  (d/'exit.json').write_text(json.dumps({'pid':p.pid,'exit':p.returncode}))
