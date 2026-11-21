#!/usr/bin/env python3
import socket,json,argparse,threading,time,pathlib
ap=argparse.ArgumentParser();ap.add_argument('--port-file',required=True);ap.add_argument('--noack',action='store_true');a=ap.parse_args()
s=socket.socket();s.bind(('127.0.0.1',0));s.listen(1);pathlib.Path(a.port_file).write_text(str(s.getsockname()[1]));c,_=s.accept();lock=threading.Lock();running=False;period=5
stats={'sampled':0,'sent':0,'running':0,'period':period}
def send(p):
    with lock:c.sendall(json.dumps(p).encode()+b'\n')
def produce():
    global running
    for i in range(128):
        if not running:break
        for sid in [0,1]:
            stats['sampled']+=1;send({'type':'SENSOR_DATA','id':sid,'seq':i,'mcu_ms':i*period,'milli':(25000 if sid==0 else 30000)+i*(25 if sid==0 else 40)});stats['sent']+=1
        time.sleep(period/1000)
    running=False
buffer=b''
while True:
    data=c.recv(4096)
    if not data:break
    buffer+=data
    while b'\n' in buffer:
        line,buffer=buffer.split(b'\n',1);r=json.loads(line);cmd=r['type'];ok=True
        if a.noack:continue
        if cmd=='SET_RATE':
            ok=10<=r['value']<=200
            if ok:period=r['value']
        if cmd=='START':running=True
        if cmd=='STOP':running=False
        send({'type':'ACK' if ok else 'NACK','request':r['request'],'ok':ok,'sampled':stats['sampled'],'sent':stats['sent'],'running':int(running),'period':period})
        if cmd=='START':threading.Thread(target=produce,daemon=True).start()
