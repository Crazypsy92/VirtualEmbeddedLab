from stage8_3_runtime import *
import argparse,struct,statistics
ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['protocol','concurrency','fault','all'],default='all');mode=ap.parse_args().mode;cases=[]
if mode in ['protocol','all']:
 with Lab('protocol') as lab:
  m=lab.master();m.call('write_coil',0,True);assert m.call('read_coils',0,count=1).bits[0]
  bits=[True,False,True,False,True,True,False,True];m.call('write_coils',0,bits);assert m.call('read_coils',0,count=8).bits[:8]==bits
  m.call('write_register',1,20);assert m.call('read_holding_registers',1,count=1).registers==[20]
  values=[1,10,500,0x69,100];m.call('write_registers',0,values);assert m.call('read_holding_registers',0,count=5).registers==values;assert m.call('read_input_registers',7,count=1).registers==[0x69]
  for bitmap in [0,15,5,10,0]:
   before=lab.slave_log.read_text().count('INPUT bits=');os.write(lab.control,bytes([65+bitmap]));wait_for(lambda:lab.slave_log.read_text().count('INPUT bits=')>before,3);assert m.call('read_discrete_inputs',0,count=4).bits[:4]==[bool(bitmap&(1<<i)) for i in range(4)]
  cases.append({'name':'eight_functions_gpio','status':'PASS'})
  # Independent serial master is allowed exclusive bus access only after relay detach.
  m.close();lab.relay.close();lab.relay=None
  from pymodbus.client import ModbusSerialClient
  direct=ModbusSerialClient(lab.slave_paths[1],baudrate=115200,parity='N',timeout=.5,retries=0);assert direct.connect();v=direct.read_holding_registers(0,count=5,device_id=1);assert not v.isError() and v.registers==values;direct.close();lab.connect_relay();m=lab.master(base=1000);assert m.call('read_holding_registers',0,count=5).registers==values
  cases.append({'name':'tcp_rtu_consistency','status':'PASS'})
  raw=lab.raw();packet=frame(301,1,3,struct.pack('>HH',0,1));raw.sendall(packet[:3]);time.sleep(.02);raw.sendall(packet[3:8]);time.sleep(.01);raw.sendall(packet[8:]);assert receive(raw)==(301,1,b'\x03\x02\x00\x01')
  raw.sendall(b''.join(frame(i,1,3,struct.pack('>HH',1,1)) for i in range(302,307)));assert [receive(raw)[0] for _ in range(5)]==list(range(302,307));raw.close();cases.append({'name':'tcp_fragment_coalesced_stream','status':'PASS'})
  for i in range(250):
   mask=i&255;m.call('write_register',3,mask);assert m.call('read_input_registers',7,count=1).registers==[mask];m.call('write_coil',i%8,True);assert m.call('read_coils',i%8,count=1).bits[0]
  final=m.call('read_holding_registers',0,count=8).registers;assert final[3]==(249|(1<<(249%8)))
  cases.append({'name':'1000_mixed_transactions','status':'PASS','transactions':1000,'final':final})
  data=lab.proof();data.update(status='PASS',cases=list(cases),times=[t for c in lab.clients for t in getattr(c,'times',[])],wire=[t for c in lab.clients for t in getattr(c,'wire',[])]);record('tcp/protocol',data)
if mode in ['concurrency','all']:
 with Lab('concurrency') as lab:
  children=[lab.ps.start('tcp_master'+str(i),[V,R/'host/modbus_tcp_master/client.py',str(lab.port),str(i),lab.d/('master'+str(i)+'.json')]) for i in range(4)]
  for p in children:assert p.wait(30)==0
  results=[json.loads((lab.d/('master'+str(i)+'.json')).read_text()) for i in range(4)];assert all(v['transactions']==80 for v in results)
  ids=[{t['tid'] for t in v['times']} for v in results];assert len(set.union(*ids))==320
  time.sleep(1);text=lab.gateway_log.read_text();assert 'max_active=1' in text
  m=lab.master();assert m.call('read_coils',0,count=4).bits[:4]==[True]*4;m.close();time.sleep(.2);baseline_fds=len(list(pathlib.Path('/proc/'+str(lab.gateway.pid)+'/fd').iterdir()))
  for i in range(20):
   probe=lab.master(base=50000+i*10);probe.call('read_holding_registers',0,count=1);probe.close()
  time.sleep(.3);final_fds=len(list(pathlib.Path('/proc/'+str(lab.gateway.pid)+'/fd').iterdir()));assert final_fds<=baseline_fds+1,(baseline_fds,final_fds)
  case={'name':'four_independent_tcp_masters','status':'PASS','transactions':320,'fd_baseline':baseline_fds,'fd_after_20_reconnects':final_fds};cases.append(case);data=lab.proof();data.update(status='PASS',cases=[case],client_results=results);record('concurrency/acceptance',data)
