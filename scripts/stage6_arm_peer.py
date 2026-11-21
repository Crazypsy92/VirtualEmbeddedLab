#!/usr/bin/env python3
import sys,json,pathlib,time,rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
rclpy.init();node=Node('vel_stage6_arm_peer');values=[]
sub=node.create_subscription(Int32,'/vel/micro_ros/test',lambda m:values.append(m.data),128);pub=node.create_publisher(Int32,'/vel/micro_ros/command',16)
end=time.monotonic()+25;last=0
try:
 while time.monotonic()<end:
  rclpy.spin_once(node,timeout_sec=.1)
  if time.monotonic()-last>.4:
   m=Int32();m.data=42;pub.publish(m);last=time.monotonic()
  if len(values)>=8:break
 assert len(values)>=8,values
 assert all(b==a+1 for a,b in zip(values,values[1:])),values
 pathlib.Path(sys.argv[1]).write_text(json.dumps({'values':values,'topics':node.get_topic_names_and_types(),'classification':'ordinary ROS 2 node receiving ARM micro-ROS publisher'})+'\n')
finally:node.destroy_node();rclpy.try_shutdown()
