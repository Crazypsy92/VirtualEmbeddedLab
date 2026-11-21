import os,sys,pathlib,json,struct,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
from stage8_3_runtime import Lab,frame,receive,R,wait_for
from stage8_3_1_relay import DelayRelay
result={}
with Lab('late-before-fix') as lab:
 m=lab.master();m.call('write_registers',1,[17,600]);m.close();lab.relay.close();lab.relay=DelayRelay(lab.slave_paths[1],lab.gateway_paths[1],lab.d);lab.relay.pause_responses()
 s=lab.raw();start=time.monotonic();s.sendall(frame(100,1,3,struct.pack('>HH',1,1)));a=receive(s);assert a==(100,1,b'\x83\x0b'),a;assert lab.relay.pending
 s.sendall(frame(101,1,3,struct.pack('>HH',2,1)))
 wait_for(lambda: any(e['direction']==1 and e['hex']=='01030002000125ca' for e in lab.relay.events),2)
 with lab.relay.mutex:
  held=b''.join(lab.relay.pending)
  assert held[:7]==bytes.fromhex('01030200117848'),held.hex()
  lab.relay.write(1,held[:7])
  lab.relay.pending=[held[7:]] if held[7:] else []
 b=receive(s);lab.relay.release_responses();correct=(b==(101,1,b'\x03\x02\x02\x58'))
 result={'status':'PASS' if correct else 'FAIL','request_A_response':[a[0],a[1],a[2].hex()],'request_B_response':[b[0],b[1],b[2].hex()],'expected_B_hex':'03020258','elapsed':time.monotonic()-start,'actual_logs':str(lab.d),'defect':'stale response A accepted for request B' if b[2]==bytes.fromhex('03020011') else None}
p=R/'evidence/stage8_3_1/rtu_late/before_fix.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));raise SystemExit(0 if correct else 1)
