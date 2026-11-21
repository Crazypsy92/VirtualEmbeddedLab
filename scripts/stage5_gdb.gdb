set pagination off
set confirm off
set remotetimeout 5
break uart_rx_marker
continue
printf "UART_RX_BYTES=%u\n", g_rx_bytes
info registers r0 r1 r2 r3 sp pc xpsr
bt
python
assert int(gdb.parse_and_eval('g_rx_bytes'))>0
end
delete breakpoints
break command_marker
continue
printf "COMMAND_REACHED running=%u\n", g_running
bt
delete breakpoints
break uart_tx_marker
continue
python
import sys,json
sys.path.insert(0, str(gdb.current_progspace().filename.rsplit('/build/',1)[0])+'/ros2/vel_ros_bridge')
from vel_ros_bridge.wire import decode
n=int(gdb.parse_and_eval('g_tx_length'))
addr=int(gdb.parse_and_eval('&g_tx_frame[0]'))
frame=bytes(gdb.selected_inferior().read_memory(addr,n))
assert frame[-1]==0 and 0<n<=82
p=decode(frame[:-1]);assert p['type']=='ACK' and p['request']==1 and p['command']==1 and p['running']==0
print('VALID_TX_HELLO_ACK',json.dumps(p))
end
delete breakpoints
break fetch
continue
printf "SENSOR_API_RUNNING=%u RX_FRAMES=%u\n", g_running, g_rx_frames
bt
python
assert int(gdb.parse_and_eval('g_running'))==1
assert int(gdb.parse_and_eval('g_rx_frames'))>=2
end
delete breakpoints
break uart_tx_marker
continue
python
n=int(gdb.parse_and_eval('g_tx_length'));addr=int(gdb.parse_and_eval('&g_tx_frame[0]'))
p=decode(bytes(gdb.selected_inferior().read_memory(addr,n))[:-1])
assert p['type']=='SENSOR_DATA' and p['id']==0 and p['seq']==0 and p['milli']==25000
assert int(gdb.parse_and_eval('g_sampled'))==1
assert int(gdb.parse_and_eval('g_errors'))==0
print('VALID_TX_SENSOR_DATA',json.dumps(p))
print('STAGE5_GDB_PASS')
end
delete breakpoints
detach
quit
