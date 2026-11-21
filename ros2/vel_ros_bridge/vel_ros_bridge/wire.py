import struct,zlib,time
TYPES={'HELLO':1,'SENSOR_DATA':2,'START':3,'STOP':4,'SET_RATE':5,'GET_STATUS':6,'ACK':7,'NACK':8,'ERROR':9}
NAMES={v:k for k,v in TYPES.items()}
def cobs(raw):
    out=bytearray([0]);pos=0;code=1
    for b in raw:
        if b==0:out[pos]=code;pos=len(out);out.append(0);code=1
        else:out.append(b);code+=1
    out[pos]=code;return bytes(out)
def uncobs(data):
    out=bytearray();i=0
    while i<len(data):
        code=data[i];i+=1
        if code==0 or i+code-1>len(data):raise ValueError('COBS')
        chunk=data[i:i+code-1]
        if 0 in chunk:raise ValueError('embedded zero')
        out.extend(chunk);i+=code-1
        if code!=255 and i<len(data):out.append(0)
    return bytes(out)
def encode(kind,seq,payload=b'',sid=0,version=1):
    if len(payload)>64:raise ValueError('payload too long')
    raw=struct.pack('<BBBBIH',version,TYPES.get(kind,kind) if not isinstance(kind,str) else TYPES[kind],sid,0,seq,len(payload))+payload
    return cobs(raw+struct.pack('<I',zlib.crc32(raw)))+b'\0'
def decode(data):
    if len(data)>=82:raise ValueError("oversize")
    raw=uncobs(data)
    if len(raw)<14:raise ValueError('short')
    version,kind,sid,flags,seq,n=struct.unpack('<BBBBIH',raw[:10])
    if n>64 or len(raw)!=14+n:raise ValueError('length')
    if zlib.crc32(raw[:-4])!=struct.unpack('<I',raw[-4:])[0]:raise ValueError('CRC')
    if version!=1 or flags!=0:raise ValueError('version')
    payload=raw[10:-4];p={'type':NAMES.get(kind,'UNKNOWN'),'request':seq,'raw_type':kind,'payload':payload.hex()}
    if kind==2:
        if n!=8:raise ValueError('data length')
        ms,milli=struct.unpack('<Ii',payload);p.update(id=sid,seq=seq,mcu_ms=ms,milli=milli)
    if kind in [7,8]:
        if n!=20:raise ValueError('ACK length')
        cmd,code,running,_pad,period,sampled,sent,errors=struct.unpack('<BBBBIIII',payload)
        p.update(command=cmd,code=code,ok=kind==7 and code==0,running=running,period=period,sampled=sampled,sent=sent,errors=errors)
    return p
def encode_command(p):
    return encode(p['type'],p['request'],struct.pack('<I',p['value']&0xffffffff) if p['type']=='SET_RATE' else b'')
class Parser:
    def __init__(self):self.buffer=bytearray();self.dropping=False;self.errors=0;self.last=time.monotonic()
    def expire(self):
        if self.buffer and time.monotonic()-self.last>.3:self.buffer.clear();self.errors+=1
    def feed(self,chunk):
        self.expire();out=[]
        for b in chunk:
            self.last=time.monotonic()
            if b==0:
                if self.buffer and not self.dropping:
                    try:out.append(decode(bytes(self.buffer)))
                    except ValueError:self.errors+=1
                self.buffer.clear();self.dropping=False
            elif not self.dropping:
                self.buffer.append(b)
                if len(self.buffer)>=82:self.buffer.clear();self.dropping=True;self.errors+=1
        return out
