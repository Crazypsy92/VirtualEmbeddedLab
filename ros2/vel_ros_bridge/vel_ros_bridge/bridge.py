import argparse,json,socket,threading,time,pathlib
import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.qos import QoSProfile,ReliabilityPolicy,HistoryPolicy
from sensor_msgs.msg import Temperature
from std_msgs.msg import String
from std_srvs.srv import Trigger
from rcl_interfaces.srv import SetParameters
from rcl_interfaces.msg import SetParametersResult
QOS=QoSProfile(depth=512,reliability=ReliabilityPolicy.RELIABLE,history=HistoryPolicy.KEEP_LAST)
class Bridge(Node):
    def __init__(self,args):
        super().__init__('vel_bridge'); self.args=args; self.state='CONNECTING'; self.closed=False; self.socket=None
        self.stats={'valid':0,'discarded':0,'duplicates':0,'timeouts':0,'sent_commands':0,'protocol_errors':0}; self.next_seq=[0,0]; self.seq=0; self.pending={}; self.request_lock=threading.Lock(); self.pending_lock=threading.Lock(); self.txlock=threading.Lock()
        self.pub=[self.create_publisher(Temperature,'/vel/sensor/'+x,QOS) for x in ['a','b']]
        self.meta=self.create_publisher(String,'/vel/records',QOS); self.status=self.create_publisher(String,'/vel/status',QOS)
        self.group=ReentrantCallbackGroup(); self.control_services=[]
        for name in ['start','stop','get_status']:
            self.control_services.append(self.create_service(Trigger,'/vel/'+name,lambda req,res,cmd=name:self.control(cmd.upper(),res),callback_group=self.group))
        self.control_services.append(self.create_service(SetParameters,'/vel/set_rate',self.set_rate,callback_group=self.group))
        self.create_timer(.2,self.publish_status); self.thread=threading.Thread(target=self.receive,daemon=True);self.thread.start()
    def publish_status(self):
        msg=String();msg.data=json.dumps({'state':self.state,**self.stats});self.status.publish(msg)
        path=pathlib.Path(self.args.stats);tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps({'state':self.state,**self.stats})+'\n');tmp.replace(path)
    def send(self,pdu):
        with self.txlock:
            if self.args.json_transport:data=json.dumps(pdu).encode()+b'\n'
            else:
                from .wire import encode_command
                data=encode_command(pdu)
            self.socket.sendall(data)
    def request(self,cmd,value=0):
        with self.request_lock:
            if self.socket is None or self.state in ['DISCONNECTED','ERROR']:return {'ok':False,'error':'not connected'}
            self.seq=(self.seq+1)&0xffffffff
            if not self.seq:self.seq=1
            event=threading.Event(); box={}
            with self.pending_lock:self.pending[self.seq]=(event,box,cmd)
            try:
                self.send({'type':cmd,'request':self.seq,'value':value});self.stats['sent_commands']+=1
                if not event.wait(self.args.timeout):self.stats['timeouts']+=1;self.state='ERROR';return {'ok':False,'error':'ACK timeout','request':self.seq}
                return box
            except OSError as e:self.state='DISCONNECTED';return {'ok':False,'error':str(e)}
            finally:
                with self.pending_lock:self.pending.pop(self.seq,None)
    def control(self,cmd,res):
        reply=self.request(cmd);res.success=bool(reply.get('ok'));res.message=json.dumps(reply);return res
    def set_rate(self,req,res):
        if len(req.parameters)!=1 or req.parameters[0].name!='period_ms' or req.parameters[0].value.type!=2:
            res.results=[SetParametersResult(successful=False,reason='expected integer period_ms')];return res
        reply=self.request('SET_RATE',req.parameters[0].value.integer_value)
        res.results=[SetParametersResult(successful=bool(reply.get('ok')),reason=json.dumps(reply))];return res
    def process(self,pdu):
        kind=pdu.get('type')
        if kind in ['ACK','NACK']:
            with self.pending_lock:
                item=self.pending.get(pdu['request'])
                if item:
                    from .wire import TYPES
                    if 'command' in pdu and pdu['command']!=TYPES[item[2]]:self.stats['discarded']+=1;self.state='ERROR';return
                    item[1].update(pdu)
                    if pdu.get('ok') and self.state!='ERROR':self.state='STREAMING' if pdu.get('running') else 'READY'
                    item[0].set()
            return
        if kind=='HELLO':
            if self.state!='ERROR':self.state='READY'
            return
        if kind=='ERROR':self.stats['protocol_errors']+=1;self.state='ERROR';return
        if kind!='SENSOR_DATA':self.stats['discarded']+=1;return
        sid,seq=pdu['id'],pdu['seq']
        if sid not in [0,1] or seq>=128 or seq!=self.next_seq[sid]:
            self.stats['discarded']+=1
            if sid in [0,1] and seq<self.next_seq[sid]:self.stats['duplicates']+=1
            self.state='ERROR';return
        expected=(25000 if sid==0 else 30000)+(seq%128)*(25 if sid==0 else 40)
        if pdu['milli']!=expected:self.stats['discarded']+=1;self.state='ERROR';return
        self.next_seq[sid]+=1;self.stats['valid']+=1
        msg=Temperature();msg.header.stamp=self.get_clock().now().to_msg();msg.header.frame_id='vel_sensor_'+str(sid);msg.temperature=pdu['milli']/1000.0;msg.variance=0.0
        self.pub[sid].publish(msg)
        pdu.update(stamp_sec=msg.header.stamp.sec,stamp_nsec=msg.header.stamp.nanosec)
        meta=String();meta.data=json.dumps(pdu);self.meta.publish(meta)
        if self.state!='ERROR':self.state='STREAMING'
    def receive(self):
        try:
            self.socket=socket.create_connection(('127.0.0.1',self.args.port),timeout=5);self.socket.settimeout(.2);self.state='READY';buffer=b''
            if not self.args.json_transport:
                from .wire import Parser
                parser=Parser()
            while not self.closed:
                try:chunk=self.socket.recv(4096)
                except socket.timeout:
                    if not self.args.json_transport:
                        parser.expire();self.parser_status(parser)
                    continue
                if not chunk:raise ConnectionError('transport EOF')
                if self.args.json_transport:
                    buffer+=chunk
                    if len(buffer)>16384:raise ValueError('oversize mock buffer')
                    while b'\n' in buffer:
                        line,buffer=buffer.split(b'\n',1);self.process(json.loads(line))
                else:
                    for pdu in parser.feed(chunk):self.process(pdu)
                    self.parser_status(parser)
        except Exception as e:
            if not self.closed:self.state='DISCONNECTED';self.get_logger().error(str(e))
        finally:
            if self.socket:self.socket.close()
    def parser_status(self,parser):
        if parser.errors>getattr(self,"parser_errors",0):
            delta=parser.errors-getattr(self,"parser_errors",0);self.stats["protocol_errors"]+=delta;self.stats["discarded"]+=delta;self.state="ERROR"
        self.parser_errors=parser.errors
    def finish(self):
        self.closed=True
        if self.socket:
            try:self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(timeout=2);self.publish_status()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,required=True);ap.add_argument('--stats',required=True);ap.add_argument('--timeout',type=float,default=1);ap.add_argument('--json-transport',action='store_true');a=ap.parse_args()
    rclpy.init();node=Bridge(a);executor=MultiThreadedExecutor(num_threads=4);executor.add_node(node)
    try:executor.spin()
    except KeyboardInterrupt:pass
    finally:node.finish();executor.shutdown();node.destroy_node();rclpy.try_shutdown()
