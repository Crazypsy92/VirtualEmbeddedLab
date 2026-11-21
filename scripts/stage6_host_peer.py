#!/usr/bin/env python3
import sys,json,pathlib,time,rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
rclpy.init();node=Node('vel_stage6_host_peer');values=[];acks=[]
sub=node.create_subscription(Int32,'/vel/micro_ros/host/test',lambda m:values.append(m.data),128)
ack=node.create_subscription(Int32,'/vel/micro_ros/host/ack',lambda m:acks.append(m.data),128)
pub=node.create_publisher(Int32,'/vel/micro_ros/host/command',16)
end=time.monotonic()+20;last=0
try:
 while time.monotonic()<end:
  rclpy.spin_once(node,timeout_sec=.1)
  if time.monotonic()-last>.3:
   msg=Int32();msg.data=42;pub.publish(msg);last=time.monotonic()
  if len(values)>=8 and 42 in acks:break
 assert len(values)>=8 and 42 in acks,(values,acks)
 assert all(b==a+1 for a,b in zip(values,values[1:])),values
 pathlib.Path(sys.argv[1]).write_text(json.dumps({'values':values,'acks':acks,'topics':[(name,types) for name,types in node.get_topic_names_and_types()],'rmw':rclpy.get_rmw_implementation_identifier()})+'\n')
 print('ORDINARY_ROS_PEER_BIDIRECTIONAL_PASS',flush=True)
finally:node.destroy_node();rclpy.try_shutdown()
