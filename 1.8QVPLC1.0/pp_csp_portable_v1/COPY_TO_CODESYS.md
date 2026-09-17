# 复制到蓝塔 CODESYS 项目的位置

当前目录中的文件是可读 ST 源码，不是可以直接覆盖 `.project` 的文本。请在 **蓝塔工程的 Device/Application** 下创建对应对象并粘贴声明/实现；不要覆盖原 `.project` 文件。

## 1. 新建 DUT

在 `Device/Application` 下新建 DUT，名称必须与文件内名称一致：

| 文件 | CODESYS 对象 |
|---|---|
| `DUT/E_Cia402AxisState.st` | `E_Cia402AxisState` |
| `DUT/ST_AxisConfig.st` | `ST_AxisConfig` |
| `DUT/ST_AxisDemand.st` | `ST_AxisDemand` |
| `DUT/ST_AxisPdoIn.st` | `ST_AxisPdoIn` |
| `DUT/ST_AxisPdoOut.st` | `ST_AxisPdoOut` |
| `DUT/ST_AxisStatus.st` | `ST_AxisStatus` |

## 2. 新建通用 FB

在 `Device/Application` 下新建两个 ST Function Block：

| 文件 | CODESYS 对象 |
|---|---|
| `FB/FB_ImodePpCspAdapter.st` | `FB_ImodePpCspAdapter` |
| `FB/FB_Cia402PpCspAxis.st` | `FB_Cia402PpCspAxis` |

## 3. 新建蓝塔绑定对象

| 文件 | 位置/类型 |
|---|---|
| `LANTA/F_LantaStatusWord.st` | `Device/Application`，Function |
| `LANTA/GVL_LantaPpCsp.st` | `Device/Application`，GVL，名称 `GVL_LantaPpCsp` |
| `LANTA/PRG_LantaPpCspBound.st` | `Device/Application`，Program |

不要复制 `Example/PRG_AxisIntegrationExample.st`，它只是通用接线示例。

## 4. 解除旧 PDO 写入者

保留 `El_ctrl_1`、`Az_ctrl_1`、`Ti_ctrl_1`，因为它们仍负责软限位、扫描、自跟踪偏置和最终目标计算；但在三个程序末尾分别停用以下调用：

```st
Axis1_Ctrl(...);
Axis2_Ctrl(...);
Axis3_Ctrl(...);
```

只停用最后的 FB 调用，不删除前面的目标和状态计算。否则旧 FB 与新能力层会同时写 6040/6060/607A，无法保证安全。

## 5. Canopen 任务顺序

保持原有程序顺序，并把 `PRG_LantaPpCspBound` 加在最后：

```text
TimeAdd
AutoTrackingCal
El_ctrl_1
Az_ctrl_1
Ti_ctrl_1
RealTimePosCal
SecurityCheck
PRG_LantaPpCspBound   <- 新增，最后执行
```

周期保持 10 ms，优先级保持原 Canopen 任务设置。

## 6. 三个驱动都要修改的 PDO

当前镜像实测状态：SYNC generation=FALSE，编译定义含 `CANOPEN_NO_SYNCPDOS/CANOPEN_NO_SYNC`，607A RPDO transmission type=254，且没有映射 6061。这种配置不能用于正式 CSP。

每个 eDriver（El/Az/Ti）均需：

1. CANopen Manager 启用 SYNC generation，周期设置为 **10000 μs**，COB-ID 保持 16#80。
2. 607A 所在 RPDO 的 transmission type 改为同步型 **1**。
3. 6064 所在 TPDO 建议改为同步型 **1**。
4. 在 TPDO 中新增 `6061:00 Modes of operation display`，8 bit；蓝塔固定 AT 已确认：
   - EL：`GVL_LantaPpCsp.siElModeDisplay AT %IB22`
   - AZ：`GVL_LantaPpCsp.siAzModeDisplay AT %IB42`
   - TI：`GVL_LantaPpCsp.siTiModeDisplay AT %IB62`
5. 保留 60FF 映射，以继续支持原 `iMode=3` 速度控制。最终固定地址为：
   - EL：`GVL.diElTargetVel AT %QD2`
   - AZ：`GVL.diAzTargetVel AT %QD8`
   - TI：`GVL.diTiTargetVel AT %QD14`
6. PP 的 6081 Profile velocity 已按当前蓝塔过程映像写成固定 AT：
   - EL：`GVL_LantaPpCsp.udiElProfileVelocity AT %QD6`
   - AZ：`GVL_LantaPpCsp.udiAzProfileVelocity AT %QD12`
   - TI：`GVL_LantaPpCsp.udiTiProfileVelocity AT %QD18`

