# 当前 WSL 的 ROS 2 环境

Bridge-Ubuntu-24.04 使用普通用户 bridge。已安装的 ROS 2 发行版为 Jazzy，通过 /opt/ros/jazzy/setup.bash 加载。使用 /usr/bin/python3 3.12，rclpy 由已安装的 ROS 包提供。工程的 ROS 2 工作区由 scripts/vel_env.py 定位，默认是 build/workspaces/ros2_stage5_ws。colcon 构建、安装和运行日志均写入该工作区。

从工程根目录执行 python3 scripts/vel.py ros 检查用户、HOME、工作区所有者、ROS_DISTRO 和 rclpy。需要选择其他已安装的发行版时，将 VEL_ROS_SETUP 指向对应的 setup.bash。此检查不会执行系统安装。

旧 Ubuntu 的 Lyrical 安装属于历史环境。Stage 6/7 的 micro-ROS 历史验收需要匹配原依赖锁和 ROS 发行版。本机 Jazzy 的 Stage 5 运行结果单独记录。
