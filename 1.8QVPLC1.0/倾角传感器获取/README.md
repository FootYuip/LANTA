# 倾角传感器获取

BWM427S 倾角传感器 + PLC 倾斜轴自动扫描与斜面分析。

## 设备

| 设备 | 默认地址 |
|------|----------|
| PLC Modbus TCP | `192.168.1.30:502` |
| BWM427S（485 转以太网） | `192.168.1.168:10123` |

## 前置条件

- CODESYS：`GVL.bLocalCtrl = FALSE`（远控）
- **仅一个 Modbus 写主站**：原上位机断开或停止写 HR
- 倾斜扫描前确认机械无干涉（Ti 约 ±190° 软限位）
- `pip install pymodbus`（自动扫描需要）

## 脚本

| 文件 | 用途 |
|------|------|
| `read_inclinometer.py` | 读传感器 X/Y |
| `survey_record.py` | 手动输入角度逐点采集 |
| **`auto_tilt_survey.py`** | **自动：仅 Ti −180→0→180，步距 15°，到位 &lt;0.05° 后每点停 10s** |
| `analyze_survey.py` | CSV 分析 → `records/analysis_*/` |

## 自动倾斜扫描

**Web 一键（推荐）**：在项目根目录运行 `python scripts/modbus_web_app.py`，浏览器打开控制页，在「倾斜轴一键扫描」区填写传感器 IP 后点 **一键倾斜扫描**。全程仅写倾斜轴 HR，不对方位/俯仰上电或操作。

**命令行**：

```cmd
cd /d D:\1.8QVPLC1.0\倾角传感器获取
pip install pymodbus
python auto_tilt_survey.py --dry-run
python auto_tilt_survey.py --plc-host 192.168.1.30 --sensor-host 192.168.1.168
```

常用参数：

| 参数 | 默认 | 说明 |
|------|------|------|
| `--step` | 15 | 倾斜扫描步距 |
| `-d` / `--dwell` | 10 | 每点停驻采集秒数 |
| `-i` / `--interval` | 0.5 | 传感器采样间隔 |
| `--ti-vel` | 2 | 倾斜指向速度上限 °/s |
| `--settle-timeout` | 120 | 单点到位超时（超时则跳过该点） |
| `--no-analysis` | — | 只保存 CSV，不自动分析 |

流程：倾斜轴上电 → 25 点逐点指向 → **|实际 Ti − 目标| &lt; 0.05°** 后采 10s → 保存 `records/survey_*.csv` → 自动 `analyze_survey`（报告含倾斜扫描说明）。方位/俯仰轴不参与扫描过程。

## 输出

```
records/
  survey_YYYYMMDD_HHMMSS.csv   # 明细 + 汇总（第一列=倾斜目标角，列名仍为「方位角」以兼容分析）
  survey_YYYYMMDD_HHMMSS.txt
  analysis_YYYYMMDD_HHMMSS/
    report.txt
    images/*.png                 # 需 matplotlib
```

## 手动采集与分析

```cmd
python survey_record.py
python analyze_survey.py records/survey_20260605_162246.csv
```

## 说明

- CSV 列「方位角(度)」在自动扫描中 **数值为倾斜轴目标角 Ti**，分析报告开头有标注。
- 分析模型原按「绕铅垂轴转方位」设计；倾斜扫描时 β 曲线仍有参考价值，几何「上坡方向」请按 Ti 扫描理解。
