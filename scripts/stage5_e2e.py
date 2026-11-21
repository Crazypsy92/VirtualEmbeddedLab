#!/usr/bin/env python3
from stage5_support import *
from stage5_uart_test import qemu_uart,freeport
import sys
identity()
if "VEL_STAGE5_E2E_RUN" not in os.environ:
    d=pathlib.Path(tempfile.mkdtemp(prefix="e2e-",dir=WS/"runs"))
    result=run_command(["bash","-c",'set -e; source "$1" >&2; env -0',
                        "vel-overlay",WS/"install/setup.bash"],rosenv(d))
    assert result.returncode==0,result.stdout
    env=dict(item.split("=",1) for item in result.stdout.split("\0") if "=" in item)
    env["VEL_STAGE5_E2E_RUN"]=str(d)
    os.execve(sys.executable,[sys.executable,__file__],env)
d=pathlib.Path(os.environ.pop("VEL_STAGE5_E2E_RUN"))
env=os.environ.copy()
from stage5_ros_client import ServiceClient

def read(path):
    return json.loads(path.read_text())

def control(command,value=20,success=True):
    file=d/(command+"_"+str(time.monotonic_ns())+".json")
    answer=client.call(command,value)
    file.write_text(json.dumps(answer)+chr(10))
    assert answer["success"]==success,answer
    pdu=json.loads(answer['message']);assert pdu['request']>0 and pdu['type'] in ['ACK','NACK'];return pdu
port=freeport()
with ServiceClient() as client, Processes(d,env) as ps:
    qemu=ps.start('qemu',qemu_uart(port));wait_for(lambda:'Stage5 UART1 protocol' in (d/'qemu.log').read_text())
    logger=ps.start('logger',['ros2','run','vel_ros_bridge','logger','--output',d/'logger.json','--lag','.04'])
    bridge=ps.start('bridge',['ros2','run','vel_ros_bridge','bridge','--port',str(port),'--stats',d/'bridge.json'])
    wait_for(lambda:(d/'bridge.json').exists() and read(d/'bridge.json')['state']=='READY');time.sleep(2)
    client.wait_for(['start','stop','set_rate','get_status'])
    assert control('set_rate',20)['period']==20;assert control('get_status')['running']==0
    assert control('start')['running']==1
    wait_for(lambda:read(d/'bridge.json')['valid']>=16)
    stopped=control('stop');assert stopped['running']==0
    count=control('get_status')['sent'];time.sleep(.25);assert control('get_status')['sent']==count
    assert count<256
    assert control('set_rate',1,success=False)['code']==2
    assert control('set_rate',60)['period']==60
    assert control('start')['running']==1
    wait_for(lambda:(d/'logger.json').exists() and read(d/'logger.json')['complete'],30)
    status=control('get_status');assert status['sampled']==256 and status['sent']==256 and status['running']==0 and status['errors']==0,status
    assert control('stop')['running']==0
    b=read(d/'bridge.json');l=read(d/'logger.json');rows=read(d/'logger.json.records')
    assert b['valid']==256 and b['discarded']==0 and b['duplicates']==0 and l['received']==256 and l['per_sensor']==[128,128] and not l['errors']
    assert l['max_delivery_delay_ms']>100,l
    assert len(rows)==256 and {p['id'] for p in rows}=={0,1}
    periods=[]
    for sid in [0,1]:
        series=[p for p in rows if p['id']==sid];assert [p['seq'] for p in series]==list(range(128))
        assert all(p['milli']==(25000 if sid==0 else 30000)+p['seq']*(25 if sid==0 else 40) for p in series)
        diffs=[b['mcu_ms']-a['mcu_ms'] for a,b in zip(series,series[1:])]
        assert any(10<=delta<=40 for delta in diffs) and any(50<=delta<=90 for delta in diffs),diffs
        periods.append({'sensor':sid,'min_delta_ms':min(diffs),'last_delta_ms':diffs[-1],'set_rate_effect_observed':True})
    assert all(p.poll() is None for p in [qemu,logger,bridge])
record('stage5_3/e2e_gate',{'status':'PASS','classification':'REAL ROS 2 and REAL QEMU separate processes','domain':env['ROS_DOMAIN_ID'],'mcu_sampled':status['sampled'],'mcu_sent':status['sent'],'bridge_valid':b['valid'],'logger_received':l['received'],'per_sensor':[128,128],'start_stop_set_rate_get_status':True,'stop_quiet':True,'invalid_rate_nack':True,'periods':periods,'lagging_consumer':'40ms per temperature callback; reliable depth512; complete record matching','max_delivery_delay_ms':l['max_delivery_delay_ms'],'bridge_stats':b,'external_logs':str(d),'processes_reaped':True})
print('ROS_QEMU_256_E2E_PASS',d)
