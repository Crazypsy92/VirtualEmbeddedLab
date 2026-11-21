from stage7_support import *
rc,log=run('interfaces_host',['colcon','build','--base-paths',ROOT/'micro_ros/stage7_interfaces','--build-base',WS/'host_build','--install-base',WS/'host_install','--packages-select','vel_recovery_interfaces','--cmake-args','-DBUILD_TESTING=OFF'],rosenv(),180,WS)
record('interfaces_host',{'status':'PASS' if rc==0 else 'FAIL','log':str(log)});raise SystemExit(rc)
