#!/usr/bin/env python3
from stage5_support import *
import sys
sys.path.insert(0,str(ROOT/'scripts'))
import stage4_support as zephyr
identity();d=pathlib.Path(tempfile.mkdtemp(prefix='firmware-build-',dir=WS/'runs'));zephyr.OUT=d
rc,text=zephyr.build('stage5_2/ros_firmware',ROOT/'zephyr/apps/ros_bridge_firmware',['-DDTC_OVERLAY_FILE='+str(ROOT/'zephyr/boards/sensors.overlay')+';'+str(ROOT/'zephyr/apps/ros_bridge_firmware/uart.overlay')])
if not rc:record('stage5_2/build_gate',{'status':'PASS','external_logs':str(d),'board':'mps2/an385','zephyr_version':'v4.4.2','compiler_warnings':text.lower().count('warning:'),'separate_uart':True})
raise SystemExit(rc)
