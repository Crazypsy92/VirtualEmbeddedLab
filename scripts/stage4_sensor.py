from stage4_support import *
import re,json
source=ROOT/'zephyr/apps/virtual_sensor_demo'
overlay=ROOT/'zephyr/boards/sensors.overlay'
rc,_=build('stage4_2/sensor',source,['-DDTC_OVERLAY_FILE='+str(overlay)])
if rc: raise SystemExit(rc)
rc,text,_,expired=run('stage4_2/sensor',qemu(ROOT/'build/zephyr/sensor/zephyr/zephyr.elf'))
z={k:int(v) for k,v in re.findall(r'\[STAT\] (\w+)=(\d+)',text)}
assert rc==0 and not expired and z['samples']==17 and z['concurrent']==80 and z['unavailable']==1 and z['result']==0 and '[ERROR]' not in text
# Driver-off is an actual separate binary run, then verified via nm.
rc,_=build('stage4_2/sensor_off',source,['-DDTC_OVERLAY_FILE='+str(overlay),'-DCONFIG_VEL_VIRTUAL_SENSOR=n'])
if rc: raise SystemExit(rc)
elf=ROOT/'build/zephyr/sensor_off/zephyr/zephyr.elf'
rc,text,_,expired=run('stage4_2/sensor_off',qemu(elf))
assert rc==0 and not expired and '[STAT] driver_disabled=1' in text
rc,symbols=call('stage4_2/sensor_off_symbols',['arm-none-eabi-nm',elf]); assert rc==0 and 'vel_api' not in symbols
# Required-property rejection is a build-time case, not a QEMU case.
bad=ROOT/'build/zephyr/missing.overlay'; bad.write_text(overlay.read_text().replace('        step-millicelsius = <25>;',''))
rc,text=build('stage4_2/sensor_missing',source,['-DDTC_OVERLAY_FILE='+str(bad)])
assert rc!=0 and 'step-millicelsius' in text and 'required' in text
print('SENSOR_RUNTIME_AND_CONFIG_PASS')
