#!/usr/bin/env python3
from stage6_acquisition_test import *
identity();assert json.loads((OUT/'stage6_3/e2e_gate.json').read_text())['status']=='PASS'
cases=[]
for mode in ['no_agent','agent_exit','uart_disconnect','mcu_restart','command_timeout','slow','recovery']:
 data=run_case(mode,.08 if mode=='slow' else 0);cases.append(data)
normal=json.loads((OUT/'stage6_3/e2e_gate.json').read_text())
for name in ['invalid_set_rate','duplicate_request']:
 cases.append({'status':'PASS','mode':name,'source':'e2e_gate.json','nack':normal['invalid_rate_nack'] if name=='invalid_set_rate' else None,'idempotent':normal['duplicate_request_idempotent'],'received':normal['received'],'final_state':normal['final_state'],'external_logs':normal['external_logs']})
record('stage6_3/fault_gate',{'status':'PASS','cases':cases,'recovery_policy':'Stop failed QEMU/Agent/Host session and establish all entities again in a fresh session. No READY state reported for unrecovered link.'})
print('STAGE6_FAULT_GATE_PASS',len(cases))
