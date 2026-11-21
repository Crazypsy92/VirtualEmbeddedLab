from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from stage5_support import *
import sys
pkg=ROOT/'ros2/vel_ros_bridge'
rc=run_command(['colcon','build','--base-paths',str(pkg),'--build-base',str(WS/'build'),'--install-base',str(WS/'install'),'--packages-select','vel_ros_bridge'],rosenv(WS/'runs'),cwd=WS,timeout=120)
(WS/'colcon_last.log').write_text(rc.stdout);assert rc.returncode==0,rc.stdout
# Use the same system interpreter with the installed workspace environment.
d=pathlib.Path(tempfile.mkdtemp(prefix='host-mock-',dir=WS/'runs'));env=rosenv(d)
cmd=['bash','-c','set -e; source "$1" >&2; env -0','vel-overlay',WS/'install/setup.bash']
r=run_command(cmd,env);assert r.returncode==0,r.stdout;env=dict(item.split("=",1) for item in r.stdout.split("\0") if "=" in item and not item.startswith("not found"))
def client(command,value=20):
    file=d/(command+'.json');r=run_command(['/usr/bin/python3',ROOT/'scripts/stage5_ros_client.py',command,'--value',str(value),'--output',file],env);assert r.returncode==0,r.stdout;return json.loads(file.read_text())
with Processes(d,env) as ps:
    mock=ps.start('mock',['/usr/bin/python3',ROOT/'scripts/stage5_mock.py','--port-file',d/'port'])
    wait_for(lambda:(d/'port').exists());port=(d/'port').read_text()
    logger=ps.start('logger',['ros2','run','vel_ros_bridge','logger','--output',d/'logger.json'])
    bridge=ps.start('bridge',['ros2','run','vel_ros_bridge','bridge','--port',port,'--json-transport','--stats',d/'bridge.json'])
    wait_for(lambda:(d/'bridge.json').exists() and json.loads((d/'bridge.json').read_text())['state']=='READY')
    time.sleep(2);assert client('set_rate')['success'];assert client('get_status')['success'];assert client('start')['success']
    wait_for(lambda:(d/'logger.json').exists() and json.loads((d/'logger.json').read_text())['complete'],20)
    assert client('stop')['success'];rows=json.loads((d/'logger.json.records').read_text());assert len(rows)==256
    assert json.loads((d/'bridge.json').read_text())['valid']==256
with Processes(d,env) as ps:
    # Restart bridge as a separate process, no-ACK transport must produce a failed Service response.
    mock=ps.start('mock_noack',['/usr/bin/python3',ROOT/'scripts/stage5_mock.py','--port-file',d/'port2','--noack']);wait_for(lambda:(d/'port2').exists())
    bridge=ps.start('bridge_restart',['ros2','run','vel_ros_bridge','bridge','--port',(d/'port2').read_text(),'--json-transport','--stats',d/'bridge2.json','--timeout','.4'])
    wait_for(lambda:(d/'bridge2.json').exists());assert not client('get_status')['success']
record('stage5_1/host_mock_gate',{'status':'PASS','classification':'HOST MOCK, not MCU/QEMU','records':256,'temperature_units':'Celsius converted from milli-C','stamp':'ROS host clock, MCU uptime preserved in metadata','service_success_requires_correlated_ACK':True,'timeout_service_failure':True,'bridge_process_restart':True,'qos':'RELIABLE KEEP_LAST depth512','external_logs':str(d),'processes_reaped':True})
print('ROS_HOST_MOCK_GATE_PASS',d)
