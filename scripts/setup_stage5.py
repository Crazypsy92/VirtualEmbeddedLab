#!/usr/bin/env python3
"""Check the installed ROS 2 environment with the compatible system Python."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from vel_env import nonroot, ros_environment, ros_setup, work


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true",
                        help="verify the configured ROS installation before use")
    parser.add_argument("--prepare", action="store_true", help="initialize the local working directory")
    parser.parse_args()
    nonroot()
    workspace = work("ros2_stage5_ws")
    (workspace / "runs").mkdir(parents=True, exist_ok=True)
    if workspace.stat().st_uid != os.getuid():
        raise SystemExit(f"Workspace is not owned by the active user: {workspace}")
    env = ros_environment()
    cmd = ["/usr/bin/python3", "-c",
           "import json,sys,rclpy; from sensor_msgs.msg import Temperature; "
           "print(json.dumps({'python':sys.executable,'rclpy':rclpy.__file__}))"]
    check = subprocess.run(cmd, env=env, check=True, capture_output=True, text=True, timeout=20)
    tools = {name: shutil.which(name, path=env["PATH"]) for name in ["ros2", "colcon"]}
    if not all(tools.values()):
        raise SystemExit(f"ROS tools missing in {ros_setup()}: {tools}")
    print(json.dumps({"user": workspace.owner(), "home": str(Path.home()),
                      "workspace": str(workspace), "ros_distro": env["ROS_DISTRO"],
                      "setup": str(ros_setup()), "tools": tools, **json.loads(check.stdout)}, indent=2))


if __name__ == "__main__":
    main()
