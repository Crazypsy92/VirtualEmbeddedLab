import pathlib,time,json,sys,struct
from pymodbus.client import ModbusTcpClient
class Master:
 def __init__(self,port,base=0):
  self.wire=[];self.times=[];self.c=ModbusTcpClient('127.0.0.1',port=port,timeout=2,retries=0,trace_packet=self.trace);assert self.c.connect();self.c.transaction.next_tid=base
 def trace(self,sending,data):self.wire.append({'sending':sending,'monotonic':time.monotonic(),'hex':data.hex()});return data
 def call(self,name,*args,**kw):
  t=time.monotonic();v=getattr(self.c,name)(*args,device_id=kw.pop('device_id',1),**kw);end=time.monotonic();assert not v.isError(),v;assert v.dev_id==1;self.times.append({'tid':v.transaction_id,'start':t,'end':end,'seconds':end-t,'function':name});return v
 def close(self):self.c.close()
if __name__=='__main__':
 port,index,out=int(sys.argv[1]),int(sys.argv[2]),pathlib.Path(sys.argv[3]);m=Master(port,base=10000*(index+1))
 try:
  for i in range(40):
   m.call('write_coil',index,bool(i%2));assert m.call('read_coils',index,count=1).bits[0]==bool(i%2)
  out.write_text(json.dumps({'status':'PASS','transactions':len(m.times),'times':m.times,'wire':m.wire},indent=2))
 finally:m.close()
