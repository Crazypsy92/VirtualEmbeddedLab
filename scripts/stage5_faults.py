#!/usr/bin/env python3
from stage5_support import *
from stage5_uart_test import qemu_uart,freeport,connect
import socket,threading,select,sys,struct,zlib
sys.path.insert(0,str(ROOT/'ros2/vel_ros_bridge'))
from vel_ros_bridge.wire import decode,uncobs,cobs
class Proxy:
    def __init__(self,upstream,mode):
        self.port=freeport();self.upstream=upstream;self.mode=mode;self.changed=0;self.frames=0;self.data=0;self.stop=threading.Event();self.error=None;self.sockets=[]
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',self.port));self.listener.listen(1);self.listener.settimeout(.1);self.sockets.append(self.listener)
        self.thread=threading.Thread(target=self.run);self.thread.start()
    def run(self):
        try:
            while not self.stop.is_set():
                try:host,_=self.listener.accept();break
                except socket.timeout:continue
            else:return
            self.sockets.append(host);mcu=connect(self.upstream);self.sockets.append(mcu);buffer=b'';held=None
            while not self.stop.is_set():
                ready,_,_=select.select([host,mcu],[],[],.1)
                for sock in ready:
                    chunk=sock.recv(4096)
                    if not chunk:return
                    if sock is host:mcu.sendall(chunk);continue
                    buffer+=chunk
                    while b'\0' in buffer:
                        frame,buffer=buffer.split(b'\0',1)
                        if not frame:continue
                        p=decode(frame);self.frames+=1
                        if self.mode=='no_ack' and p['type'] in ['ACK','NACK']:self.changed+=1;continue
                        data=p['type']=='SENSOR_DATA'
                        if data:self.data+=1
                        if data and not self.changed and self.mode in ['disconnect','crc','length','incomplete','duplicate','reorder']:
                            self.changed+=1
                            if self.mode=='disconnect':return
                            if self.mode=='crc':raw=bytearray(uncobs(frame));raw[-1]^=1;frame=cobs(raw)
                            if self.mode=='length':
                                raw=bytearray(uncobs(frame));raw[8]=63;raw[-4:]=struct.pack('<I',zlib.crc32(raw[:-4]));frame=cobs(raw)
                            if self.mode=='incomplete':host.sendall(frame[:4]);continue
                            if self.mode=='duplicate':host.sendall(frame+b'\0')
                            if self.mode=='reorder':held=frame;continue
                        host.sendall(frame+b'\0')
                        if held is not None and data and p.get('id')==0 and p.get('seq')==1:host.sendall(held+b'\0');held=None
        except OSError as e:
            if not self.stop.is_set():self.error=str(e)
        except Exception as e:self.error=repr(e)
        finally:
            for sock in self.sockets:
                try:sock.close()
                except OSError:pass
    def close(self):
        self.stop.set();self.thread.join(2)
        assert not self.thread.is_alive(),'proxy did not terminate'
