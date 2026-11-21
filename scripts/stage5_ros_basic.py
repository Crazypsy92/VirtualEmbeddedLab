#!/usr/bin/env python3
from stage5_support import *
import re,sys
identity(); (WS/'runs').mkdir(exist_ok=True)
d=pathlib.Path(tempfile.mkdtemp(prefix='ros-basic-',dir=WS/'runs')); env=rosenv(d)
with Processes(d,env) as ps:
    listener=ps.start('listener',['ros2','run','demo_nodes_py','listener'])
    talker=ps.start('talker',['ros2','run','demo_nodes_cpp','talker'])
    server=ps.start('service',['ros2','run','demo_nodes_cpp','add_two_ints_server'])
    wait_for(lambda:(d/'listener.log').read_text().count('I heard:')>=3,25)
    def graph_list(kind, required):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = run_command(['ros2', kind, 'list', '--no-daemon', '--spin-time', '2.0'],
                                 env, timeout=8)
            with (d/'cli.log').open('a') as log:
                log.write(f"{kind} exit={result.returncode}\n{result.stdout}")
            if result.returncode == 0 and all(item in result.stdout.splitlines() for item in required):
                return result
        raise RuntimeError(f"ROS {kind} discovery incomplete. See {d / 'cli.log'}")

    nodes=graph_list('node', ['/talker', '/listener'])
    topics=graph_list('topic', ['/chatter'])
    service=run_command(['ros2','service','call','/add_two_ints','example_interfaces/srv/AddTwoInts','{a: 19, b: 23}'],env)
    with (d/'cli.log').open('a') as log:
        log.write(service.stdout)
    assert service.returncode==0 and 'sum=42' in service.stdout,service.stdout
    sent=re.findall(r'Hello World: (\d+)',(d/'talker.log').read_text()); received=re.findall(r'Hello World: (\d+)',(d/'listener.log').read_text())
    assert len(received)>=3 and all(x in sent for x in received)
    assert all(p.poll() is None for p in [listener,talker,server])
record('stage5_0/runtime_gate',{'status':'PASS','user':pwd.getpwuid(os.getuid()).pw_name,'python':sys.executable,'ros_distro':env['ROS_DISTRO'],'rmw':env['RMW_IMPLEMENTATION'],'domain':env['ROS_DOMAIN_ID'],'talker_published':len(sent),'listener_received':len(received),'verified_sequences':received,'service_sum':42,'nodes':nodes.stdout.splitlines(),'topics':topics.stdout.splitlines(),'external_logs':str(d),'owned_processes_reaped':True})
print('ROS_BASIC_RUNTIME_PASS',d)