if mode in ['fault','all']:
 with Lab('fault') as lab:
  # No master initially; gateway and slave stay alive.
  time.sleep(.3);assert lab.gateway.poll() is None and lab.slave.poll() is None
  m=lab.master();assert m.call('read_holding_registers',0,count=1).registers==[1];m.close()
  for packet in [struct.pack('>HHHBB',1,1,2,1,3),struct.pack('>HHHBB',1,0,1,1,3),struct.pack('>HHHBB',1,0,255,1,3)]:
   s=lab.raw();s.sendall(packet);assert s.recv(1)==b'';s.close()
  s=lab.raw();s.sendall(frame(2,2,3,struct.pack('>HH',0,1)));assert receive(s)==(2,2,b'\x83\x0a');s.sendall(frame(3,1,0x41,b'\x00\x00\x00\x01'));assert receive(s)==(3,1,b'\xc1\x01');s.close()
  # Real disconnect with queued work. New connection must never receive old IDs.
  s=lab.raw();s.sendall(frame(400,1,3,struct.pack('>HH',0,1)));s.close();m=lab.master(base=500);assert m.call('read_holding_registers',0,count=1).registers==[1];m.close()
  s=lab.raw();s.sendall(b'\x00\x01');time.sleep(1.3);assert s.recv(1)==b'';s.close()
  lab.relay.close();lab.relay=None;s=lab.raw();s.sendall(frame(600,1,6,struct.pack('>HH',1,25)));assert receive(s)==(600,1,b'\x86\x0b');s.close();lab.connect_relay();m=lab.master(base=650);assert m.call('read_holding_registers',1,count=1).registers==[10];m.close()
  # Burst beyond the real bounded queue while the downstream byte relay is detached.
  lab.relay.close();lab.relay=None;s=lab.raw();s.sendall(b''.join(frame(i,1,3,struct.pack('>HH',0,1)) for i in range(700,724)));responses=[receive(s) for _ in range(24)];assert {v[0] for v in responses}==set(range(700,724));assert any(v[2]==b'\x83\x06' for v in responses);assert all(v[2] in [b'\x83\x06',b'\x83\x0b'] for v in responses);s.close();lab.connect_relay()
  # Stop and restart the actual slave process and attach its newly created UART.
  lab.relay.close();lab.relay=None;os.killpg(lab.slave.pid,signal.SIGTERM);lab.slave.wait(3);os.close(lab.control);lab.control=None
  s=lab.raw();s.sendall(frame(800,1,3,struct.pack('>HH',0,1)));assert receive(s)==(800,1,b'\x83\x0b');s.close();lab.start_slave();lab.connect_relay();m=lab.master(base=850);assert m.call('read_holding_registers',0,count=1).registers==[1];m.close()
  # Restart the gateway process; old connections must not survive, new sockets work.
  lab.relay.close();lab.relay=None;os.killpg(lab.gateway.pid,signal.SIGTERM);lab.gateway.wait(3);lab.start_gateway();lab.connect_relay();m=lab.master(base=900);assert m.call('read_holding_registers',0,count=1).registers==[1];m.close()
  case={'name':'socket_serial_process_fault_matrix','status':'PASS','queue_overload_responses':[[tid,u,pdu.hex()] for tid,u,pdu in responses],'hidden_retries':False};cases.append(case);data=lab.proof();data.update(status='PASS',cases=[case]);record('fault/acceptance',data)
record('tests_'+mode,{'status':'PASS','cases':cases,'tests':len(cases)});print('GATEWAY_TESTS_PASS',mode,len(cases))
