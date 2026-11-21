import argparse,json,pathlib,time
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Temperature
from std_msgs.msg import String
from .bridge import QOS
class Logger(Node):
    def __init__(self,args):
        super().__init__('vel_logger');self.args=args;self.temps={};self.meta={};self.next=[0,0];self.records=[];self.errors=[];self.start=time.monotonic();self.max_delay_ms=0.0
        self.sub=[self.create_subscription(Temperature,'/vel/sensor/'+x,lambda msg,i=i:self.temperature(i,msg),QOS) for i,x in enumerate(['a','b'])]
        self.sub.append(self.create_subscription(String,'/vel/records',self.record,QOS));self.create_timer(.1,self.report)
    def temperature(self,sid,msg):
        if self.args.lag:time.sleep(self.args.lag)
        delay=(self.get_clock().now().nanoseconds-msg.header.stamp.sec*1000000000-msg.header.stamp.nanosec)/1000000
        self.max_delay_ms=max(self.max_delay_ms,delay)
        key=(sid,msg.header.stamp.sec,msg.header.stamp.nanosec)
        self.temps[key]=msg;self.match(key)
    def record(self,msg):
        pdu=json.loads(msg.data);key=(pdu['id'],pdu['stamp_sec'],pdu['stamp_nsec']);self.meta[key]=pdu;self.match(key)
    def match(self,key):
        if key not in self.temps or key not in self.meta:return
        temp=self.temps.pop(key);pdu=self.meta.pop(key);sid=pdu['id'];seq=pdu['seq']
        if seq!=self.next[sid] or abs(temp.temperature-pdu['milli']/1000)>1e-9 or temp.header.frame_id!='vel_sensor_'+str(sid) or pdu['stamp_sec']<=0:self.errors.append('sequence/value/header mismatch');return
        if self.records and any(x['id']==sid and x['mcu_ms']>pdu['mcu_ms'] for x in self.records):self.errors.append('MCU time regressed');return
        self.next[sid]+=1;self.records.append(pdu)
    def report(self):
        result={'max_delivery_delay_ms':self.max_delay_ms,'received':len(self.records),'per_sensor':self.next,'errors':self.errors,'pending_meta':len(self.meta),'pending_temperature':len(self.temps),'complete':self.next==[128,128] and not self.errors}
        path=pathlib.Path(self.args.output);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(result)+'\n');tmp.replace(path)
        if result['complete']:pathlib.Path(self.args.output+'.records').write_text(json.dumps(self.records)+'\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',required=True);ap.add_argument('--lag',type=float,default=0);a=ap.parse_args();rclpy.init();n=Logger(a)
    try:rclpy.spin(n)
    except KeyboardInterrupt:pass
    finally:n.report();n.destroy_node();rclpy.try_shutdown()
