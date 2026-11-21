"""Hold/release real slave response bytes; never synthesizes RTU frames."""
import os,time,select,threading,json
from stage8_3_pty_relay import Relay as Base
class DelayRelay(Base):
 def __init__(self,*args):self.holding=False;self.pending=[];self.mutex=threading.Lock();self.timeline=[];super().__init__(*args)
 def pause_responses(self):
  with self.mutex:self.holding=True;self.timeline.append({'event':'pause','monotonic':time.monotonic()})
 def release_responses(self):
  with self.mutex:
   self.timeline.append({'event':'release','monotonic':time.monotonic(),'bytes':sum(len(b) for b in self.pending)})
   for data in self.pending:self.write(1,data)
   self.pending=[];self.holding=False
 def write(self,index,data):
  offset=0;deadline=time.monotonic()+1
  while offset<len(data):
   if time.monotonic()>deadline:raise TimeoutError('relay write')
   try:offset+=os.write(self.fds[index],data[offset:])
   except BlockingIOError:select.select([],[self.fds[index]],[],.01)
 def run(self):
  try:
   while not self.stop.is_set():
    ready,_,_=select.select(self.fds,[],[],.02)
    for fd in ready:
     data=os.read(fd,4096)
     if not data:continue
     i=self.fds.index(fd)
     with self.mutex:
      self.files[i].write(data);self.files[i].flush();self.events.append({'monotonic':time.monotonic(),'direction':i,'hex':data.hex(),'held':bool(i==0 and self.holding)})
      if i==0 and self.holding:self.pending.append(data)
      else:self.write(1-i,data)
      self.counts[i]+=len(data)
  except BaseException as e:
   if not self.stop.is_set():self.error=repr(e)
 def close(self):
  super().close();self.event_path.with_suffix('.delay.json').write_text(json.dumps({'events':self.timeline,'pending_bytes':sum(len(b) for b in self.pending)},indent=2))
