from stage8_3_1_runtime import *
import argparse,random
from contextlib import closing
from stage8_3_1_audit import audit_workers, fields, resource_trend
from vel_jobs import install_cancel_handlers

install_cancel_handlers()
ap=argparse.ArgumentParser();ap.add_argument('--mode',required=True);mode=ap.parse_args().mode
with Lab(mode) as lab:
 if mode in ('tid','stress','endurance'):
  with closing(lab.raw()) as warmup:
   warmup.sendall(frame(65000,1,3,struct.pack('>HH',1,1)))
   assert receive(warmup)==(65000,1,b'\x03\x02\x00\x0a')
 time.sleep(1.2)
 start=time.monotonic();samples=[];cases=[];detail={}
 def sample():
  value=lab.sample()
  samples.append(value)
  with (lab.d/'resource_timeline.jsonl').open('a') as file:
   file.write(json.dumps(value)+'\n')
 sample()
 if mode in ['tid','stress','endurance']:
  deadline = None
  jobs=[lab.ps.start('client'+str(i),[V,R/'scripts/stage8_3_1_worker.py',mode,str(lab.port),str(i),lab.d]) for i in range(4)]
  if mode == 'endurance':
   wait_for(lambda: all((lab.d/f'endurance-ready-{i}').exists() for i in range(4)), 15)
   load_start = time.monotonic() + .5
   deadline = load_start + 1801
   temporary = lab.d/'endurance-start.tmp'
   temporary.write_text(json.dumps({'start': load_start, 'end': deadline}))
   temporary.replace(lab.d/'endurance-start.json')
  limit=start+(1900 if deadline else 900)
  next_sample=(load_start if deadline else start)+60
  next_delay=(load_start if deadline else start)+120
  while any(p.poll() is None for p in jobs):
   assert time.monotonic()<limit,'group deadline'
   if time.monotonic()>=next_sample:sample();next_sample+=60
   if deadline and time.monotonic()>=next_delay:
    lab.relay.pause_responses()
    try:
     wait_for(lambda: bool(lab.relay.pending), 3)
     time.sleep(.12)
    finally:
     lab.relay.release_responses()
    next_delay+=120
   if any(p.poll() not in [None,0] for p in jobs):raise AssertionError('client failed: '+str(lab.d))
   time.sleep(.05)
  assert all(p.wait(2)==0 for p in jobs)
  results=[json.loads((lab.d/('client'+str(i)+'.json')).read_text()) for i in range(4)];total=sum(p['transactions'] for p in results)
  if mode=='tid':
   assert total == 400
   all_tids = set()
   for i, result in enumerate(results):
    records = [json.loads(line) for line in pathlib.Path(result['wire']).read_text().splitlines()]
    ids = {row['request_tid'] for row in records}
    assert len(records) == result['transactions'] == 100
    assert ids == set(range(100*i+1,100*i+101)) and not (ids & all_tids)
    for row in records:
     assert row['request_tid'] == row['response_tid'] and row['request_unit'] == row['unit'] == 1
     assert row['request_fc'] == row['response_fc']
    result['tids'] = sorted(ids)
    all_tids.update(ids)
   assert len(all_tids) == 400
   detail['unique_request_tids'] = len(all_tids)
  elif mode=='stress':assert total==10000
  else:
   overlap = min(p['active_finish'] for p in results) - max(p['active_start'] for p in results)
   assert overlap >= 1800, overlap
   detail['four_client_overlap_seconds'] = overlap
  m=lab.master(base=64000);coils=m.call('read_coils',0,count=8).bits[:8];holding=m.call('read_holding_registers',0,count=8).registers
  if mode=='tid':assert coils==[bool(p['final_two_coils']&(1<<bit)) for p in results for bit in range(2)]
  if mode!='tid':
   assert coils[:4]==[p['final_coil'] for p in results];assert holding[5]==sum(p['writes'] for p in results)
  inputs=m.call('read_input_registers',0,count=8).registers
  assert inputs[7] == sum(int(coil) << i for i, coil in enumerate(coils))
  if mode!='tid':
   assert all(holding[p['register_address']] == p['register_value'] for p in results)
  m.close()
  time.sleep(1.2)
  sample()
  assert samples[-1]['connections'] == 0 and samples[-1]['active'] == 0
  assert samples[-1]['fds'] == samples[0]['fds']
  (lab.d/'resource_samples.json').write_text(json.dumps(samples, indent=2))
  assert samples[-1]['Threads'] == samples[0]['Threads'], samples
  detail['audit'] = audit_workers(results, lab.gateway_log, lab.relay, mode)
  detail['inputs'] = inputs
  if deadline:
   pause_events = lab.relay.timeline
   assert len(pause_events) >= 28
   assert all(row['bytes'] > 0 for row in pause_events if row['event'] == 'release')
   assert len(samples) >= 30
   detail.update(response_pauses=pause_events, resources=resource_trend(samples))
  detail.update(clients=results,transactions=total,coils=coils,holding=holding,wall_seconds=time.monotonic()-start)
  cases.append({'name':mode,'status':'PASS'})
 elif mode=='rtu-late':
  with closing(lab.master()) as m:
   m.call('write_registers',1,[17,600])
  s=lab.raw()
  for i,delay in enumerate([.10, .44,.46,.46,.47, .53,.54,.54,.56, .70,.90,.98]):
   first, following = 100+i*2, 101+i*2
   lab.relay.pause_responses()
   t=time.monotonic()
   s.sendall(frame(first,1,3,struct.pack('>HH',1,1)))
   wait_for(lambda:bool(lab.relay.pending),2)
   observed=next(x for x in reversed(lab.relay.events) if x['direction']==1)['monotonic']
   request_b=frame(following,1,3,struct.pack('>HH',2,1))
   if delay>.5:
    a=receive(s)
    assert a==(first,1,b'\x83\x0b'),a
    s.sendall(request_b)
   time.sleep(max(0,delay-(time.monotonic()-observed)))
   lab.relay.release_responses()
   released=lab.relay.timeline[-1]
   assert released['bytes'] == 7, released
   if delay < .5:
    a=receive(s)
    assert a==(first,1,b'\x03\x02\x00\x11'),a
    s.sendall(request_b)
   b=receive(s)
   assert b==(following,1,b'\x03\x02\x02\x58'),b
   cases.append({'name':f'delay_{i+1}', 'status':'PASS','tid_a':first,'tid_b':following,
                 'response_A':a[2].hex(),'response_B':b[2].hex(),'target_seconds':delay,
                 'release_after_first_rtu_tx_seconds':released['monotonic']-observed,
                 'tcp_elapsed_seconds':time.monotonic()-t})
  s.close()
  text=lab.gateway_log.read_text()
  assert text.count('RTU_RESYNCHRONIZED') >= sum(case['target_seconds']>.5 for case in cases)
  rtu={int(line.split()[1].split('=')[1]):line for line in text.splitlines() if line.startswith('RTU ')}
  detail['gateway_dispatch']=[rtu[t] for c in cases for t in (c['tid_a'],c['tid_b'])]
 elif mode=='tcp-stream':
  s=lab.raw();expected=b'\x03\x02\x00\x0a';request=frame(1,1,3,struct.pack('>HH',1,1))
  for kind in ['bytes','random','header_pause','pdu_pause']:
   if kind=='bytes':parts=[bytes([b]) for b in request]
   elif kind=='random':
    rng=random.Random(31);parts=[];n=0
    while n<len(request):size=rng.randint(1,4);parts.append(request[n:n+size]);n+=size
   elif kind=='header_pause':parts=[request[:3],request[3:]]
   else:parts=[request[:9],request[9:]]
   for part in parts:s.sendall(part);time.sleep(.05 if 'pause' in kind else .001)
   assert receive(s)==(1,1,expected);cases.append({'name':kind,'status':'PASS'})
  for n in [2,4,8]:
   s.sendall(b''.join(frame(55,1,3,struct.pack('>HH',1,1)) for _ in range(n)));assert all(receive(s)==(55,1,expected) for _ in range(n));cases.append({'name':'coalesced_'+str(n),'status':'PASS'})
  mixed=[(5,struct.pack('>HH',0,0xff00),b'\x05\x00\x00\xff\x00'),(1,struct.pack('>HH',0,1),b'\x01\x01\x01'),(6,struct.pack('>HH',1,17),b'\x06\x00\x01\x00\x11'),(3,struct.pack('>HH',1,1),b'\x03\x02\x00\x11')]
  s.sendall(b''.join(frame(88,1,fc,payload) for fc,payload,_ in mixed))
  for fc,payload,expected_mixed in mixed:assert receive(s)==(88,1,expected_mixed)
  # Read the actual write side-effect counter: exactly two writes above.
  s.sendall(frame(89,1,3,struct.pack('>HH',5,1)));assert receive(s)==(89,1,b'\x03\x02\x00\x02')
  s.sendall(frame(90,1,6,struct.pack('>HH',1,10)));assert receive(s)==(90,1,b'\x06\x00\x01\x00\x0a')
  cases.append({'name':'mixed_functions_same_tid_write_count','status':'PASS'})
  s.close()
  with closing(lab.raw()) as burst:
   lab.relay.pause_responses()
   burst.sendall(frame(600,1,3,struct.pack('>HH',1,1)))
   wait_for(lambda:bool(lab.relay.pending),2)
   burst.sendall(b''.join(frame(tid,1,3,struct.pack('>HH',1,1)) for tid in range(601,625)))
   busy=[receive(burst) for _ in range(8)]
   assert busy==[(tid,1,b'\x83\x06') for tid in range(617,625)],busy
   lab.relay.release_responses()
   remaining=[receive(burst) for _ in range(17)]
   assert remaining==[(tid,1,expected) for tid in range(600,617)]
  cases.append({'name':'queue_full_and_tid_preserved','status':'PASS','busy_tids':[r[0] for r in busy]})
  original=lab.raw()
  lab.relay.pause_responses()
  original.sendall(frame(800,1,3,struct.pack('>HH',1,1)))
  wait_for(lambda:bool(lab.relay.pending),2)
  original.sendall(frame(801,1,3,struct.pack('>HH',1,1)))
  def received(tid):
   return next((line for line in lab.gateway_log.read_text().splitlines()
                if line.startswith(f'TCP_RECEIVED tid={tid} ')),None)
  wait_for(lambda:received(801),1)
  original.close()
  time.sleep(.08)  # allow the gateway poll loop to retire the old descriptor
  with closing(lab.raw()) as replacement:
   replacement.sendall(frame(802,1,3,struct.pack('>HH',4,1)))
   wait_for(lambda:received(802),1)
   lab.relay.release_responses()
   assert receive(replacement)==(802,1,b'\x03\x02\x00\x64')
  ticks=[fields(received(tid)) for tid in (801,802)]
  assert ticks[0]['slot']==ticks[1]['slot'] and ticks[0]['generation']!=ticks[1]['generation'],ticks
  assert not any(line.startswith('RTU tid=801 ') for line in lab.gateway_log.read_text().splitlines())
  cases.append({'name':'stale_job_and_reused_slot','status':'PASS','tcp_received':ticks})
  with closing(lab.raw()) as bounded:
   def read_words(tid,address):
    bounded.sendall(frame(tid,1,3,struct.pack('>HH',address,1)))
    return receive(bounded)
   baseline=read_words(810,5)
   original_count=int.from_bytes(baseline[2][2:],'big')
   lab.relay.pause_responses()
   bounded.sendall(frame(811,1,6,struct.pack('>HH',1,47)))
   wait_for(lambda:bool(lab.relay.pending),2)
   assert receive(bounded)==(811,1,b'\x86\x0b')
   lab.relay.release_responses()
   assert read_words(812,1)==(812,1,b'\x03\x02\x00\x2f')
   assert read_words(813,5)==(813,1,b'\x03\x02'+struct.pack('>H',original_count+1))
   bounded.sendall(frame(814,1,6,struct.pack('>HH',1,10)))
   assert receive(bounded)==(814,1,b'\x06\x00\x01\x00\x0a')
  dispatch=[fields(line) for line in lab.gateway_log.read_text().splitlines() if line.startswith('RTU tid=811 ')]
  assert len(dispatch)==1 and dispatch[0]['issued']==1 and dispatch[0]['uncertain']==1,dispatch
  cases.append({'name':'timed_out_write_remains_uncertain','status':'PASS','write_dispatch':dispatch[0],
                'readback':47,'counter_before':original_count,'counter_after':original_count+1})
  with closing(lab.raw()) as good, closing(lab.raw()) as other:
   data=struct.pack('>HH',1,1)
   good.sendall(frame(900,1,3,data))
   other.sendall(frame(900,2,3,data))
   assert receive(other)==(900,2,b'\x83\x0a')
   assert receive(good)==(900,1,expected)
  cases.append({'name':'same_tid_on_two_sockets_distinct_units','status':'PASS',
                'tid':900,'valid_unit':1,'unconfigured_unit':2,'exception':10})


  for invalid in [struct.pack('>HHHBB',1,1,2,1,3),struct.pack('>HHHBB',1,0,1,1,3),struct.pack('>HHHBB',1,0,255,1,3)]:
   s=lab.raw();s.sendall(invalid);assert s.recv(1)==b'';s.close()
  slow=lab.raw();slow.sendall(request[:3]);m=lab.master();before=time.monotonic();assert m.call('read_holding_registers',1,count=1).registers==[10];assert time.monotonic()-before<1;m.close();time.sleep(1.2);assert slow.recv(1)==b'';slow.close()
  trickle=lab.raw()
  trickle.sendall(request[:1])
  for byte in request[1:4]:
   time.sleep(.25)
   trickle.sendall(bytes([byte]))
  time.sleep(.45)
  assert trickle.recv(1)==b'', 'partial TCP frame deadline must not slide'
  trickle.close()
  cases.append({'name':'partial_frame_absolute_deadline','status':'PASS'})
  for incomplete in [request[:5],request[:10]]:
   s=lab.raw();s.sendall(incomplete);time.sleep(1.2);assert s.recv(1)==b'';s.close()
  s=lab.raw();s.sendall(request);s.shutdown(socket.SHUT_WR);data=b''
  while True:
   chunk=s.recv(256)
   if not chunk:break
   data+=chunk
  assert data in [b'',frame(1,1,3,b'\x02\x00\x0a')];s.close()
  s=lab.raw();s.setsockopt(socket.SOL_SOCKET,socket.SO_LINGER,struct.pack('ii',1,0));s.sendall(request[:4]);s.close();m=lab.master();assert m.call('read_holding_registers',1,count=1).registers==[10];m.close();cases.append({'name':'fin_rst_halfclose_slow_incomplete','status':'PASS'})
  from stage8_3_1_reconnect import full_slot_reconnect
  cases.append(full_slot_reconnect(lab))
 elif mode=='recovery':
  rng=random.Random(831);rounds=[]
  for i in range(100):
   kind=rng.choice(['disconnect','slave_pause','relay_detach','response_delay','reconnect']);begin=time.monotonic();s=lab.raw()
   if kind in ['disconnect','reconnect']:s.sendall(frame(i+1,1,3,struct.pack('>HH',1,1)));s.close()
   else:
    if kind=='slave_pause':os.killpg(lab.slave.pid,signal.SIGSTOP)
    elif kind=='relay_detach':lab.relay.close();lab.relay=None
    else:lab.relay.pause_responses()
    s.sendall(frame(i+1,1,3,struct.pack('>HH',1,1)));response=receive(s);assert response==(i+1,1,b'\x83\x0b');s.close()
    if kind=='slave_pause':os.killpg(lab.slave.pid,signal.SIGCONT)
    elif kind=='relay_detach':lab.connect_relay()
    else:lab.relay.release_responses()
   m=lab.master();assert m.call('read_holding_registers',1,count=1).registers==[10];m.close();rounds.append({'round':i+1,'kind':kind,'start':begin,'recovered':time.monotonic(),'status':'PASS'})
   if time.monotonic()-samples[-1]['monotonic']>=60:sample()
  cases.append({'name':'100_recovery_rounds','status':'PASS'});detail['rounds']=rounds
  restart_cases=[]
  for target in ('slave','gateway'):
   s=lab.raw()
   s.sendall(frame(970,1,3,struct.pack('>HH',1,1)))
   assert receive(s)==(970,1,b'\x03\x02\x00\x0a')
   restart=lab.restart(target)
   if target=='gateway':
    assert s.recv(1)==b''
    s.close()
    s=lab.raw()
   s.sendall(frame(971,1,3,struct.pack('>HH',1,1)))
   assert receive(s)==(971,1,b'\x03\x02\x00\x0a')
   s.close()
   restart_cases.append(dict(target=target,status='PASS',**restart))
   cases.append({'name':target+'_restart','status':'PASS'})
  detail['restarts']=restart_cases
 else:raise ValueError(mode)
 sample();proof=lab.proof();proof.update(status='PASS',cases=cases,tests=len(cases),samples=samples,detail=detail,wall_seconds=time.monotonic()-start);record(mode.replace('-','_')+'/acceptance',proof)
print('STAGE8_3_1_GROUP_PASS',mode,len(cases))