def main():
    identity();root=pathlib.Path(tempfile.mkdtemp(prefix='faults-',dir=WS/'runs'));proof=[]
    for mode in ['crc','incomplete','length','disconnect','qemu_exit','no_ack','duplicate','reorder','recovery']:
        d=root/mode;d.mkdir();env=rosenv(d)
        r=run_command(['bash','-c','source '+str(WS/'install/setup.bash')+'; /usr/bin/python3 -c \'import json,os;print(json.dumps(dict(os.environ)))\''],env);assert r.returncode==0;env=json.loads(r.stdout)
        def read():return json.loads((d/'bridge.json').read_text())
        def command(cmd,success=True):
            f=d/(cmd+'.json');run=run_command(['/usr/bin/python3',ROOT/'scripts/stage5_ros_client.py',cmd,'--output',f],env)
            assert run.returncode==0,run.stdout
            result=json.loads(f.read_text());assert result['success']==success,result
            return result
        port=freeport();proxy=None
        try:
            with Processes(d,env) as ps:
                q=ps.start('qemu',qemu_uart(port));wait_for(lambda:'Stage5 UART1 protocol' in (d/'qemu.log').read_text())
                proxy=Proxy(port,mode)
                b=ps.start('bridge',['ros2','run','vel_ros_bridge','bridge','--port',str(proxy.port),'--stats',d/'bridge.json','--timeout','.6'])
                wait_for(lambda:(d/'bridge.json').exists() and read()['state']=='READY')
                if mode=='no_ack':
                    proxy.mode='paused_mcu';os.killpg(q.pid,signal.SIGSTOP)
                    try:
                        command('get_status',False);wait_for(lambda:read()['timeouts']==1);assert proxy.frames==0
                    finally:os.killpg(q.pid,signal.SIGCONT)
                else:
                    command('start')
                    if mode=='qemu_exit':os.killpg(q.pid,signal.SIGKILL);q.wait(3)
                    if mode=='recovery':
                        wait_for(lambda:read()['valid']==256,20);command('get_status');command('stop');assert read()['state']!='ERROR'
                    else:wait_for(lambda:read()['state'] in ['ERROR','DISCONNECTED'])
                result=read()
                if mode=='no_ack':assert result['state']=='ERROR' and result['timeouts']==1 and result['sent_commands']==1
                elif mode in ['disconnect','qemu_exit']:assert result['state']=='DISCONNECTED'
                elif mode=='recovery':assert result['valid']==256 and result['discarded']==0
                else:
                    assert result['state']=='ERROR' and result['discarded']>0,result
                    if mode=='duplicate':assert result['duplicates']>0,result
                    elif mode!='reorder':assert result['protocol_errors']>0,result
                assert b.poll() is None
                proof.append({'fault':mode,'mcu_data_observed_at_proxy':proxy.data,'wire_frames_observed':proxy.frames,'mutations':proxy.changed,'valid_received':result['valid'],'discarded':result['discarded'],'duplicates':result['duplicates'],'timeouts':result['timeouts'],'commands_sent':result['sent_commands'],'final_state':result['state'],'proxy_error':proxy.error,'qemu_exit':q.poll(),'new_session':mode=='recovery','injection':'QEMU execution paused by SIGSTOP; no ACK generated before timeout' if mode=='no_ack' else mode})
                print(mode,'PASS',result,flush=True)
        finally:
            if proxy:proxy.close()
    baseline=json.loads((OUT/'stage5_3/e2e_gate.json').read_text())
    stats=baseline['bridge_stats']
    rejected=[]
    for file in pathlib.Path(baseline['external_logs']).glob('set_rate_*.json'):
        answer=json.loads(file.read_text())
        if not answer['success']:rejected.append(json.loads(answer['message']))
    assert len(rejected)==1 and rejected[0]['type']=='NACK' and rejected[0]['code']==2 and rejected[0]['period']==20
    for fault in ['slow_consumer','invalid_set_rate']:
        case={'fault':fault,'source':'e2e_gate.json','mcu_sent':baseline['mcu_sent'],'valid_received':stats['valid'],'logger_received':baseline['logger_received'],'final_state':stats['state'],'discarded':stats['discarded'],'duplicates':stats['duplicates'],'timeouts':stats['timeouts'],'commands_sent':stats['sent_commands']}
        if fault=='slow_consumer':case.update(lag_ms=40,max_delivery_delay_ms=baseline['max_delivery_delay_ms'])
        else:case.update(rejected_response=rejected[0],failure='MCU NACK code2; Service success=false; period unchanged; subsequent valid command recovered')
        proof.append(case)
    record('stage5_3/fault_gate',{'status':'PASS','real_qemu':True,'cases':proof,'external_logs':str(root),'processes_reaped':True,'recovery_policy':'Restart QEMU and bridge in a fresh isolated session. ERROR is sticky until restart; no silent full-success after corrupted records.'})
if __name__=='__main__':main()
