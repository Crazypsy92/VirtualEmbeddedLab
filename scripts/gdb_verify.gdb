set pagination off
set confirm off
set print pretty on
set remotetimeout 5
python
import gdb
import struct
def value(expr): return int(gdb.parse_and_eval('(unsigned long)(' + expr + ')'))
def require(condition, message):
    if not condition: raise gdb.GdbError('ASSERT FAIL: ' + message)
    gdb.write('ASSERT PASS: ' + message + '\n')
def stop_at(symbol, initial=False):
    address = value('(unsigned int)&' + symbol) & ~1
    if not (initial and value('$pc') == address):
        bp = gdb.Breakpoint('*' + hex(address), temporary=True)
        gdb.execute('continue')
    require(value('$pc') == address, 'breakpoint ' + symbol)
def reg(expr):
    gdb.write(expr + ' = ' + str(gdb.parse_and_eval(expr)) + '\n')
stop_at('Reset_Handler', initial=True)
gdb.execute('info registers')
require(0x203FC000 <= value('$sp') <= 0x20400000, 'initial MSP range')
# Dirty RAM proves startup copies .data and clears .bss, independent of QEMU zero fill.
inferior = gdb.selected_inferior()
a,b = value('&_sdata'), value('&_edata')
inferior.write_memory(a, bytes([0xA5])*(b-a))
a,b = value('&_sbss'), value('&_ebss')
inferior.write_memory(a, bytes([0xDE])*(b-a))
pc = value('$pc')
gdb.execute('stepi')
require(value('$pc') != pc, 'single instruction advanced PC')
stop_at('main')
require(value('data_probe[0]') == 0x12345678 and value('data_probe[3]') == 0xC003C003, '.data restored after poison')
require(all(value('bss_probe[%d]'%i) == 0 for i in range(16)), '.bss cleared after poison')
gdb.execute('info registers')
for index, ret in enumerate([0xFFFFFFF9, 0xFFFFFFFD]):
    stop_at('svc_dispatch')
    gdb.execute('info registers')
    require(value('$r1') == ret, 'SVC EXC_RETURN ' + hex(ret))
    frame = value('$r0')
    words = struct.unpack('<8I', bytes(inferior.read_memory(frame,32)))
    require(words[0] == 0x13579BDF and words[7] & 0x01000000, 'SVC real basic frame and challenge')
    require(value('$xpsr') & 0x1ff == 11, 'SVC active exception 11')
    require(frame == value('$psp' if index else '$msp'), 'hardware frame agrees with PSP/MSP')
    if index: require(value('&psp_stack[0]') <= value('$psp') < value('&psp_stack[256]'), 'PSP within dedicated stack')
    gdb.execute('x/8wx $r0')
    gdb.execute('info registers')
stop_at('pendsv_dispatch')
require(value('$r1') == 0xFFFFFFF9, 'PendSV returns via MSP')
require(value('$xpsr') & 0x1ff == 14, 'PendSV active exception 14')
gdb.execute('x/8wx $r0')
stop_at('SysTick_Handler')
require(value('$xpsr') & 0x1ff == 15, 'SysTick active exception 15')
gdb.execute('info registers')
stop_at('completion_marker')
require(value('startup_ok') == 1, 'startup runtime check')
require(value('ticks') >= 5, 'SysTick incremented')
require(value('svc_count') == 2 and value('svc_msp_seen') == 1 and value('svc_psp_seen') == 1, 'SVC MSP and PSP counts')
require(value('pendsv_count') == 1 and value('pendsv_pending_seen') == 1, 'PendSV pending and executed')
require(value('exception_failures') == 0 and value('completion_status') == 0, 'firmware validation status')
gdb.execute('info registers')
gdb.write('GDB_VALIDATION_PASS\n')
end
detach
quit
