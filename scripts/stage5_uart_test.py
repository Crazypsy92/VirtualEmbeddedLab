#!/usr/bin/env python3
from stage5_support import *
import sys,struct,socket
sys.path.insert(0,str(ROOT/'ros2/vel_ros_bridge'))
from vel_ros_bridge.wire import *
ELF=ROOT/'build/zephyr/ros_firmware/zephyr/zephyr.elf'
def qemu_uart(port):return ['qemu-system-arm','-M','mps2-an385','-cpu','cortex-m3','-display','none','-monitor','none','-serial','stdio','-chardev',f'socket,id=veluart,host=127.0.0.1,port={port},server=on,wait=off','-serial','chardev:veluart','-semihosting-config','enable=on,target=native','-kernel',str(ELF)]
def freeport():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
def connect(port):
    end=time.monotonic()+5
    while time.monotonic()<end:
        try:s=socket.create_connection(('127.0.0.1',port),timeout=.3);s.settimeout(.1);return s
        except OSError:time.sleep(.1)
    raise TimeoutError('UART socket startup')
class Link:
    def __init__(self,s):self.s=s;self.parser=Parser();self.data=[]
    def response(self,seq,timeout=3):
        end=time.monotonic()+timeout
        while time.monotonic()<end:
            try:chunk=self.s.recv(4096)
            except socket.timeout:continue
            if not chunk:raise ConnectionError('UART disconnected')
            for p in self.parser.feed(chunk):
                if p['type']=='SENSOR_DATA':self.data.append(p)
                elif p.get('request')==seq and p['type'] in ['ACK','NACK']:return p
        raise TimeoutError('UART ACK')
    def send(self,kind,seq,value=0):self.s.sendall(encode(kind,seq,struct.pack('<I',value) if kind=='SET_RATE' else b''));return self.response(seq)
def main():
    identity();d=pathlib.Path(tempfile.mkdtemp(prefix='uart-',dir=WS/'runs'));env=os.environ.copy();proof=[]
    for restart in range(2):
        port=freeport()
        with Processes(d,env) as ps:
            proc=ps.start('qemu'+str(restart),qemu_uart(port));s=connect(port);link=Link(s)
            try:
                assert link.send('HELLO',1)['ok'];assert link.send('SET_RATE',2,20)['period']==20
                # Fragmented command, several UART RX polls; duplicate is idempotent.
                frame=encode('START',3)
                for b in frame:s.sendall(bytes([b]));time.sleep(.002)
                assert link.response(3)['ok'];s.sendall(frame);assert link.response(3)['ok']
                # Reordered/changed duplicate request must be rejected.
                assert not link.send('STOP',2)['ok'];assert not link.send('STOP',3)['ok']
                assert link.send('GET_STATUS',4)['running']==1
                time.sleep(.15);assert link.send('STOP',5)['running']==0
                status=link.send('GET_STATUS',6);sent=status['sent'];time.sleep(.12);assert link.send('GET_STATUS',7)['sent']==sent
                assert sent>0 and status['sampled']==sent
                assert not link.send('SET_RATE',8,1)['ok'];assert link.send('GET_STATUS',9)['period']==20
                # CRC, illegal length/version, unknown type, oversize and torn frame followed by resync.
                valid=encode('GET_STATUS',10);raw=bytearray(uncobs(valid[:-1]));raw[-1]^=1;s.sendall(cobs(raw)+b'\0')
                raw=bytearray(uncobs(valid[:-1]));raw[8]=1;raw[-4:]=struct.pack('<I',zlib.crc32(raw[:-4]));s.sendall(cobs(raw)+b'\0')
                s.sendall(encode('GET_STATUS',10,version=2));s.sendall(b'\x01'*100+b'\0')
                s.sendall(b'\x03\x01');time.sleep(.45);s.sendall(b'\0')
                assert link.send('GET_STATUS',10)['errors']>=5
                s.sendall(encode(99,11));assert not link.response(11)['ok']
                assert link.send('HELLO',12)['ok']
                # Serial-number arithmetic at the half-window boundary and uint32 wrap.
                for sequence in [0x7fffffff,0xfffffffe,0xffffffff,1]:assert link.send('GET_STATUS',sequence)['ok']
                assert not link.send('GET_STATUS',0)['ok']
                s.sendall(encode('SET_RATE',2,b'abc'));assert link.response(2)['code']==2
                s.sendall(encode('GET_STATUS',3,sid=1));assert link.response(3)['code']==2
                assert link.send('HELLO',3)['ok'];assert proc.poll() is None
                proof.append({'restart':restart,'sampled':status['sampled'],'sent':sent,'host_data_frames':len(link.data),'crc_length_version_timeout_resync':True,'duplicate_idempotent':True,'reorder_rejected':True,'stop_quiet':True,'request_uint32_wrap':True,'invalid_id_payload_length_nack':True})
            finally:s.close()
    record('stage5_2/uart_gate',{'status':'PASS','transport':'QEMU UART1 TCP chardev; UART0 console','runs':proof,'restarted_qemu':True,'external_logs':str(d),'processes_reaped':True});print('BIDIRECTIONAL_UART_GATE_PASS')
if __name__=='__main__':main()
