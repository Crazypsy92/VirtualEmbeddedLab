#!/usr/bin/env python3
from stage5_support import *
from stage5_uart_test import qemu_uart,freeport,connect,Link,ELF
import threading,socket
identity();d=pathlib.Path(tempfile.mkdtemp(prefix='gdb-',dir=WS/'runs'));port=freeport();stub=freeport();done=threading.Event();answers=[];errors=[]
def sender():
    try:
        s=connect(port)
        try:
            link=Link(s);answers.append(link.send('HELLO',1));answers.append(link.send('START',2))
            end=time.monotonic()+10
            while not done.is_set() and time.monotonic()<end:
                try:chunk=s.recv(4096)
                except socket.timeout:continue
                if not chunk:break
                for p in link.parser.feed(chunk):
                    if p['type']=='SENSOR_DATA':answers.append(p);done.set()
        finally:s.close()
    except Exception as e:errors.append(repr(e))
with Processes(d,os.environ.copy()) as ps:
    q=ps.start('qemu',qemu_uart(port)+['-S','-gdb',f'tcp:127.0.0.1:{stub}'])
    time.sleep(.4);thread=threading.Thread(target=sender);thread.start()
    try:
        result=run_command(['gdb-multiarch','-q','-nx','-batch',ELF,'-ex',f'target remote 127.0.0.1:{stub}','-x',ROOT/'scripts/stage5_gdb.gdb'],os.environ.copy(),timeout=35)
        (d/'gdb.log').write_text(result.stdout)
        assert result.returncode==0 and 'STAGE5_GDB_PASS' in result.stdout,result.stdout
        wait_for(done.is_set,5);assert not errors,errors;assert q.poll() is None
    finally:done.set();thread.join(4)
    assert not thread.is_alive() and not errors,errors
    assert len(answers)>=3 and answers[0]['type']=='ACK' and answers[1]['type']=='ACK'
    assert 'FATAL' not in (d/'qemu.log').read_text() and 'HardFault' not in (d/'qemu.log').read_text()
record('stage5_3/gdb_gate',{'status':'PASS','uart_rx_breakpoint':True,'command_breakpoint':True,'sensor_api_driver_fetch_breakpoint':True,'tx_ack_and_sensor_frames_crc_decoded':True,'state_stopped_to_running':True,'no_fatal_or_hardfault_observed':True,'external_logs':str(d),'processes_reaped':True})
print('STAGE5_GDB_GATE_PASS',d)
