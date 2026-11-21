"""Byte-transparent relay between the slave endpoints of two native PTY UARTs."""
import os,tty,select,threading,time
class Relay:
 def __init__(self,a,b,d):
  self.paths=[a,b];self.fds=[os.open(p,os.O_RDWR|os.O_NOCTTY|os.O_NONBLOCK) for p in self.paths]
  for fd in self.fds:tty.setraw(fd)
  self.stop=threading.Event();self.error=None;self.events=[];self.event_path=d/('relay_events-'+str(time.monotonic_ns())+'.json');self.counts=[0,0];self.files=[(d/('uart_direction'+str(i)+'-'+str(time.monotonic_ns())+'.bin')).open('wb') for i in range(2)];self.thread=threading.Thread(target=self.run);self.thread.start()
 def run(self):
  try:
   while not self.stop.is_set():
    ready,_,_=select.select(self.fds,[],[],.02)
    for fd in ready:
     data=os.read(fd,4096)
     if not data:continue
     i=self.fds.index(fd);self.events.append({'monotonic':time.monotonic(),'direction':i,'bytes':len(data),'hex':data.hex()});self.files[i].write(data);self.files[i].flush();offset=0;deadline=time.monotonic()+1
     while offset<len(data):
      if time.monotonic()>deadline:raise TimeoutError('PTY relay write')
      try:offset+=os.write(self.fds[1-i],data[offset:])
      except BlockingIOError:select.select([],[self.fds[1-i]],[],.02)
     self.counts[i]+=len(data)
  except BaseException as e:
   if not self.stop.is_set():self.error=repr(e)
 def close(self):
  self.stop.set();self.thread.join(2);assert not self.thread.is_alive()
  for fd in self.fds:os.close(fd)
  for f in self.files:f.close()
  import json;self.event_path.write_text(json.dumps(self.events,indent=2))
