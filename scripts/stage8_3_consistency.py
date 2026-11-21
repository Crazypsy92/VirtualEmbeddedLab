from stage8_3_runtime import *
from pymodbus.client import ModbusSerialClient
with Lab('status-crosscheck') as lab:
 m=lab.master();m.call('write_registers',0,[0,20,600,0xa6,50]);os.write(lab.control,b'L');wait_for(lambda:'INPUT bits=11' in lab.slave_log.read_text(),3)
 tcp={'holding':m.call('read_holding_registers',0,count=8).registers,'status':m.call('read_input_registers',0,count=1).registers,'io':m.call('read_input_registers',6,count=2).registers,'coils':m.call('read_coils',0,count=8).bits[:8]};assert tcp['io']==[11,166];m.close();lab.relay.close();lab.relay=None
 d=ModbusSerialClient(lab.slave_paths[1],baudrate=115200,parity='N',timeout=.5,retries=0);assert d.connect()
 try:
  rs=[d.read_holding_registers(0,count=8,device_id=1),d.read_input_registers(0,count=1,device_id=1),d.read_input_registers(6,count=2,device_id=1),d.read_coils(0,count=8,device_id=1)];assert not any(v.isError() for v in rs);direct={'holding':rs[0].registers,'status':rs[1].registers,'io':rs[2].registers,'coils':rs[3].bits[:8]};assert tcp==direct
 finally:d.close()
 lab.connect_relay();m=lab.master(base=3000);assert m.call('read_input_registers',6,count=2).registers==[11,166]
 data=lab.proof();data.update(status='PASS',tests=1,cases=[{'name':'independent_device_status_crosscheck','status':'PASS'}],tcp=tcp,direct_rtu=direct);record('rtu/consistency',data)
print('DEVICE_STATUS_CROSSCHECK_PASS')
