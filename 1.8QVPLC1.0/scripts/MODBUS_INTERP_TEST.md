# 程引插值 Modbus 联调（192.168.1.30）

PLC 为 **Modbus TCP 从站**，端口 **502**。电脑必须为 **Master**。

## 1. 电脑网络

- PC 网卡设为 `192.168.1.x`（与 PLC 同网段），掩码 `255.255.255.0`
- `ping 192.168.1.30` 通后再跑脚本

## 2. CODESYS（仅看插值，不让天线走）

在线 Login 后，在监视表**准备**并设为：

| 变量 | 值 |
|------|-----|
| `GVL.bLocalCtrl` | **FALSE**（远控） |
| `GVL.bTimeSwich` | **TRUE**（用上位机 UTC） |

**不要**在线使能俯仰/方位伺服；`HR[7]` 脚本默认不写 PID 使能位。

仍须 `iMode=4` 才会计算插值（由脚本写 HR[8]、HR[19]）。

## 3. 运行脚本

```bash
pip install pymodbus
cd d:\1.8QVPLC1.0
python scripts/modbus_master_chengyin_test.py
```

可选参数：

```bash
python scripts/modbus_master_chengyin_test.py --table-steps 10 --dt-ms 100 --sweep-steps 50
```

## 4. 脚本做什么

1. **阶段1**：连推 10 个递增 `UTC_Orbit`（HR[45..48]）+ 俯仰/方位角 → 填满 `aUTC_TIME[]`
2. **阶段2**：只改 HR[0..3] `UTC_New`，在表时间范围内扫描 → `rInterElPos` / `rInterAzPos` 应连续变化

## 5. 成功判据

| 监视变量 | 期望 |
|----------|------|
| `Modbus_Slave.aUTC_TIME[10]` | 等于最后一次下发的轨道 UTC |
| `RealTimePosCal.rInterElPos` | 阶段2 随时间变化 |
| `RealTimePosCal.rInterAzPos` | 阶段2 随时间变化 |
| `RealTimePosCal.iErrcode` | 0（107=表空） |
| 编码器 `rFctPosReal_*` | 可不动 |

## 6. Modbus Poll 用户

- Connection: **TCP/IP Client**，IP `192.168.1.30`，Port `502`，Unit ID `1`
- 写 **Holding Registers** 从地址 **0** 起（若工具用 40001，则地址 0 对应 40001）
- 读 **Input Registers** 从地址 **0** 起，**最多 79 个**（`uiai_number:=79`，读 80 会报 Exception 04）

## 7. 引导文件回放（真实程引 + CSV 落盘）

用上位机导出的 **Tab 分隔引导 TXT** 以 **10ms 实时节拍** 驱动 PLC 插值，并把每步 IR 理论角写入 CSV。

### 7.1 文件列约定

| 列号（0 起） | 含义 | 说明 |
|-------------|------|------|
| 0 | Unix 毫秒时间 | 与第 7 列 ISO 一致；相邻行间隔应为 100ms |
| 3 | 方位 | **PLC 坐标**，原样下发 → `aPosCmd_2` |
| 4 | 俯仰 | **PLC rPosCmd 坐标**，原样（脚本不做 +90°） |

### 7.2 前置条件（与 §2 相同）

1. CODESYS **Login + Run**
2. `GVL.bTimeSwich := TRUE`，`GVL.bLocalCtrl := FALSE`
3. 双轴伺服**不使能**（仅验证插值）
4. `ping 192.168.1.30` 通，502 可用

### 7.3 运行

```bash
pip install pymodbus
cd d:\1.8QVPLC1.0
python scripts/modbus_replay_guidance.py ^
  --input "c:\path\to\未识别_..._文件引导_....txt" ^
  --host 192.168.1.30 ^
  --output scripts/output/guidance_replay_20260519.csv
```

常用参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--interval` | `0.01` | 步进间隔（秒），0.01 = 10ms 实时 |
| `--max-steps` | 无 | 调试子集，例如 `--max-steps 500` 只跑 5s |
| `--output` | `scripts/output/guidance_replay_<stem>.csv` | 未指定时自动命名 |

**预计时长**：约 `(末时刻−首时刻)/10` 步 × 10ms ≈ 文件时长（例：4741 点 / 100ms 间隔 ≈ 8 分钟）。

### 7.4 每步行为

- **每 10ms**：写 `HR[0..3] = t_play`，`HR[8]=HR[19]=4`（程引模式），当前轨道行方位/俯仰
- **每 100ms**（`t_play` 命中文件第 1 列）：额外写 `HR[45..48]` 推入新 `UTC_Orbit`
- **每步**：读 IR[0..78]（最多 79 寄存器），反算 `rInterAz` / `rInterEl` 写入 CSV

共享编解码见 `scripts/modbus_plc_codec.py`（与 `modbus_master_chengyin_test.py` 一致）。

### 7.5 CSV 列说明

| 列 | 含义 |
|----|------|
| `step` | 步号 k，`t_play = t0 + k×10` |
| `t_play_ms` | 本步写入的 `UTC_New` |
| `file_row` / `file_t_ms` | 当前采用的引导行号与时间 |
| `az_cmd` / `el_cmd` | 本步下发的命令角（PLC 坐标） |
| `orbit_push` | 1=本步推了新轨道 UTC |
| `ir_t_ms` | IR[0..3]：PLC `(dRealTime−8h)` 毫秒 |
| `rInterAz` / `rInterEl` | 由 IR[75..78] 反算，与监视里理论角一致 |
| `delta_ms` | `ir_t_ms − t_play_ms`（通常约 +100~200ms，属 PLC 固定偏移） |
| `note` | `orbit` / `clamp?` / 读 IR 错误等 |

### 7.6 限制说明

- Modbus **无法直接读** `RealTimePosCal.rInterElPos` 内部变量；CSV 为 IR 理论角反算值
- `t_play` 超出 10 点 FIFO 约 900ms 窗时，IR 角可能钉在末点（CSV `note` 可为 `clamp?`）
- 完整回放 Modbus 负载高；调试用 `--max-steps`

### 7.7 验收

- 回放中 `Modbus_Slave.aUTC_TIME[10]` 随文件推进递增
- CSV 中 `rInterAz` / `rInterEl` 随 `t_play_ms` 连续变化
- `delta_ms` 大致稳定在 +100~200ms
- 首末 `t_play_ms` 与引导文件时间范围一致

### 7.8 IR 角一直是 -20 / 100

多为曾跑过 `modbus_master_chengyin_test.py`，表里是**当前墙钟**时刻；引导文件是**任务 UTC**（如 2026-05-19），`UTC_Orbit` **必须大于表中全部 10 个时刻** 才会入表，旧表不会被更小时间覆盖。

回放脚本默认会先 **清表 + 预填引导前 10 点**；若仍不对，PLC 冷启动后再跑。跳过清表：`--no-reset-table`（仅连续同文件续跑时用）。

## 8. 故障排查

- 连不上：PLC 未 RUN、IP 不对、PC 不在 192.168.1.x
- 表不更新：`UTC_Orbit_New` 必须**严格大于** `aUTC_TIME[1..10]` 全部旧值（联调墙钟 > 引导任务时间会卡死）
- 插值不变：双轴 mode 非 4、`bTimeSwich=FALSE` 且无 GNSS、`aUTC_TIME` 全 0
