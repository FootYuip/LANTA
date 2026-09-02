# plc-src 同步记录

## 2026-06-03（来自 codesys-export 最新 PLCopen XML）

- **导出时间**: `2026-06-03T09:30:15`（上次镜像: `2026-05-26T11:33:55`）
- **工程**: 1m8QV2026年3月28日 - 信号稳定延长 - 10ms - 副本
- **统计**: POUs 33 · GVL 2 · DUT 4 · UNION 5 · Tasks 5（与上次一致）

### 镜像已更新的 POU（18 个，ST/注释有差异）

`AGCMaxSearch_PB_1`, `AutoTrackingCal`, `Az_Ctrl_FB`, `Az_ctrl_1`, `El_Ctrl_FB`, `El_ctrl_1`, `GPRMC_1`, `Modbus_Slave`, `PID`, `READ_485`, `RealTimePosCal`, `SecurityCheck`, `SpiralScan`, `SpiralScan_1`, `Ti_Ctrl_FB`, `Ti_ctrl_1`, `TimeAdd`, `vpid`

### 变更性质（相对 2026-05-26）

| 类别 | 说明 |
|------|------|
| **结构** | 无增删 POU；GVL 变量表、任务周期绑定未变 |
| **逻辑** | 核心 ST 算法基本未改；主要为块注释、变量说明、分段标题 |
| **Modbus_Slave** | 增补段 A–E 说明；删除未用变量 `Remote_time`；HR[61..63] 程引最大速度映射注释更清晰 |
| **轴控制 FB** | `Az_Ctrl_FB` / `El_Ctrl_FB` / `Ti_Ctrl_FB` 变量区中文说明重写 |
| **时统/程引** | `GPRMC_1`, `TimeAdd`, `RealTimePosCal` 增加程序头注释 |

### 未变部分

- `GVL` / `PersistentVars` / `MODES` 等结构体地址映射
- `PLC_PRG`, `MainTask`/`Canopen`/`SerialCom` 任务表
- CANopen 驱动占位文件

重新生成镜像: `python scripts/export_plcopen_to_txt.py`
