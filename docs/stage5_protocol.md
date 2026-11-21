# Stage 5 有界 UART 协议 v1

业务通道为 UART1，115200；UART0 为控制台。C 编解码器与 Python 编解码器使用相同 Golden Vector，协议不直接发送 C 结构体。

## 帧布局

原始帧按小端序编码；COBS(raw) 后附 `00` 分隔。最大 payload64字节，原始帧最大78字节，实际 COBS+分隔最大80字节，静态分配82字节并拒绝达到/超过接收上界的畸形输入。

| 偏移 | 字节数 | 内容 |
|---|---|---|
| 0 | 1 | version=1 |
| 1 | 1 | type |
| 2 | 1 | device/sensor ID |
| 3 | 1 | reserved=0 |
| 4 | 4 | 请求或记录 seq |
| 8 | 2 | payload长度0–64 |
| 10 | N | payload |
| 10+N | 4 | CRC32，小端 |

CRC-32/ISO-HDLC：反射多项式0xEDB88320，init=0xFFFFFFFF，refin/refout=true，xorout=0xFFFFFFFF，覆盖header+payload。`123456789`结果0xCBF43926。

HELLO，ID0，seq1，空payload的 Golden Vector（含结尾分隔）：`0301010102010101010105aec46fd000`。

## 消息

| type | 方向 | payload |
|---|---|---|
| 1 HELLO | Host→MCU | 空；MCU先返回关联ACK，再返回HELLO，payload u32版本1 |
| 2 SENSOR_DATA | MCU→Host | u32 MCU uptime(ms) + i32温度(milli-C)，ID0/1，seq各0–127 |
| 3 START | Host→MCU | 空；继续已有会话，不清零计数 |
| 4 STOP | Host→MCU | 空；ACK后不再采样 |
| 5 SET_RATE | Host→MCU | u32 period_ms，合法10–200 |
| 6 GET_STATUS | Host→MCU | 空 |
| 7 ACK / 8 NACK | MCU→Host | u8原命令、u8 code、u8 running、u8保留，随后u32 period、sampled、sent、errors（共20字节） |
| 9 ERROR | MCU→Host | u32接收错误代码：坏帧/上界/接收超时，seq0 |

ACK/NACK 的header seq引用请求；Bridge核对请求序号和原命令。NACK code2=参数或长度错误，3=零/旧序号/不同内容重复，4=未知命令。命令ID只能0。接收错误增加MCU errors并停止采样，发ERROR；恢复解析不等于当前数据会话完整成功。

## 序号与同步

单请求串行发送，Host seq按uint32增加并跳过0。MCU最近一个请求以seq和命令/payload指纹缓存响应，同内容重复重发缓存ACK而不重复执行；同seq不同内容NACK。先后关系按有符号32位差判断，只允许前进小于2^31；因此0xFFFFFFFF→1可用。一次会话禁止跨越半个序号空间跳跃。Host不启用自动重试，GET_STATUS/STOP有明确ACK超时。

数据序号独立于请求序号，按每个sensor严格连续，重复或缺口均使Bridge进入ERROR，不虚构缺失值或丢失后宣称256全成功。时间为32位MCU uptime，本阶段60秒会话不发生回绕；长期运行需要新的扩展时间策略。

超时300ms清除部分帧，超长帧丢弃直到00，坏COBS/长度/CRC/版本拒绝。下一个完整帧可重新解码；Bridge错误状态保持，完整采集通过新会话恢复。Python解析器单次输入可以多帧，分片积累有固定上限；C实现所有输出与解码长度有界。

`scripts/stage5_protocol_test.py`实际运行C ASan/UBSan及10000个确定性畸形输入，交叉检查0/1/8/32/64 payload、分片/合并、CRC、长度、版本、COBS、超长、超时和同步。`stage5_uart_test.py`在真实QEMU中验证命令RX、ACK TX、重复、乱序及重启；`stage5_faults.py`在真实链路代理注入传感器故障，暂停MCU验证无ACK，并独立测试异常退出。
