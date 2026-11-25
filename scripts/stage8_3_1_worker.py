from stage8_3_1_runtime import *
kind,port,index,folder=sys.argv[1],int(sys.argv[2]),int(sys.argv[3]),pathlib.Path(sys.argv[4]);raw=Raw(port,folder/('wire'+str(index)+'.jsonl'));state=False;expected=0;done=0;writes=0;wires=[str(raw.path)]
try:
 if kind=='tid':
  for ordinal in range(1,101):
   tid = 100 * index + ordinal
   (folder/('ready'+str(index)+'-'+str(ordinal))).touch();deadline=time.monotonic()+10
   while not all((folder/('ready'+str(i)+'-'+str(ordinal))).exists() for i in range(4)):
    if time.monotonic()>deadline:raise TimeoutError('four-client send barrier')
    time.sleep(.001)
   if ordinal%2:
    expected=((ordinal//2)+index)&3;pdu=raw.txn(tid,15,struct.pack('>HHBB',2*index,2,1,expected));assert pdu==bytes([15])+struct.pack('>HH',2*index,2)
   else:assert raw.txn(tid,1,struct.pack('>HH',2*index,2))==bytes([1,1,expected])
   done+=1
 else:
  addr=[0,1,2,4][index];value=[1,17,600,100][index];raw.txn(10000*index+1,6,struct.pack('>HH',addr,value));writes+=1;end=None;i=0
  if kind == 'endurance':
   (folder/f'endurance-ready-{index}').touch()
   wait_for(lambda: (folder/'endurance-start.json').exists(), 15)
   window = json.loads((folder/'endurance-start.json').read_text())
   end = window['end']
   time.sleep(max(0, window['start']-time.monotonic()))
   started = time.monotonic()
  while (i<2500 if kind=='stress' else time.monotonic()<end):
   tid=10000*index+2+i%9000;fn=[1,2,3,4,5,6,15,16][i%8]
   if fn==1:assert raw.txn(tid,fn,struct.pack('>HH',index,1))==bytes([1,1,int(state)])
   elif fn==2:assert raw.txn(tid,fn,struct.pack('>HH',0,4))==bytes([2,1,0])
   elif fn==3:assert raw.txn(tid,fn,struct.pack('>HH',addr,1))==bytes([3,2])+struct.pack('>H',value)
   elif fn==4:
    pdu=raw.txn(tid,fn,struct.pack('>HH',7,1));assert pdu[0:2]==bytes([4,2]);assert bool(int.from_bytes(pdu[2:],'big')&(1<<index))==state
   elif fn==5:
    state=bool((i//8+index)%2);data=struct.pack('>HH',index,0xff00 if state else 0);assert raw.txn(tid,fn,data)==bytes([5])+data
   elif fn==6:assert raw.txn(tid,fn,struct.pack('>HH',addr,value))==bytes([6])+struct.pack('>HH',addr,value)
   elif fn==15:assert raw.txn(tid,fn,struct.pack('>HHBB',index,1,1,int(state)))==bytes([15])+struct.pack('>HH',index,1)
   else:assert raw.txn(tid,fn,struct.pack('>HHBH',addr,1,2,value))==bytes([16])+struct.pack('>HH',addr,1)
   done+=1;i+=1
   if fn in [5,6,15,16]:writes+=1
   if kind=='endurance':
    time.sleep(.4)
    if i%120==0:raw.close();raw=Raw(port,folder/('wire'+str(index)+'-'+str(i)+'.jsonl'));wires.append(str(raw.path))
 (folder/('client'+str(index)+'.json')).write_text(json.dumps({'status':'PASS','transactions':done,'writes':writes,'pid':os.getpid(),'kind':kind,'wire':str(raw.path),'wires':wires,'final_coil':state,'final_two_coils':expected,'register_address':addr if kind!='tid' else None,'register_value':value if kind!='tid' else None,'active_start':started if kind=='endurance' else None,'active_finish':time.monotonic()}))
finally:raw.close()
