import argparse
import pathlib,time,json,sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))
from vel_modbus_transport import TransportTcpClient
from vel_transport import TcpConfig, TcpTransport
class Master:
 def __init__(self,port,base=0,*,host='127.0.0.1',connect_timeout=2,read_timeout=2,write_timeout=2):
  self.wire=[];self.times=[]
  self.transport=TcpTransport(TcpConfig(host,port,connect_timeout,read_timeout,write_timeout))
  self.c=TransportTcpClient(self.transport,trace_packet=self.trace)
  assert self.c.connect()
  self.c.transaction.next_tid=base
 def trace(self,sending,data):self.wire.append({'sending':sending,'monotonic':time.monotonic(),'hex':data.hex()});return data
 def call(self,name,*args,**kw):
  unit=kw.pop('device_id',1); t=time.monotonic();v=getattr(self.c,name)(*args,device_id=unit,**kw);end=time.monotonic();assert not v.isError(),v;assert v.dev_id==unit;self.times.append({'tid':v.transaction_id,'start':t,'end':end,'seconds':end-t,'function':name});return v
 def close(self):self.c.close()
if __name__=='__main__':
 parser=argparse.ArgumentParser()
 parser.add_argument('port',type=int)
 parser.add_argument('index',type=int)
 parser.add_argument('out',type=pathlib.Path)
 parser.add_argument('--host',default='127.0.0.1')
 args=parser.parse_args()
 index=args.index;out=args.out;m=Master(args.port,base=10000*(index+1),host=args.host)
 try:
  for i in range(40):
   m.call('write_coil',index,bool(i%2));assert m.call('read_coils',index,count=1).bits[0]==bool(i%2)
  out.write_text(json.dumps({'status':'PASS','transactions':len(m.times),'times':m.times,'wire':m.wire,'transport':m.transport.metadata},indent=2))
 finally:m.close()