PDO 改完后必须重新检查 I/O 地址，不能假定后续地址一定不移动。优先使用设备树的符号映射列绑定 6061。

当前最终过程映像已经核对为连续、无重叠。原 `GVL` 中 EL 输出地址保持不变；AZ、TI 输出地址必须按下一节整体后移。输入侧原 6041/603F/606C/6064 地址保持不变，新增 6061 使用上述 `%IB22/%IB42/%IB62`。

## 7. 修改原 GVL 的 AZ/TI 输出 AT 地址

修改蓝塔工程原 `GVL` 中以下 AT 地址。三个 6060 模式变量的类型同时由 `UINT` 改为与 PDO 一致的 `SINT`；原程序只进行数值比较和赋值，此类型修正不改变上位机接口。EL 其余输出地址不变。

也可以直接复制 `LANTA/GVL_FinalFromCsv.st` 的全部内容，覆盖候选 CODESYS 工程中原 `GVL` 对象的声明区。该文件由 2026-09-14 导出的 `eDriver_El.csv`、`eDriver_Az.csv`、`eDriver_Ti.csv` 核对生成，不包含 6061/6081；这两个新增对象继续由独立的 `GVL_LantaPpCsp` 绑定，禁止重复声明。

### EL 模式类型修正

```st
siElMode AT %QB6 : SINT;
```

### AZ 输出

```st
bAzCtrlBit0 AT %QX28.0 : BOOL;
bAzCtrlBit1 AT %QX28.1 : BOOL;
bAzCtrlBit2 AT %QX28.2 : BOOL;
bAzCtrlBit3 AT %QX28.3 : BOOL;
bAzCtrlBit4 AT %QX28.4 : BOOL;
bAzCtrlBit5 AT %QX28.5 : BOOL;
bAzCtrlBit7 AT %QX28.7 : BOOL;
bAzCtrlBit8 AT %QX29.0 : BOOL;
siAzMode AT %QB30 : SINT;
diAzTargetVel AT %QD8 : DINT;
diAzTargetPos AT %QD9 : DINT;
diAzTargetAcc AT %QD10 : UDINT;
diAzTargetDec AT %QD11 : UDINT;
```

### TI 输出

```st
bTiCtrlBit0 AT %QX52.0 : BOOL;
bTiCtrlBit1 AT %QX52.1 : BOOL;
bTiCtrlBit2 AT %QX52.2 : BOOL;
bTiCtrlBit3 AT %QX52.3 : BOOL;
bTiCtrlBit4 AT %QX52.4 : BOOL;
bTiCtrlBit5 AT %QX52.5 : BOOL;
bTiCtrlBit7 AT %QX52.7 : BOOL;
bTiCtrlBit8 AT %QX53.0 : BOOL;
siTiMode AT %QB54 : SINT;
diTiTargetVel AT %QD14 : DINT;
diTiTargetPos AT %QD15 : DINT;
diTiTargetAcc AT %QD16 : UDINT;
diTiTargetDec AT %QD17 : UDINT;
```

这些位地址分别对应截图中的 AZ `%QW14` 和 TI `%QW26` 控制字。不要修改原输入反馈地址：AZ 仍为 `%IW12/%IW13/%ID7/%ID8`，TI 仍为 `%IW22/%IW23/%ID12/%ID13`。

## 8. 编译前确认

- `GVL.diEl/Az/TiTargetPos` 仍映射 607A。
- `GVL.b*CtrlBit0..8` 仍映射 6040 对应位。
- `GVL.si*Mode` 仍映射 6060。
- `GVL.b*StsBit*` 仍映射 6041。
- `GVL.di*ActPos`、`di*ActVel`、`e*Errorcode` 仍映射 6064、606C、603F。
- 三轴 6061 已映射到 `GVL_LantaPpCsp`。
- 三轴 6081 已映射到 `GVL_LantaPpCsp`，原60FF映射仍保留。
- 原三个 `AxisX_Ctrl(...)` 调用已停用，新程序是唯一 PDO 写入者。

## 9. 验证顺序

先另存为候选 `.project`，只在候选工程中导入并完整编译。依次验证：上下电、Halt、小角度 PP、PP 固定点切 CSP 保持、CSP 小步连续点、跳变拒绝、短程程引、完整程引。未经这些验证不要替换现场工程。
