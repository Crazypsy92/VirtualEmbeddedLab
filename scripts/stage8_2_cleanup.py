from vel_env import tool_environment
from vel_env import work, nonroot, tool, tool_environment, zephyr_base, ros_environment
from pathlib import Path
import sys
from pathlib import Path
import subprocess,os,signal,time,json
R=Path(__file__).resolve().parents[1];W=work('modbus_stage8_2_ws');log=W/'runs'/('termination-'+str(time.monotonic_ns())+'.log')
with log.open('w') as f:
 p=subprocess.Popen([str(W/'venv/bin/python'),str(R/'host/modbus_master/test_master.py'),'fault'],stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
 child=None
 for _ in range(100):
  path=Path('/proc')/str(p.pid)/'task'/str(p.pid)/'children'
  if path.exists() and path.read_text().strip():child=int(path.read_text().split()[0]);break
  time.sleep(.01)
 assert child
 os.killpg(p.pid,signal.SIGTERM);rc=p.wait(5);time.sleep(.1);assert not Path('/proc/'+str(child)).exists(),child
out=Path(os.environ.get('VEL_STAGE8_2_EVIDENCE',str(R/'evidence/stage8_2')))/'fault';out.mkdir(exist_ok=True,parents=True);(out/'cleanup.json').write_text(json.dumps({'status':'PASS','scenario':'terminate_host_master','master_pid':p.pid,'native_child_pid':child,'exit':rc,'child_reaped':True,'log':str(log)},indent=2)+'\n');print('CLEANUP_PASS',rc)
