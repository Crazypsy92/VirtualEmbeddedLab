#!/usr/bin/env python3
from stage6_arm_runtime import *
identity();assert json.loads((OUT/'stage6_2/runtime_gate.json').read_text())['status']=='PASS'
d=pathlib.Path(tempfile.mkdtemp(prefix='arm-gdb-',dir=WS/'runs'));env=runtime_env(d);port=freeport();stub=freeport();ps=Processes(d,env);relay=None
try:
 q=ps.start('qemu',qemu(port)+['-S','-gdb',f'tcp:127.0.0.1:{stub}']);relay=Relay(port,d)
 agent=ps.start('agent',[WS/'host_install/lib/micro_ros_agent/micro_ros_agent','serial','--dev',relay.device,'-b','115200','-v','6'])
 peer=ps.start('ros_peer',['/usr/bin/python3',ROOT/'scripts/stage6_arm_peer.py',d/'peer.json']);time.sleep(.5)
 rc,log=run('arm_gdb',['gdb-multiarch','-q','-nx','-batch',ELF,'-ex',f'target remote 127.0.0.1:{stub}','-x',ROOT/'scripts/stage6_gdb.gdb'],env,45)
 text=log.read_text();assert rc==0 and 'STAGE6_GDB_PASS' in text,text[-5000:]
 assert q.poll() is None and agent.poll() is None
 assert 'FATAL' not in (d/'qemu.log').read_text() and 'HardFault' not in (d/'qemu.log').read_text()
 record('stage6_2/gdb_gate',{'status':'PASS','breakpoints':['uxr_create_session','rclc_executor_spin_some','rmw_publish','command_marker'],'command_confirmed':42,'official_arm_backtraces':True,'external_log':str(log),'external_logs':str(d),'uart_bytes':relay.counts,'no_fatal_or_hardfault_observed':True})
 print('STAGE6_ARM_GDB_PASS')
finally:
 ps.close()
 if relay:relay.close()
