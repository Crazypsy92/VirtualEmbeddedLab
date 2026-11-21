#!/usr/bin/env python3
import rclpy,time,json,pathlib,argparse
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy,HistoryPolicy
from vel_micro_interfaces.msg import Record,Command,Ack
ap=argparse.ArgumentParser();ap.add_argument('--directory',required=True);ap.add_argument('--mode',default='normal');ap.add_argument('--lag',type=float,default=0);a=ap.parse_args();d=pathlib.Path(a.directory)
rclpy.init();n=Node('vel_micro_ros_logger_control');q=QoSProfile(depth=512,reliability=ReliabilityPolicy.RELIABLE,history=HistoryPolicy.KEEP_LAST)
rows=[];sequences=[0,0];errors=[];acks=[];sent=0;timeouts=0;request=0;last_stamps=[0,0]
def sensor(msg,sid):
 if a.lag:time.sleep(a.lag)
 if msg.sensor_id!=sid or msg.sequence!=sequences[sid] or msg.temperature_milli_c!=(25000 if sid==0 else 30000)+msg.sequence*(25 if sid==0 else 40) or msg.uptime_ms<last_stamps[sid]:errors.append('sensor/sequence/value/time mismatch');return
 sequences[sid]+=1;last_stamps[sid]=msg.uptime_ms;rows.append({'sensor_id':sid,'sequence':msg.sequence,'temperature_milli_c':msg.temperature_milli_c,'uptime_ms':msg.uptime_ms,'host_monotonic':time.monotonic()})
def ack(msg):acks.append({key:getattr(msg,key) for key in msg.get_fields_and_field_types()})
subs=[n.create_subscription(Record,'/vel/micro_ros/sensor/'+name,lambda msg,i=i:sensor(msg,i),q) for i,name in enumerate(['a','b'])];sub=n.create_subscription(Ack,'/vel/micro_ros/ack',ack,q);pub=n.create_publisher(Command,'/vel/micro_ros/command',q)
def spin_until(predicate,timeout=15):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  if predicate():return True
  rclpy.spin_once(n,timeout_sec=.03)
 return bool(predicate())
def control(opcode,period=0,repeat=False,expected=0,timeout=5):
 global sent,timeouts,request
 if not repeat:request+=1
 msg=Command();msg.request_id=request;msg.opcode=opcode;msg.period_ms=period;before=len(acks);pub.publish(msg);sent+=1
 if not spin_until(lambda:any(p['request_id']==request and p['opcode']==opcode for p in acks[before:]),timeout):timeouts+=1;raise TimeoutError('MCU ACK timeout')
 answer=next(p for p in acks[before:] if p['request_id']==request and p['opcode']==opcode);assert answer['result']==expected,answer;return answer
result={'status':'FAIL','mode':a.mode}
try:
 if a.mode=='no_agent':
  spin_until(lambda:False,1)
  try:control(4,timeout=2)
  except TimeoutError:pass
  else:raise AssertionError('unexpected ACK without Agent')
  result.update(status='PASS',final_state='DISCONNECTED',timeouts=timeouts)
 else:
  assert spin_until(lambda:pub.get_subscription_count()>0,20),'MCU command entity not discovered'
  stopped=control(4);assert not stopped['running'] and stopped['published']==0
  assert control(3,20)['period_ms']==20
  start=control(1);assert start['running']
  duplicate=control(1,repeat=True);assert duplicate==start
  assert spin_until(lambda:len(rows)>=20)
  if a.mode=='cutoff':
   (d/'streaming.checkpoint').write_text('ready');assert spin_until(lambda:(d/'cutoff.done').exists(),10)
   try:control(4,timeout=2)
   except TimeoutError:pass
   else:raise AssertionError('unexpected ACK after cutoff')
   result.update(status='PASS',final_state='ERROR',timeouts=timeouts)
  else:
   stop=control(2);assert not stop['running'];stable=control(4)['published'];spin_until(lambda:False,.25);assert control(4)['published']==stable and stable<256
   bad=control(3,1,expected=2);assert bad['period_ms']==20
   assert control(3,60)['period_ms']==60;assert control(1)['running']
   assert spin_until(lambda:sequences==[128,128],35),(sequences,errors)
   status=control(4);assert status['sampled']==status['published']==256 and status['errors']==0 and not status['running'],status
   assert len(rows)==256 and not errors
   periods=[]
   for sid in [0,1]:
    series=[p for p in rows if p['sensor_id']==sid];delta=[b['uptime_ms']-a['uptime_ms'] for a,b in zip(series,series[1:])];assert any(10<=v<=50 for v in delta) and any(55<=v<=150 for v in delta),delta
    periods.append({'sensor':sid,'minimum_ms':min(delta),'last_ms':delta[-1]})
   growth=[]
   for sid in [0,1]:
    series=[p for p in rows if p['sensor_id']==sid];growth.append((series[-1]['host_monotonic']-series[0]['host_monotonic'])*1000-(series[-1]['uptime_ms']-series[0]['uptime_ms']))
   if a.lag>=.08:assert max(growth)>500,growth
   assert control(5)['published']==256
   (d/'records.json').write_text(json.dumps(rows)+'\n');saved=json.loads((d/'records.json').read_text());assert saved==rows
   result.update(status='PASS',final_state='COMPLETE',mcu_sampled=status['sampled'],mcu_published=status['published'],received=len(rows),per_sensor=sequences,periods=periods,duplicate_request_idempotent=True,invalid_rate_nack=bad,stop_quiet=True,records_file_verified=True,delivery_lag_growth_ms=growth,first_record_time=rows[0]['host_monotonic'],last_record_time=rows[-1]['host_monotonic'])
 result.update(commands_sent=sent,timeouts=timeouts,received=len(rows),per_sensor=sequences,errors=errors,acks=acks,qos='RELIABLE KEEP_LAST depth512',lag_seconds=a.lag)
 (d/'peer.json').write_text(json.dumps(result,indent=2)+'\n');print('MICROROS_ACQUISITION_PEER_PASS',a.mode,flush=True)
finally:n.destroy_node();rclpy.try_shutdown()
