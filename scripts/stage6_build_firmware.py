from vel_env import zephyr_environment
#!/usr/bin/env python3
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage6_support import *
import hashlib,sys
acquisition="--acquisition" in sys.argv
if acquisition:assert json.loads((OUT/"stage6_2/gdb_gate.json").read_text())["status"]=="PASS"
build=WS/("acquisition_build" if acquisition else "firmware_build")
identity();assert json.loads((OUT/'stage6_1/host_gate.json').read_text())['status']=='PASS';assert json.loads((OUT/'stage6_2/arm_libraries.json').read_text())['status']=='PASS'
z=zephyr_base().parent;app=ROOT/'zephyr/apps/micro_ros_firmware';private=WS/'newlib_install/arm-none-eabi'
multi=subprocess.check_output(['arm-none-eabi-gcc','-mcpu=cortex-m3','-mthumb','--print-multi-directory'],text=True).strip()
for name in ['libc.a','libm.a','libg.a']:
 target=private/'lib'/multi/name;target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():target.symlink_to(private/'lib'/name)
env=zephyr_environment("cross-compile");env["CMAKE_BUILD_PARALLEL_LEVEL"]="4"
cmd=[sys.executable,'-m','west','build','-b','mps2/an385',app,'-d',build,'--','-DVEL_ACQUISITION='+('ON' if acquisition else 'OFF'),'-DDTC='+str(Path(tool('dtc'))),'-DTOOLCHAIN_HAS_NEWLIB=ON','-DCROSS_COMPILE_TOOLCHAIN_PATH='+str(private),'-DSYSROOT_DIR='+str(private),'-DEXTRA_CPPFLAGS=-isystem '+str(private/'include'),'-DDTC_OVERLAY_FILE='+str(ROOT/'zephyr/boards/sensors.overlay')+';'+str(app/'uart.overlay')]
rc,log=run('micro_ros_firmware',cmd,env,300,zephyr_base());result={'status':'PASS' if rc==0 else 'FAIL','external_log':str(log),'board':'mps2/an385','zephyr':'v4.4.2'}
if rc==0:
 elf=build/'zephyr/zephyr.elf';symbols=subprocess.check_output(['arm-none-eabi-nm','-C',elf],text=True)
 required=['rclc_executor_spin_some','rmw_init','uxr_create_session','uxr_init_custom_transport','rcl_publish'];assert all(s in symbols for s in required),required
 result.update(elf_sha256=hashlib.sha256(elf.read_bytes()).hexdigest(),official_symbols=required,not_runtime_gate=True)
record('stage6_3/firmware_build' if acquisition else 'stage6_2/firmware_build',result);raise SystemExit(rc)
