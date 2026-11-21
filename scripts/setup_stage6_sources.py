#!/usr/bin/env python3
from vel_env import work, nonroot, ros_environment, tool_environment
from pathlib import Path
import sys
"""Acquire official, commit-pinned sources into a separate user workspace."""
import os,pwd,pathlib,json,urllib.request,tarfile,hashlib,concurrent.futures,sys,re,yaml,subprocess,signal,urllib.error
ROOT=pathlib.Path(__file__).resolve().parents[1];WS=work('micro_ros_stage6_ws')
nonroot()
if ros_environment().get('ROS_DISTRO') != 'lyrical':
    raise SystemExit('Stage 6 micro-ROS sources were locked for Lyrical. Set VEL_ROS_SETUP to a compatible Lyrical installation before rebuilding them.')
for d in ['downloads','sources','runs']:(WS/d).mkdir(parents=True,exist_ok=True)
specs=[('spdlog','gabime/spdlog','v1.9.2'),('micro_ros_setup','micro-ROS/micro_ros_setup','lyrical'),('micro_ros_agent','micro-ROS/micro-ROS-Agent','lyrical'),('zephyr_module','micro-ROS/micro_ros_zephyr_module','kilted'),('microxrcedds_agent','eProsima/Micro-XRCE-DDS-Agent','v3.0.2'),('microcdr','eProsima/Micro-CDR','v2.0.2'),('microxrcedds_client','eProsima/Micro-XRCE-DDS-Client','v3.0.2'),('rclc','eProsima/rclc','lyrical'),('micro_ros_msgs','micro-ROS/micro_ros_msgs','lyrical'),('rmw_microxrcedds','micro-ROS/rmw-microxrcedds','lyrical'),('rosidl_typesupport_microxrcedds','micro-ROS/rosidl_typesupport_microxrcedds','lyrical'),('common_interfaces','ros2/common_interfaces','lyrical'),('rcl_interfaces','ros2/rcl_interfaces','lyrical'),('unique_identifier_msgs','ros2/unique_identifier_msgs','lyrical')]
if '--arm' in sys.argv:
 assert json.loads((ROOT/'evidence/stage6/stage6_1/host_gate.json').read_text())['status']=='PASS'
 official=yaml.safe_load(urllib.request.urlopen('https://raw.githubusercontent.com/ros2/ros2/lyrical/ros2.repos',timeout=30).read())['repositories']
 for key in ['ament/ament_cmake','ament/ament_package','ament/ament_index','ros2/ament_cmake_ros','ros2/rmw','ros2/rosidl_defaults','ros2/rosidl','ros2/rmw_implementation','ros2/rcl_logging','ros2/rosidl_core','ros2/ros2_tracing','ros2/rosidl_dynamic_typesupport']:
  item=official[key];repo=item['url'].removeprefix('https://github.com/').removesuffix('.git');name=key.split('/')[-1]
  ref='5f4ace0288ecf942307ed62b9239ab5986884676' if name=='rosidl' else item['version']
  specs.append((name,repo,ref))
 for name in ['rcl','rcutils','rosidl_typesupport']:
  specs.append((name+'_arm','micro-ROS/'+name,'lyrical'))
lock=ROOT/'micro_ros/dependencies.lock.json';old=json.loads(lock.read_text()) if lock.exists() else {}
def get(spec):
 name,repo,ref=spec;entry=old.get(name)
 if not entry:
  req=urllib.request.Request(f'https://api.github.com/repos/{repo}/commits/{ref}',headers={'User-Agent':'VirtualEmbeddedLab-Stage6'})
  if re.fullmatch('[0-9a-f]{40}',ref):sha=ref
  else:
   try:sha=json.loads(urllib.request.urlopen(req,timeout=30).read())['sha']
   except urllib.error.HTTPError as error:
    if error.code!=403:raise
    process=subprocess.Popen(['git','ls-remote','https://github.com/'+repo+'.git','refs/heads/'+ref],stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:output,errors=process.communicate(timeout=90)
    except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait();raise
    if process.returncode:raise RuntimeError(errors.decode())
    sha=output.decode().split()[0];assert re.fullmatch('[0-9a-f]{40}',sha)
  entry={'repository':'https://github.com/'+repo,'requested_ref':ref,'commit':sha}
 else:sha=entry['commit']
 archive=WS/'downloads'/(name+'-'+sha+'.tar.gz');url=f'https://codeload.github.com/{repo}/tar.gz/{sha}'
 if not archive.exists():archive.write_bytes(urllib.request.urlopen(url,timeout=60).read())
 digest=hashlib.sha256(archive.read_bytes()).hexdigest()
 if entry.get('archive_sha256'):assert digest==entry['archive_sha256'],name
 entry.update(archive_sha256=digest,archive_url=url);target=WS/'sources'/name
 if not target.exists():
  staging=WS/'sources'/(name+'-extract');staging.mkdir(exist_ok=True)
  with tarfile.open(archive) as tar:tar.extractall(staging,filter='data')
  children=list(staging.iterdir());assert len(children)==1;children[0].rename(target);staging.rmdir()
 return name,entry
results={};fail=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
 futures={pool.submit(get,spec):spec[0] for spec in specs}
 for future in concurrent.futures.as_completed(futures):
  try:name,entry=future.result();results[name]=entry;print(name,entry['commit'],flush=True)
  except Exception as e:fail.append({'name':futures[future],'error':repr(e)});print(futures[future],repr(e),flush=True)
old.update(results);lock.write_text(json.dumps(old,indent=2)+'\n');(WS/'runs/source_errors.json').write_text(json.dumps(fail,indent=2)+'\n')
if fail:raise SystemExit(1)
