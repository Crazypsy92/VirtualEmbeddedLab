from stage8_3_1_runtime import *
import argparse,random
ap=argparse.ArgumentParser();ap.add_argument('--mode',required=True);mode=ap.parse_args().mode
with Lab(mode) as lab:
 time.sleep(1.1);start=time.monotonic();samples=[lab.sample()];cases=[];detail={}
 if mode in ['tid','stress','endurance']:
  deadline=start+1800 if mode=='endurance' else None
  jobs=[lab.ps.start('client'+str(i),[V,R/'scripts/stage8_3_1_worker.py',mode,str(lab.port),str(i),lab.d,*([str(deadline)] if deadline else [])]) for i in range(4)]
  limit=start+(1900 if deadline else 900);next_sample=start+60;next_delay=start+120
  while any(p.poll() is None for p in jobs):
   assert time.monotonic()<limit,'group deadline'
   if time.monotonic()>=next_sample:samples.append(lab.sample());next_sample+=60
   if deadline and time.monotonic()>=next_delay:
    lab.relay.pause_responses();time.sleep(.1);lab.relay.release_responses();next_delay+=120
   if any(p.poll() not in [None,0] for p in jobs):raise AssertionError('client failed: '+str(lab.d))
   time.sleep(.05)
  assert all(p.wait(2)==0 for p in jobs)
  results=[json.loads((lab.d/('client'+str(i)+'.json')).read_text()) for i in range(4)];total=sum(p['transactions'] for p in results)
  if mode=='tid':assert total==400
  elif mode=='stress':assert total==10000
  else:assert time.monotonic()-start>=1800
  m=lab.master();coils=m.call('read_coils',0,count=8).bits[:8];holding=m.call('read_holding_registers',0,count=8).registers
  if mode=='tid':assert coils==[bool(p['final_two_coils']&(1<<bit)) for p in results for bit in range(2)]
  if mode!='tid':
   assert coils[:4]==[p['final_coil'] for p in results];assert holding[5]==sum(p['writes'] for p in results)
  m.close();time.sleep(.1);samples.append(lab.sample());assert samples[-1]['fds']<=samples[0]['fds']+1
  detail.update(clients=results,transactions=total,coils=coils,holding=holding,wall_seconds=time.monotonic()-start)
  cases.append({'name':mode,'status':'PASS'})
 elif mode=='rtu-late':
  m=lab.master();m.call('write_registers',1,[17,600]);m.close();s=lab.raw()
  for i,delay in enumerate([.1,.4,.47,.65,.8,.7,.7,.7]):
   lab.relay.pause_responses()
   t=time.monotonic()
   s.sendall(frame(100+i*2,1,3,struct.pack('>HH',1,1)))
   wait_for(lambda:bool(lab.relay.pending),2)
   request_b=frame(101+i*2,1,3,struct.pack('>HH',2,1))
   if delay>.5:
    a=receive(s)
    assert a==(100+i*2,1,b'\x83\x0b'),a
    s.sendall(request_b)
    # B is already queued over TCP when the stale RTU frame is released.
    time.sleep(max(0,delay-(time.monotonic()-t)))
    lab.relay.release_responses()
   else:
    time.sleep(max(0,delay-(time.monotonic()-t)))
    lab.relay.release_responses()
    a=receive(s)
    assert a[0:2]==(100+i*2,1)
    assert a[2]==b'\x03\x02\x00\x11' or (delay>=.4 and a[2]==b'\x83\x0b'),a
    s.sendall(request_b)
   b=receive(s);assert b==(101+i*2,1,b'\x03\x02\x02\x58'),b;cases.append({'name':'delay_'+str(delay),'status':'PASS','response_A':a[2].hex(),'response_B':b[2].hex(),'delay_seconds':delay})
  s.close()
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
   if time.monotonic()-samples[-1]['monotonic']>=60:samples.append(lab.sample())
  cases.append({'name':'100_recovery_rounds','status':'PASS'});detail['rounds']=rounds
 else:raise ValueError(mode)
 samples.append(lab.sample());proof=lab.proof();proof.update(status='PASS',cases=cases,tests=len(cases),samples=samples,detail=detail,wall_seconds=time.monotonic()-start);record(mode.replace('-','_')+'/acceptance',proof)
print('STAGE8_3_1_GROUP_PASS',mode,len(cases))
