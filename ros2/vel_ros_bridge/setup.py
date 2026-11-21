from setuptools import setup
setup(name='vel_ros_bridge',version='0.1.0',packages=['vel_ros_bridge'],data_files=[('share/ament_index/resource_index/packages',['resource/vel_ros_bridge']),('share/vel_ros_bridge',['package.xml'])],entry_points={'console_scripts':['bridge=vel_ros_bridge.bridge:main','logger=vel_ros_bridge.logger:main']})
