# 上位机 Modbus 模拟控制

脚本 `modbus_host_sim.py` 按 PLC 源码 `Modbus_Slave` / `SecurityCheck` / `*_ctrl_1` 的映射，模拟真实上位机下发命令。

## 前置条件

| 项 | 要求 |
|----|------|
| 网络 | PC `192.168.1.x`，`ping 192.168.1.30` |
| 远控 | CODESYS 监视 **`GVL.bLocalCtrl := FALSE`** |
| 程引 | **`GVL.bTimeSwich := TRUE`**（用上位机 UTC） |
| 安全 | 限位、人员、负载；先小角度、低速度试 |
| 主站 | **同时只跑一个**写 HR 的脚本/工具 |

## iMode 与 PLC 行为（HR[8] 方位 / HR[19] 俯仰）

| iMode | 名称 | 天线行为 |
|-------|------|----------|
| 0 | 下电 | DS402 断使能 |
| 1 | 上电 | DS402 三步使能序列 |
| 2 | 指向 | PID 跟踪 `rPosCmd`（HR 方位/俯仰角） |
| 3 | 速度 | 跟踪 `rVelCmd` |
| 4 | 程引 | PID 跟踪 `RealTimePosCal` 插值 + 偏置 |
| 7 | halt | 快速停止 |

## 主要 HR 映射

| 寄存器 | 内容 |
|--------|------|
| HR[0..3] | `UTC_New`（Unix ms，程引时间轴） |
| HR[7] | 控制字：B12 俯仰 PID、B13 方位 PID |
| HR[8..10] | 方位 iMode + 位置 |
| HR[19..21] | 俯仰 iMode + 位置 |
| HR[45..48] | `UTC_Orbit`（轨道表，须严格递增） |
| HR[61..62] | 指向最大速度 Az/El（×1000） |

角度编码与 `modbus_plc_codec.py` 一致：方位 `az_plc` 原样；俯仰为 PLC `rPosCmd`（约 93~180）。

## 典型流程

### 1. 只读状态

```cmd
python scripts\modbus_host_sim.py status
```

### 2. 指向模式（到指定角）

```cmd
python scripts\modbus_host_sim.py power-on --az 0 --el 120 --wait 3
python scripts\modbus_host_sim.py point --az 120.5 --el 100 --duration 30
python scripts\modbus_host_sim.py halt
python scripts\modbus_host_sim.py power-off
```

`point` 默认写 HR[7] PID 使能位；仅测命令不加 `--no-pid-bits`。

### 3. 程引 + 引导文件

```cmd
python scripts\modbus_host_sim.py track ^
  --input "scripts\未识别_..._文件引导_....txt" ^
  --max-steps 500
```

**真运动**（伺服已上电、PID 使能）：

```cmd
python scripts\modbus_host_sim.py power-on --wait 3
python scripts\modbus_host_sim.py track --input "scripts\....txt" --motion --max-steps 500
```

与 `modbus_replay_guidance.py` 相同：默认清表+预填；`--motion` 才置 PID 位。

## IR 反馈（status）

| IR | 含义 |
|----|------|
| [5] | `Error_code` |
| [10]/[27] | 方位/俯仰 iMode |
| [13..14] | 方位实际位置 |
| [30..31] | 俯仰实际位置 |
| [75..78] | 程引理论角 |

## 与现有脚本关系

| 脚本 | 用途 |
|------|------|
| `modbus_host_sim.py` | **完整上位机模拟**：上电/指向/程引/状态 |
| `modbus_replay_guidance.py` | 仅程引回放 + CSV（默认不动天线） |
| `modbus_master_chengyin_test.py` | 联调插值（简单两阶段） |

共享编解码：`modbus_plc_codec.py`。

## Web 界面

```cmd
pip install -r scripts\requirements-ui.txt
python scripts\modbus_web_app.py
```

浏览器打开 **http://127.0.0.1:8765**：输入 Az/El、连接 PLC、上电 / 指向 / 停止 / 下电，状态约 1s 自动刷新。

说明见同目录 `modbus_web_app.py` 注释；运动前须 `GVL.bLocalCtrl=FALSE`。
