#!/usr/bin/env python3
from stage6_support import *
identity();env=rosenv();prefix=WS/'agent_install'
def need(name,cmd,timeout=600):
 rc,path=run(name,cmd,env,timeout)
 if rc:record('stage6_1/build_failure',{'status':'FAIL','step':name,'exit':rc,'external_log':str(path)});raise SystemExit(rc)
need('spdlog_configure',['cmake','-S',WS/'sources/spdlog','-B',WS/'spdlog_build','-G','Ninja','-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DCMAKE_POSITION_INDEPENDENT_CODE=ON','-DSPDLOG_FMT_EXTERNAL=OFF','-DSPDLOG_BUILD_EXAMPLE=OFF','-DSPDLOG_BUILD_TESTS=OFF','-DCMAKE_POLICY_VERSION_MINIMUM=3.5'])
need('spdlog_build',['cmake','--build',WS/'spdlog_build','-j','4'])
need('spdlog_install',['cmake','--install',WS/'spdlog_build'])
env['CMAKE_PREFIX_PATH']=str(prefix)+':'+env.get('CMAKE_PREFIX_PATH','')
need('xrce_agent_configure',['cmake','-S',WS/'sources/microxrcedds_agent','-B',WS/'agent_build','-G','Ninja','-Dspdlog_DIR='+str(prefix/'lib/cmake/spdlog'),'-DUAGENT_SUPERBUILD=OFF','-DUAGENT_USE_SYSTEM_FASTDDS=ON','-DUAGENT_USE_SYSTEM_FASTCDR=ON','-DUAGENT_USE_SYSTEM_LOGGER=ON','-DUAGENT_CED_PROFILE=OFF','-DUAGENT_P2P_PROFILE=OFF','-DCMAKE_BUILD_TYPE=RelWithDebInfo','-DCMAKE_INSTALL_PREFIX='+str(prefix)])
need('xrce_agent_build',['cmake','--build',WS/'agent_build','-j','4'])
need('xrce_agent_install',['cmake','--install',WS/'agent_build'])
env['CMAKE_PREFIX_PATH']=str(prefix)+':'+env.get('CMAKE_PREFIX_PATH','');env['LD_LIBRARY_PATH']=str(prefix/'lib')+':'+env.get('LD_LIBRARY_PATH','')
base=['colcon','build','--executor','sequential','--base-paths',*[WS/'sources'/name for name in ['microcdr','microxrcedds_client','rosidl_typesupport_microxrcedds','rclc','micro_ros_msgs','rmw_microxrcedds','common_interfaces','rcl_interfaces','unique_identifier_msgs','micro_ros_agent']],'--build-base',WS/'host_build','--install-base',WS/'host_install','--merge-install','--packages-ignore','microxrcedds_agent','test_msgs','--cmake-args','-DBUILD_TESTING=OFF','-DBUILD_SHARED_LIBS=ON','-DMICROROSAGENT_SUPERBUILD=OFF','-DCMAKE_POLICY_VERSION_MINIMUM=3.5','-DPython3_EXECUTABLE=/usr/bin/python3']
# Build extension generators first, then regenerate only the required standard interfaces.
need('host_generators',base+['--packages-select','microcdr','microxrcedds_client','rosidl_typesupport_microxrcedds_c','rosidl_typesupport_microxrcedds_cpp'])
r=subprocess.run(['bash','-c','source '+str(WS/'host_install/local_setup.bash')+"; /usr/bin/python3 -c 'import json,os;print(json.dumps(dict(os.environ)))'"],env=env,capture_output=True,text=True,timeout=15,check=True);env=json.loads(r.stdout)
need('host_libraries',base+['--packages-select','builtin_interfaces','std_msgs','micro_ros_msgs','rmw_microxrcedds','rclc','micro_ros_agent'])
record('stage6_1/build_gate',{'status':'PASS','agent_version':'7.0.0','xrce_version':'3.0.2','external_workspace':str(WS)})
