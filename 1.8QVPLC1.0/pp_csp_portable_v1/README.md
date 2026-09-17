# PP/CSP 可移植轴控制模块 v1

本目录是独立草案，不修改、不覆盖 `plc-src` 镜像。代码按 CODESYS Structured Text 编写，目标是保留现有上位机的 `iMode` 语义，同时把电机控制改为：

- `iMode=0`：受控停止后下使能；
- `iMode=1`：上使能；
- `iMode=2`：PP 绝对位置指向；
- `iMode=3`：PV/速度模式，保留原上位机手动速度控制；
- `iMode=4`：CSP 程引；进入后先固定保持 PP 预置点，正式轨迹开始后才跟随；
- `iMode=7`：Halt，保持使能；
- `iMode=6`：故障复位请求。

## 分层

```text
原上位机 / Modbus / 本控
        -> FB_ImodePpCspAdapter（兼容 iMode，锁存 PP 预置点）
        -> ST_AxisDemand（与站点无关的绝对计数需求）
        -> FB_Cia402PpCspAxis（唯一 PDO 写入者）
        -> ST_AxisPdoOut（由站点设备树绑定 PDO）
```

`FB_Cia402PpCspAxis` 不引用蓝塔 GVL，也不包含角度、减速比、正负方向或 Modbus 地址，因此可以移植到其他站。站点适配层只负责：

1. 用户角度与电机绝对计数的换算；
2. 软限位、安全联锁、硬限位和急停；
3. 把设备树 PDO 映射到 `ST_AxisPdoIn/ST_AxisPdoOut`；
4. 把 `ST_AxisStatus` 重新打包到原有 IR，原寄存器地址可保持不变。

## PP -> CSP 时序

1. `iMode=2` 时，PP 指向上位机给出的预置点。
2. 适配器持续记住这个 PP 绝对目标。
3. 上位机确认位置误差和速度满足要求后写 `iMode=4`。
4. 在 `iMode=4` 上升沿，适配器把 PP 目标锁存为 `diCspHoldPosition`，此后保持阶段不再修改它。
5. 能力层按 `6060=8 -> 607A=固定预置点 -> 6 -> 7 -> 15` 进入 CSP。
6. `xTrajectoryActive=FALSE` 时，每个周期都把同一个 `diCspHoldPosition` 写入 607A。
7. 到正式任务时间且轨迹有效后，`xTrajectoryActive=TRUE`，才接受绝对 CSP 轨迹点。

保持点禁止使用“实际位置 + 增量”“上一拍目标 + 增量”或不断刷新的轨迹点，否则会形成单向漂移。

## CSP 跳变保护

`diMaxCspStep` 是一个同步周期允许的最大位置增量（计数）。新轨迹点与上一条已接受 CSP 命令的差值超过该值时：

- 不写入异常目标；
- 冻结在上一条已接受目标；
- `xCspStepRejected=TRUE`、`xFault=TRUE`；
- `udiErrorId=16#C501`。

该阈值应按 `最大允许速度 * CSP周期` 计算，并留出合理裕量。能力层必须与 CANopen SYNC 同周期调用。

## PDO 最低要求

输出：6040、6060、607A、6081、6083、6084。  
输入：6041、6061、6064、606C、603F（推荐）。

首次进入 PP 使用：`6060=1 -> 参数/目标 -> 6 -> 7 -> 15 -> 31`。  
首次进入 CSP 使用：`6060=8 -> 固定预置目标 -> 6 -> 7 -> 15`。  
故障复位使用 6040 bit7 的单周期上升沿。

## 文件顺序

在 CODESYS 中建议按以下顺序建立对象：

1. `DUT/E_Cia402AxisState.st`
2. `DUT/ST_AxisConfig.st`
3. `DUT/ST_AxisDemand.st`
4. `DUT/ST_AxisPdoIn.st`
5. `DUT/ST_AxisPdoOut.st`
6. `DUT/ST_AxisStatus.st`
7. `FB/FB_ImodePpCspAdapter.st`
8. `FB/FB_Cia402PpCspAxis.st`
9. `Example/PRG_AxisIntegrationExample.st`（仅接线示例，不应直接用于现场）

## 上报兼容

原上位机所需的位置、速度、模式、故障、限位、电流等 IR 地址不需要改变。建议：

- 原 `iMode` 回显继续回显上位机命令；
- 实际位置/速度继续来自 6064/606C；
- 原“PID使能反馈位”作为兼容位，可定义为该轴位置运动已允许；
- 新增诊断（若有空闲 IR）：CiA-402 状态、6061、603F、CSP准备、CSP保持、CSP跟随、CSP跳变拒绝。

## 尚需现场确认

- 三轴实际 PDO 排列和地址；
- 模式显示 6061 是否已映射；
- CSP SYNC 周期及 CAN 总线负载；
- 各轴计数/度、方向、零偏和软限位；
- Halt 使用控制字 bit8 是否符合当前 eRob 参数配置；
- 603F 厂家错误码与现有 `Error_code` 的映射。

本目录没有执行 CODESYS 导入、编译、PLC 登录或实机运动。
