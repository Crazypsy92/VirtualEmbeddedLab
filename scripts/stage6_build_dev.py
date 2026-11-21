#!/usr/bin/env python3
from stage6_support import *
identity();assert json.loads((OUT/'stage6_1/host_gate.json').read_text())['status']=='PASS'
env=os.environ.copy()
for key in list(env):
 if key.startswith(('ROS','AMENT','COLCON')) or key in ['CMAKE_PREFIX_PATH','LD_LIBRARY_PATH','PYTHONPATH','VIRTUAL_ENV']:env.pop(key,None)
env.update(PATH='/usr/local/bin:/usr/bin:/bin',PYTHONNOUSERSITE='1',CMAKE_BUILD_PARALLEL_LEVEL='4')
cmd=['colcon','build','--base-paths',*[WS/'sources'/x for x in ['ament_package','ament_index','ament_cmake','ament_cmake_ros']],'--build-base',WS/'dev_build','--install-base',WS/'dev_install','--merge-install','--executor','sequential','--packages-up-to','ament_cmake','ament_cmake_ros','ament_index_python','--packages-ignore','rmw_test_fixture','rmw_test_fixture_implementation','--cmake-args','-DBUILD_TESTING=OFF','-DPython3_EXECUTABLE=/usr/bin/python3','-DCMAKE_POLICY_VERSION_MINIMUM=3.5']
rc,log=run('arm_dev_tools',cmd,env,300)
record('stage6_2/dev_tools',{'status':'PASS' if rc==0 else 'FAIL','classification':'Host ament tools only','external_log':str(log)})
raise SystemExit(rc)
