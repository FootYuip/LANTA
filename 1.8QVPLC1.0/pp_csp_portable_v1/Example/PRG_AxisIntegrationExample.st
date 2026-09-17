(*
	单轴接线示例。不要直接绑定现场地址。
	角度换算、软限位、安全互锁和原Modbus HR/IR打包属于站点适配层。
*)
PROGRAM PRG_AxisIntegrationExample
VAR
	fbAdapter         : FB_ImodePpCspAdapter;
	fbAxis            : FB_Cia402PpCspAxis;
	stConfig          : ST_AxisConfig;
	stPdoIn           : ST_AxisPdoIn;
	stPdoOut          : ST_AxisPdoOut;
	stStatus          : ST_AxisStatus;

	(* 来自原上位机兼容层 *)
	iHostMode         : INT;
	diHostPosition    : DINT;
	diHostVelocity    : DINT;
	xTrajectoryActive : BOOL;
	xTrajectoryValid  : BOOL;
	diTrajectoryPoint : DINT;
	xMotionPermitted  : BOOL;
	xFaultReset       : BOOL;
	diCspEntryTolerance : DINT := DINT#1000;
END_VAR

fbAdapter(
	iMode := iHostMode,
	diPositionCommand := diHostPosition,
	diVelocityCommand := diHostVelocity,
	xTrajectoryActive := xTrajectoryActive,
	xTrajectoryValid := xTrajectoryValid,
	diTrajectoryPoint := diTrajectoryPoint,
	xMotionPermitted := xMotionPermitted,
	xFaultReset := xFaultReset,
	diCspEntryTolerance := diCspEntryTolerance,
	stAxisStatus := stStatus
);

fbAxis(
	stDemand := fbAdapter.stDemand,
	stPdoIn := stPdoIn,
	stConfig := stConfig,
	stPdoOut => stPdoOut,
	stStatus => stStatus
);

(*
	站点接线：
	- 设备树输入PDO -> stPdoIn；stPdoOut -> 设备树输出PDO。
	- stStatus中的实际位置、速度、故障、限位重新打包到原IR。
	- 原iMode仍原样回显，不要把6061直接作为上位机iMode回显。
*)
