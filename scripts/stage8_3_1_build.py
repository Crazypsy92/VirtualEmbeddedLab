"""Independent long-running test builds; original slave source remains unchanged."""
import pathlib,subprocess,os,json,hashlib,time
from vel_env import ROOT as R, native_build, work
W=work('gateway_stage8_3_1_ws');(W/'runs').mkdir(parents=True,exist_ok=True)
port=int(os.environ.get('VEL_GATEWAY_PORT','15021'))
source=R/'zephyr/apps/modbus_rtu_slave';app=W/'long_slave_app';app.mkdir(exist_ok=True);s=(source/'src/main.c').read_text();assert s.count('k_uptime_get()<120000')==1;(app/'main.c').write_text(s.replace('k_uptime_get()<120000','k_uptime_get()<2100000'));(app/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.20)\nfind_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})\nproject(longevity_slave C)\ntarget_sources(app PRIVATE main.c)\ntarget_include_directories(app PRIVATE ${ZEPHYR_BASE}/subsys/modbus)\nzephyr_link_libraries(-Wl,--wrap=modbus_server_handler)\ntarget_compile_options(app PRIVATE -Wall -Wextra -Werror)\n')
proof={'original_slave_sha256':hashlib.sha256((source/'src/main.c').read_bytes()).hexdigest(),'long_slave_sha256':hashlib.sha256((app/'main.c').read_bytes()).hexdigest(),'only_slave_change':'runtime guard 120000 -> 2100000 ms; protocol, callbacks and register definitions unchanged','builds':{}}
for name,project,args in [('gateway',R/'zephyr/apps/modbus_tcp_gateway',['-DGW_PORT='+str(port),'-DGW_RUNTIME_MS=2100000']),('slave',app,['-DCONF_FILE='+str(source/'prj.conf'),'-DDTC_OVERLAY_FILE='+str(source/'app.overlay')])]:
 log=W/'runs'/('build-'+name+'-'+str(time.monotonic_ns())+'.log')
 with log.open('w') as f:
  native_build(project,W/(name+'_build'),args,log=f)
 proof['builds'][name]={'exit':0,'log':str(log)}
(W/'port.json').write_text(json.dumps({'port':port}));d=pathlib.Path(os.environ.get('VEL_STAGE8_3_1_EVIDENCE',R/'evidence/stage8_3_1'))/'build';d.mkdir(exist_ok=True,parents=True);(d/'profiles.json').write_text(json.dumps(proof,indent=2)+'\n');print('LONG_BUILDS_PASS')
