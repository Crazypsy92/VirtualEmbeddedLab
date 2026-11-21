from vel_env import zephyr_environment
#!/usr/bin/env python3
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage6_support import *
identity();assert json.loads((OUT/'stage6_1/host_gate.json').read_text())['status']=='PASS'
z=zephyr_base().parent;env=zephyr_environment("cross-compile");env["CMAKE_BUILD_PARALLEL_LEVEL"]="4"
cmd=[sys.executable,'-m','west','build','-b','mps2/an385',zephyr_base()/'samples/hello_world','-d',WS/'zephyr_prepare','--','-DDTC='+str(Path(tool('dtc'))),'-DEXTRA_CONF_FILE='+str(ROOT/'micro_ros/arm/zephyr.conf'),'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DTOOLCHAIN_HAS_NEWLIB=ON','-DCROSS_COMPILE_TOOLCHAIN_PATH='+str(WS/'newlib_install/arm-none-eabi'),'-DSYSROOT_DIR='+str(WS/'newlib_install/arm-none-eabi'),'-DEXTRA_CPPFLAGS=-isystem '+str(WS/'newlib_install/arm-none-eabi/include')]
rc,log=run('zephyr_prepare',cmd,env,180,zephyr_base())
record('stage6_2/toolchain_prepare',{'status':'PASS' if rc==0 else 'FAIL','classification':'Zephyr configuration probe only; NOT micro-ROS ARM acceptance','external_log':str(log)})
raise SystemExit(rc)
