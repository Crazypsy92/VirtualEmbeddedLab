from vel_env import zephyr_environment
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage7_support import *
import sys,hashlib
optimized='--optimized' in sys.argv
if optimized:
 for name in ['stage7_1/recovery_gate','stage7_2/stress','stage7_2/faults','stage7_2/gdb']:
  assert json.loads((OUT/(name+'.json')).read_text())['status']=='PASS',name
build=WS/('optimized_build' if optimized else 'baseline_build')
z=zephyr_base().parent;app=ROOT/'zephyr/apps/recovery_firmware';private=OLD/'newlib_install/arm-none-eabi'
multi=subprocess.check_output(['arm-none-eabi-gcc','-mcpu=cortex-m3','-mthumb','--print-multi-directory'],text=True).strip()
for name in ['libc.a','libm.a','libg.a']:
 target=private/'lib'/multi/name;target.parent.mkdir(parents=True,exist_ok=True)
 if not target.exists():target.symlink_to(private/'lib'/name)
env=zephyr_environment("cross-compile");env["CMAKE_BUILD_PARALLEL_LEVEL"]="4"
cmd=[sys.executable,'-m','west','build','-p','auto','-b','mps2/an385',app,'-d',build,'--','-DDTC='+str(Path(tool('dtc'))),'-DTOOLCHAIN_HAS_NEWLIB=ON','-DCROSS_COMPILE_TOOLCHAIN_PATH='+str(private),'-DSYSROOT_DIR='+str(private),'-DEXTRA_CPPFLAGS=-isystem '+str(private/'include'),'-DEXTRA_CONF_FILE='+str(app/'optimized.conf') if optimized else '-DEXTRA_CONF_FILE=', '-DDTC_OVERLAY_FILE='+str(ROOT/'zephyr/boards/sensors.overlay')+';'+str(app/'uart.overlay')]
rc,log=run('firmware_opt' if optimized else 'firmware_base',cmd,env,300,zephyr_base())
record('optimized_build' if optimized else 'baseline_build',{'status':'PASS' if rc==0 else 'FAIL','log':str(log),'elf':str(build/'zephyr/zephyr.elf')});raise SystemExit(rc)
