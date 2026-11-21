set pagination off
set confirm off
set remotetimeout 5
break uxr_create_session
continue
bt
printf "XRCE_SESSION_INIT_REACHED\n"
delete breakpoints
break rclc_executor_spin_some
continue
bt
python
assert int(gdb.parse_and_eval('g_session'))==1
assert int(gdb.parse_and_eval('g_published'))>0
assert int(gdb.parse_and_eval('g_urx'))>0
assert int(gdb.parse_and_eval('g_utx'))>0
end
printf "EXECUTOR_REAL_ARM_REACHED\n"
delete breakpoints
break rmw_publish
continue
bt
printf "RMW_PUBLISH_REAL_ARM_REACHED\n"
delete breakpoints
break command_marker
continue
bt
info registers pc sp xpsr
python
assert int(gdb.parse_and_eval('g_command'))==42
assert int(gdb.parse_and_eval('g_errors'))==0
print('STAGE6_GDB_PASS')
end
delete breakpoints
detach
quit
