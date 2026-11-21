# Stage 6 兼容性与固定版本

平台为当前 WSL 普通用户、WSL Ubuntu26.04、ROS 2 Lyrical、系统Python3.14。Stage5基线e415aa8，开始时工作树干净。新增依赖和构建位于 `build/workspaces/micro_ros_stage6_ws`，现有ROS/Zephyr工作区保持原位。

## 精确依赖

来源、commit及下载包SHA256见 `micro_ros/dependencies.lock.json`。获取器默认使用锁文件，首次才解析指定分支；构建不自动升级锁定版本。

| 组件 | 选择分支/Tag | package版本 | Commit |
|---|---|---|---|


版本依据：固定micro_ros_setup lyrical清单指定XRCE Client3.0.2、Micro-CDR2.0.2和eProsima/rclc lyrical临时分支；固定micro-ROS Agent7.0.0的SuperBuild指定XRCE Agent3.0.2。没有用当前rolling替代Lyrical。

## 实际兼容问题与处理

1. 官方Zephyr模块的实时仓库默认分支为kilted，main不存在。Stage5调查所读取的网页缓存main链接不能作为本轮源码获取依据；本轮使用实时GitHub API查到的分支和固定commit。该版本README仅声明Zephyr4.0.0/4.1.0测试，**不证明4.4.2 + Lyrical + MPS2已被上游验证**。
2. XRCE Agent3.0.2与Ubuntu系统spdlog/fmt10组合实际编译失败，端点类型无法格式化。使用其官方CMake指定的spdlog1.9.2及内置fmt，在独立agent_install前缀编译安装后重试成功。未修改官方协议/会话算法，未替换系统spdlog/fmt。
3. 当前Zephyr模块构建脚本默认拉rolling，且其示例transport和POSIX配置与4.4.2的兼容性待实际验证。必须固定依赖并完成Host关卡后，才允许进入ARM实验。

## 构建要求与资源边界

现有GCC/G++、CMake4.2.3、Ninja、colcon和Lyrical Fast DDS/Fast CDR可供Host构建，日志记录实际查找结果。只构建必需的生成器、标准消息、rclc、RMW和Agent；不执行系统rosdep安装，不下载板级SDK。Python使用 `/usr/bin/python3`，Zephyr环境单独使用原有venv；后续交叉编译应显式区分Host代码生成工具与ARM目标库。

Host会话通过不代表ARM成功；ARM成功还需检查ELF中的官方Client/RMW/XRCE符号、实际PTY/Serial字节和GDB。当前AN385 RAM映射不可更改，micro-ROS资源预算需由其实际链接和运行结果测量。替代Zephyr4.1仅可在独立实验目录验证，不能归属4.4.2。

## 官方来源

- [micro_ros_setup lyrical](https://github.com/micro-ROS/micro_ros_setup/tree/lyrical)：Host清单和生成静态库路线。
- [micro-ROS Agent lyrical](https://github.com/micro-ROS/micro-ROS-Agent/tree/lyrical)：Agent与XRCE版本选择。
- [Zephyr模块](https://github.com/micro-ROS/micro_ros_zephyr_module/tree/kilted)：已测试版本及默认构建配置。
- [XRCE Agent3.0.2](https://github.com/eProsima/Micro-XRCE-DDS-Agent/tree/v3.0.2)：spdlog、Fast DDS和transport选项。

文档中上游支持声明、实测结果和未验证组合分别标明；运行结果以各关卡JSON为准。


## 2026-10-28 实测更新

Host、ARM最小发布订阅及官方执行路径均已通过。完整锁文件现含30个源码组件，表格早期清单以该锁文件为准。Lyrical的官方generate_lib创建脚本将ROSIDL固定到 `5f4ace0288ecf942307ed62b9239ab5986884676`，本轮遵循该依据，避免新的运行时C库依赖C++异常组件。

系统Newlib没有 `_RETARGETABLE_LOCKING`，Zephyr4.4.2与官方已测试的4.1均要求该接口，因此没有盲目下载替代Zephyr。Minimal libc探针可以编译，但RCUtils实际需要其不提供的stdio功能；最终使用独立构建的Newlib4.4.0（commit `26f7004bf73c421c3fd5e5a6ccf470d05337b435`），启用 `--enable-newlib-retargetable-locking`，只编译Cortex-M3 Thumb一个变体，安装到Stage6私有前缀。未安装SDK、未替换系统C库。源码commit由Git tag解析，固定commit包SHA256见锁文件；Sourceware发布包下载停滞后改用该镜像，不将所读SHA512清单冒充镜像包签名验证。

最小平台适配：`micro_ros/arm/compat/zephyr/posix/time.h`将旧头路径转发到私有Newlib标准time.h；`platform_compat.h`补充Zephyr libc-hooks已导出的isatty声明，并包含正式strings.h；编译优先GCC自带stdatomic，避免选中Newlib面向其他编译器的原子头。`CONFIG_NEWLIB_LIBC_USE_POSIX_LIMITS_H=n`遵循该Kconfig说明，用外部Newlib已有的POSIX limits；`CONFIG_STATIC_INIT_GNU=y`允许ROSIDL静态分发器的初始化段。没有修改任何上游源码算法，`stage6_versions.py`逐文件对照源码包验证。

UART RX采用Zephyr官方中断API+2048字节有界环形缓冲，read回调用信号量提供超时，不因10ms线程休眠拖延单字节接收。TCP中继两端启用TCP_NODELAY，消除小包聚合延迟。原始轮询版曾在实体创建时超时，日志保留；Stage5 COBS协议没有参与这条链路。

当前工具链中ROSIDL C分发器含C++编译单元，最终链接保留ARM unwind扩展段并有orphan-placement警告。资源脚本按ELF实际地址检查它们在原板内存范围内；不宣称构建零警告。应用C代码保持-Wall/-Wextra/-Werror。没有通过关闭错误来伪装成功。


## 完整源码版本清单

多包仓库列出源码package.xml版本；并非其中每个包都参与目标构建，实际选择见脚本与运行日志。

| 组件 | 源码包版本 | Commit |
|---|---|---|



Host UDP端点适配：固定XRCE Agent3.0.2的UDPv4实现绑定INADDR_ANY且CLI无地址选项；本项目只在Host测试Agent进程使用本地bind适配库，限制目标端口为127.0.0.1，并检查内核实际绑定记录。官方协议、会话与DDS实现不改动。对应Host双向会话已重新实际运行通过；ARM Serial/PTY验证不使用该适配器。
