#!/usr/bin/env python3
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage7_support import *
SOURCE=OLD
import shlex
identity();assert json.loads(((ROOT/'evidence/stage6')/'stage6_1/host_gate.json').read_text())['status']=='PASS';assert json.loads(((ROOT/'evidence/stage6')/'stage6_2/dev_tools.json').read_text())['status']=='PASS';assert json.loads(((ROOT/'evidence/stage6')/'stage6_2/toolchain_prepare.json').read_text())['status']=='PASS'
commands=json.loads((OLD/'zephyr_prepare/compile_commands.json').read_text());command=next(p['command'] for p in commands if p['file'].endswith('/samples/hello_world/src/main.c'));parts=shlex.split(command);flags=[];i=1
while i<len(parts):
 if parts[i] in ['-o','-c']:i+=2;continue
 flags.append(parts[i]);i+=1
assert any(p.startswith('--sysroot='+str(OLD/'newlib_install')) for p in flags)
cfg=(OLD/'zephyr_prepare/zephyr/.config').read_text();assert 'CONFIG_NEWLIB_LIBC=y' in cfg and 'CONFIG_POSIX_TIMERS=y' in cfg
gcc_include=subprocess.check_output(['arm-none-eabi-gcc','-print-file-name=include'],text=True).strip()
flags=['-isystem',gcc_include,'-I'+str(ROOT/'micro_ros/arm/compat')]+flags
flags+=['-include',str(ROOT/'micro_ros/arm/platform_compat.h')]
toolchain=WS/'arm_toolchain.cmake';cflags=' '.join(shlex.quote(p) for p in flags)
toolchain.write_text('set(CMAKE_SYSTEM_NAME Generic)\nset(CMAKE_SYSTEM_PROCESSOR arm)\nset(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)\nset(CMAKE_C_COMPILER '+tool('arm-none-eabi-gcc')+')\nset(CMAKE_CXX_COMPILER '+tool('arm-none-eabi-g++')+')\nset(CMAKE_C_FLAGS "'+cflags+'" CACHE STRING "" FORCE)\nset(CMAKE_CXX_FLAGS_INIT "-mcpu=cortex-m3 -mthumb -ffunction-sections -fdata-sections")\nset(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)\nset(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)\nset(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)\nset(CMAKE_C_COMPILER_WORKS TRUE)\nset(CMAKE_CXX_COMPILER_WORKS TRUE)\nset(__BIG_ENDIAN__ 0)\n')
env=os.environ.copy()
for key in list(env):
 if key.startswith(('ROS','AMENT','COLCON')) or key in ['CMAKE_PREFIX_PATH','LD_LIBRARY_PATH','PYTHONPATH','VIRTUAL_ENV']:env.pop(key,None)
env.update(PATH='/usr/local/bin:/usr/bin:/bin',PYTHONNOUSERSITE='1',CMAKE_BUILD_PARALLEL_LEVEL='4')
r=subprocess.run(['bash','-c','source '+str(OLD/'dev_install/local_setup.bash')+"; /usr/bin/python3 -c 'import json,os;print(json.dumps(dict(os.environ)))'"],env=env,capture_output=True,text=True,check=True,timeout=15);env=json.loads(r.stdout)
meta=json.loads((OLD/'sources/micro_ros_setup/config/generate_lib/generic/client-colcon.meta').read_text());meta['names']['rcutils']['cmake-args']+=['-DRCUTILS_NO_64_ATOMIC=ON','-DRCUTILS_NO_PROCESS_SUPPORT=ON']
meta['names']['microxrcedds_client']['cmake-args']+=['-DUCLIENT_PROFILE_UDP=OFF','-DUCLIENT_PROFILE_TCP=OFF','-DUCLIENT_PROFILE_DISCOVERY=OFF','-DUCLIENT_PROFILE_SERIAL=OFF','-DUCLIENT_PROFILE_CUSTOM_TRANSPORT=ON','-DUCLIENT_PROFILE_STREAM_FRAMING=ON','-DUCLIENT_CUSTOM_TRANSPORT_MTU=512']
meta['names']['rmw_microxrcedds']['cmake-args']=['-DRMW_UXRCE_TRANSPORT=custom','-DRMW_UXRCE_MAX_NODES=1','-DRMW_UXRCE_MAX_PUBLISHERS=4','-DRMW_UXRCE_MAX_SUBSCRIPTIONS=1','-DRMW_UXRCE_MAX_SERVICES=1','-DRMW_UXRCE_MAX_CLIENTS=1','-DRMW_UXRCE_MAX_HISTORY=8','-DRMW_UXRCE_STREAM_HISTORY=4']
metafile=ROOT/'micro_ros/stage7_arm.meta';metafile.write_text(json.dumps(meta,indent=2)+'\n')
base_names=['microcdr','microxrcedds_client','rcl_arm','rcutils_arm','rosidl_typesupport_arm','rosidl_typesupport_microxrcedds','rmw_microxrcedds','rclc','micro_ros_msgs','rosidl','rosidl_defaults','rosidl_core','rmw','rmw_implementation','rcl_logging','ros2_tracing','rosidl_dynamic_typesupport','common_interfaces','rcl_interfaces','unique_identifier_msgs']
ignore=['rosidl_buffer','rosidl_buffer_backend','rosidl_buffer_backend_registry','rcl_logging_spdlog','rcl_logging_implementation','rcl_yaml_param_parser','rclc_examples','rclc_parameter','rclc_lifecycle','rmw_security_common','test_msgs','test_tracetools','lttngpy']
cmd=['colcon','--log-base',str(WS/'colcon_logs'),'build','--base-paths',*[OLD/'sources'/name for name in base_names],ROOT/'micro_ros/stage7_interfaces','--build-base',WS/'arm_build','--install-base',WS/'arm_install','--merge-install','--executor','sequential','--packages-up-to','rclc','std_msgs','vel_recovery_interfaces','--packages-ignore',*ignore,'--packages-ignore-regex','.*_cpp','--metas',metafile,'--cmake-args','--no-warn-unused-cli','-DBUILD_TESTING=OFF','-DBUILD_SHARED_LIBS=OFF','-DCMAKE_POSITION_INDEPENDENT_CODE=OFF','-DTHIRDPARTY=ON','-DCMAKE_TOOLCHAIN_FILE='+str(toolchain),'-DCMAKE_POLICY_VERSION_MINIMUM=3.5','-DPython3_EXECUTABLE=/usr/bin/python3']
rc,log=run('arm_libraries',cmd,env,600)
record('interfaces_arm',{'status':'PASS' if rc==0 else 'FAIL','external_log':str(log),'toolchain':str(toolchain),'libc':'Private Newlib 4.4.0 retargetable locking, Zephyr POSIX','not_firmware_gate':True})
raise SystemExit(rc)
