import pathlib,json,time,sys,rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy
from vel_recovery_interfaces.msg import Record,Command,Status
D=pathlib.Path(sys.argv[1]);rclpy.init();n=Node('vel_recovery_logger');q=QoSProfile(depth=512,reliability=ReliabilityPolicy.RELIABLE);latest={};acks=[];sessions={};seen=set();errors=[];duplicates=missing=0;cursor=0;received=0;heap_live_peak=0;stack_unused_min=2**32-1
f=(D/'records.jsonl').open('w')
def sample(m):
 global duplicates,missing,received
 key=(m.boot_id,m.session_id,m.sensor_id,m.sequence);session=f'{m.boot_id}.{m.session_id}';counts=sessions.setdefault(session,{'received':[0,0],'next':[0,0]});sid=m.sensor_id
 if sid>1:errors.append('invalid sensor');return
 if key in seen:duplicates+=1;return
 seen.add(key);gap=m.sequence-counts['next'][sid]
 if gap<0:errors.append('reordered record')
 missing+=max(0,gap);counts['next'][sid]=m.sequence+1
 if m.temperature_milli_c!=(25000 if sid==0 else 30000)+(m.sample_index%128)*(25 if sid==0 else 40):errors.append('wrong temperature')
 counts['received'][sid]+=1;received+=1;assert received<=20000
 row={key:getattr(m,key) for key in m.get_fields_and_field_types()};row['host_monotonic']=time.monotonic();f.write(json.dumps(row)+'\n');f.flush()
def status(m):
 global latest,heap_live_peak,stack_unused_min
 p={key:getattr(m,key) for key in m.get_fields_and_field_types()};p['host_monotonic']=time.monotonic();heap_live_peak=max(heap_live_peak,m.heap_live);stack_unused_min=min(stack_unused_min,m.stack_unused)
 if not latest or (m.boot_id,m.session_id)>=(latest['boot_id'],latest['session_id']):latest=p
 if m.request_id:acks.append(p)
subs=[n.create_subscription(Record,'/vel/recovery/'+s,sample,q) for s in ['a','b']];sub=n.create_subscription(Status,'/vel/recovery/status',status,q);pub=n.create_publisher(Command,'/vel/recovery/command',q)
end=time.monotonic()+550;last=0
try:
 while time.monotonic()<end and not (D/'peer.stop').exists():
  rclpy.spin_once(n,timeout_sec=.01)
  p=D/'commands.jsonl'
  if p.exists():
   lines=p.read_text().splitlines()
   for line in lines[cursor:]:
    data=json.loads(line);m=Command()
    for key,value in data.items():setattr(m,key,value)
    pub.publish(m)
   cursor=len(lines)
  if time.monotonic()-last>.05:
   result={'latest':latest,'acks':acks[-256:],'sessions':sessions,'received':received,'duplicates':duplicates,'missing':missing,'errors':errors,'commands_sent':cursor,'heap_live_peak_sampled':heap_live_peak,'stack_unused_min_sampled':stack_unused_min};tmp=D/'peer.tmp';tmp.write_text(json.dumps(result));tmp.replace(D/'peer.json');last=time.monotonic()
finally:f.close();n.destroy_node();rclpy.try_shutdown()
