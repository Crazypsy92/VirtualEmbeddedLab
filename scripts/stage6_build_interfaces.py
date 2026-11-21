#!/usr/bin/env python3
from stage6_support import *
identity();assert json.loads((OUT/'stage6_2/gdb_gate.json').read_text())['status']=='PASS'
env=rosenv();rc,log=run('host_interfaces',['colcon','build','--base-paths',ROOT/'micro_ros/vel_micro_interfaces','--build-base',WS/'ros_interfaces_build','--install-base',WS/'ros_interfaces_install','--packages-select','vel_micro_interfaces','--cmake-args','-DBUILD_TESTING=OFF','-DPython3_EXECUTABLE=/usr/bin/python3'],env,180)
record('stage6_3/interfaces',{'status':'PASS' if rc==0 else 'FAIL','external_log':str(log),'version':'1.0.0','unbounded_fields':False});raise SystemExit(rc)
