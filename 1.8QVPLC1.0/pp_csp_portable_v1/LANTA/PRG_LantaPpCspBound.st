(*
	蓝塔三轴绑定。放在10ms Canopen任务最后、SecurityCheck之后。
	El/Az/Ti_ctrl_1继续计算目标与偏置，但必须停用末尾AxisX_Ctrl调用，
	保证本程序是PDO唯一写入者。
*)
PROGRAM PRG_LantaPpCspBound
VAR
	fbElAdapter, fbAzAdapter, fbTiAdapter : FB_ImodePpCspAdapter;
	fbElAxis, fbAzAxis, fbTiAxis : FB_Cia402PpCspAxis;
	stElIn, stAzIn, stTiIn : ST_AxisPdoIn;
	stElOut, stAzOut, stTiOut : ST_AxisPdoOut;
	stElStatus, stAzStatus, stTiStatus : ST_AxisStatus;
	stElCfg, stAzCfg, stTiCfg : ST_AxisConfig;
	xOrbitTableValid, xOrbitActive, xRemotePermitted : BOOL;
	iCheck : INT;
	uliUtcNow : ULINT;
	diElPpTarget, diAzPpTarget, diTiPpTarget : DINT;
	diElCspPoint, diAzCspPoint, diTiCspPoint : DINT;
	diElVelCmd, diAzVelCmd, diTiVelCmd : DINT;
END_VAR

(* 轨道有效且当前UTC到达表首点后，才从固定保持切入CSP跟随。 *)
xOrbitTableValid := Modbus_Slave.aUTC_TIME[1] <> ULINT#0;
FOR iCheck := 1 TO 9 DO
	IF Modbus_Slave.aUTC_TIME[iCheck + 1] <= Modbus_Slave.aUTC_TIME[iCheck] THEN
		xOrbitTableValid := FALSE;
	END_IF
END_FOR
IF GVL.dRealTime >= ULINT#28800000 THEN
	uliUtcNow := GVL.dRealTime - ULINT#28800000;
ELSE
	uliUtcNow := ULINT#0;
END_IF
xOrbitActive := xOrbitTableValid AND (RealTimePosCal.iErrcode = 0)
	AND (uliUtcNow >= Modbus_Slave.aUTC_TIME[1]);
xRemotePermitted := (NOT GVL.bLocalCtrl) AND (GVL.Error_code = 0);

(* 当前蓝塔换算：524288 count/rev；俯仰用户角含lrElOffset。 *)
diElPpTarget := LREAL_TO_DINT((REAL_TO_LREAL(GVL.Axis1Remote.rPosCmd) - Modbus_Slave.lrElOffset)
	* LREAL#524288.0 / LREAL#360.0);
diAzPpTarget := REAL_TO_DINT(GVL.Axis2Remote.rPosCmd * REAL#524288.0 / REAL#360.0);
diTiPpTarget := REAL_TO_DINT(GVL.Axis3Remote.rPosCmd * REAL#524288.0 / REAL#360.0);
diElCspPoint := LREAL_TO_DINT((GVL.Axis1Remote.rPIDCmdPos - Modbus_Slave.lrElOffset)
	* LREAL#524288.0 / LREAL#360.0);
diAzCspPoint := LREAL_TO_DINT(GVL.Axis2Remote.rPIDCmdPos * LREAL#524288.0 / LREAL#360.0);
diTiCspPoint := diTiPpTarget; (* 当前倾斜轴无时间轨道，沿用绝对命令。 *)
diElVelCmd := REAL_TO_DINT(GVL.Axis1Remote.rVelCmd * REAL#524288.0 / REAL#360.0);
diAzVelCmd := REAL_TO_DINT(GVL.Axis2Remote.rVelCmd * REAL#524288.0 / REAL#360.0);
diTiVelCmd := REAL_TO_DINT(GVL.Axis3Remote.rVelCmd * REAL#524288.0 / REAL#360.0);

(* 输入PDO物理地址已由原GVL绑定：6041/603F/606C/6064。 *)
stElIn.uiStatusWord := F_LantaStatusWord(GVL.bElStsBit0, GVL.bElStsBit1,
	GVL.bElStsBit2, GVL.bElStsBit3, GVL.bElStsBit10, GVL.bElStsBit12);
stElIn.diActualPosition := GVL.diElActPos;
stElIn.diActualVelocity := GVL.diElActVel;
stElIn.uiDriveErrorCode := GVL.eElErrorcode;
stElIn.siModeDisplay := GVL_LantaPpCsp.siElModeDisplay;
stElIn.xNodeOperational := GVL.eElErrorcode <> UINT#16#8130;
stElIn.xHeartbeatOk := GVL.eElErrorcode <> UINT#16#8130;

stAzIn.uiStatusWord := F_LantaStatusWord(GVL.bAzStsBit0, GVL.bAzStsBit1,
	GVL.bAzStsBit2, GVL.bAzStsBit3, GVL.bAzStsBit10, GVL.bAzStsBit12);
stAzIn.diActualPosition := GVL.diAzActPos;
stAzIn.diActualVelocity := GVL.diAzActVel;
stAzIn.uiDriveErrorCode := GVL.eAzErrorcode;
stAzIn.siModeDisplay := GVL_LantaPpCsp.siAzModeDisplay;
stAzIn.xNodeOperational := GVL.eAzErrorcode <> UINT#16#8130;
stAzIn.xHeartbeatOk := GVL.eAzErrorcode <> UINT#16#8130;

stTiIn.uiStatusWord := F_LantaStatusWord(GVL.bTiStsBit0, GVL.bTiStsBit1,
	GVL.bTiStsBit2, GVL.bTiStsBit3, GVL.bTiStsBit10, GVL.bTiStsBit12);
stTiIn.diActualPosition := GVL.diTiActPos;
stTiIn.diActualVelocity := GVL.diTiActVel;
stTiIn.uiDriveErrorCode := GVL.eTiErrorcode;
stTiIn.siModeDisplay := GVL_LantaPpCsp.siTiModeDisplay;
stTiIn.xNodeOperational := GVL.eTiErrorcode <> UINT#16#8130;
stTiIn.xHeartbeatOk := GVL.eTiErrorcode <> UINT#16#8130;

(* 10ms站点参数。diMaxCspStep为每拍绝对位置增量硬限制。 *)
stElCfg.udiCycleUs := UDINT#10000;
stElCfg.diVelocityZeroLimit := DINT#51;
stElCfg.diPositionTolerance := DINT#146;
stElCfg.diMaxCspStep := DINT#220;
stElCfg.udiProfileVelocity := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis1Remote.Pos_Vel) * LREAL#524288.0 / LREAL#360.0);
stElCfg.udiProfileAcc := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis1Remote.rAcceleration) * LREAL#524288.0 / LREAL#360.0);
stElCfg.udiProfileDec := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis1Remote.rDeceleration) * LREAL#524288.0 / LREAL#360.0);
stElCfg.xRequireModeDisplay := TRUE;
stAzCfg := stElCfg;
stAzCfg.diMaxCspStep := DINT#300;
stAzCfg.udiProfileVelocity := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis2Remote.Pos_Vel) * LREAL#524288.0 / LREAL#360.0);
stAzCfg.udiProfileAcc := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis2Remote.rAcceleration) * LREAL#524288.0 / LREAL#360.0);
stAzCfg.udiProfileDec := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis2Remote.rDeceleration) * LREAL#524288.0 / LREAL#360.0);
stTiCfg := stElCfg;
stTiCfg.diMaxCspStep := DINT#160;
stTiCfg.udiProfileVelocity := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis3Remote.Pos_Vel) * LREAL#524288.0 / LREAL#360.0);
stTiCfg.udiProfileAcc := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis3Remote.rAcceleration) * LREAL#524288.0 / LREAL#360.0);
stTiCfg.udiProfileDec := LREAL_TO_UDINT(REAL_TO_LREAL(GVL.Axis3Remote.rDeceleration) * LREAL#524288.0 / LREAL#360.0);

fbElAdapter(iMode := GVL.Axis1Remote.iMode, diPositionCommand := diElPpTarget, diVelocityCommand := diElVelCmd,
	xTrajectoryActive := xOrbitActive, xTrajectoryValid := xOrbitTableValid,
	diTrajectoryPoint := diElCspPoint, xMotionPermitted := xRemotePermitted,
	xFaultReset := GVL.bError_Reset, diCspEntryTolerance := stElCfg.diPositionTolerance,
	stAxisStatus := stElStatus);
fbElAxis(stDemand := fbElAdapter.stDemand, stPdoIn := stElIn, stConfig := stElCfg,
	stPdoOut => stElOut, stStatus => stElStatus);

fbAzAdapter(iMode := GVL.Axis2Remote.iMode, diPositionCommand := diAzPpTarget, diVelocityCommand := diAzVelCmd,
	xTrajectoryActive := xOrbitActive, xTrajectoryValid := xOrbitTableValid,
	diTrajectoryPoint := diAzCspPoint, xMotionPermitted := xRemotePermitted,
	xFaultReset := GVL.bError_Reset, diCspEntryTolerance := stAzCfg.diPositionTolerance,
	stAxisStatus := stAzStatus);
fbAzAxis(stDemand := fbAzAdapter.stDemand, stPdoIn := stAzIn, stConfig := stAzCfg,
	stPdoOut => stAzOut, stStatus => stAzStatus);

fbTiAdapter(iMode := GVL.Axis3Remote.iMode, diPositionCommand := diTiPpTarget, diVelocityCommand := diTiVelCmd,
	xTrajectoryActive := GVL.Axis3Remote.iMode = 4, xTrajectoryValid := TRUE,
	diTrajectoryPoint := diTiCspPoint, xMotionPermitted := xRemotePermitted,
	xFaultReset := GVL.bError_Reset, diCspEntryTolerance := stTiCfg.diPositionTolerance,
	stAxisStatus := stTiStatus);
fbTiAxis(stDemand := fbTiAdapter.stDemand, stPdoIn := stTiIn, stConfig := stTiCfg,
	stPdoOut => stTiOut, stStatus => stTiStatus);

(* 输出PDO物理绑定。60FF继续用于iMode=3；6081由GVL_LantaPpCsp独立绑定。 *)
GVL.bElCtrlBit0 := (stElOut.uiControlWord AND UINT#16#0001) <> UINT#0;
GVL.bElCtrlBit1 := (stElOut.uiControlWord AND UINT#16#0002) <> UINT#0;
GVL.bElCtrlBit2 := (stElOut.uiControlWord AND UINT#16#0004) <> UINT#0;
GVL.bElCtrlBit3 := (stElOut.uiControlWord AND UINT#16#0008) <> UINT#0;
GVL.bElCtrlBit4 := (stElOut.uiControlWord AND UINT#16#0010) <> UINT#0;
GVL.bElCtrlBit5 := (stElOut.uiControlWord AND UINT#16#0020) <> UINT#0;
GVL.bElCtrlBit7 := (stElOut.uiControlWord AND UINT#16#0080) <> UINT#0;
GVL.bElCtrlBit8 := (stElOut.uiControlWord AND UINT#16#0100) <> UINT#0;
GVL.siElMode := stElOut.siModeOfOperation;
GVL.diElTargetVel := stElOut.diTargetVelocity;
GVL_LantaPpCsp.udiElProfileVelocity := stElOut.udiProfileVelocity;
GVL.diElTargetPos := stElOut.diTargetPosition;
GVL.diElTargetAcc := stElOut.udiProfileAcc;
GVL.diElTargetDec := stElOut.udiProfileDec;

GVL.bAzCtrlBit0 := (stAzOut.uiControlWord AND UINT#16#0001) <> UINT#0;
GVL.bAzCtrlBit1 := (stAzOut.uiControlWord AND UINT#16#0002) <> UINT#0;
GVL.bAzCtrlBit2 := (stAzOut.uiControlWord AND UINT#16#0004) <> UINT#0;
GVL.bAzCtrlBit3 := (stAzOut.uiControlWord AND UINT#16#0008) <> UINT#0;
GVL.bAzCtrlBit4 := (stAzOut.uiControlWord AND UINT#16#0010) <> UINT#0;
GVL.bAzCtrlBit5 := (stAzOut.uiControlWord AND UINT#16#0020) <> UINT#0;
GVL.bAzCtrlBit7 := (stAzOut.uiControlWord AND UINT#16#0080) <> UINT#0;
GVL.bAzCtrlBit8 := (stAzOut.uiControlWord AND UINT#16#0100) <> UINT#0;
GVL.siAzMode := stAzOut.siModeOfOperation;
GVL.diAzTargetVel := stAzOut.diTargetVelocity;
GVL_LantaPpCsp.udiAzProfileVelocity := stAzOut.udiProfileVelocity;
GVL.diAzTargetPos := stAzOut.diTargetPosition;
GVL.diAzTargetAcc := stAzOut.udiProfileAcc;
GVL.diAzTargetDec := stAzOut.udiProfileDec;

GVL.bTiCtrlBit0 := (stTiOut.uiControlWord AND UINT#16#0001) <> UINT#0;
GVL.bTiCtrlBit1 := (stTiOut.uiControlWord AND UINT#16#0002) <> UINT#0;
GVL.bTiCtrlBit2 := (stTiOut.uiControlWord AND UINT#16#0004) <> UINT#0;
GVL.bTiCtrlBit3 := (stTiOut.uiControlWord AND UINT#16#0008) <> UINT#0;
GVL.bTiCtrlBit4 := (stTiOut.uiControlWord AND UINT#16#0010) <> UINT#0;
GVL.bTiCtrlBit5 := (stTiOut.uiControlWord AND UINT#16#0020) <> UINT#0;
GVL.bTiCtrlBit7 := (stTiOut.uiControlWord AND UINT#16#0080) <> UINT#0;
GVL.bTiCtrlBit8 := (stTiOut.uiControlWord AND UINT#16#0100) <> UINT#0;
GVL.siTiMode := stTiOut.siModeOfOperation;
GVL.diTiTargetVel := stTiOut.diTargetVelocity;
GVL_LantaPpCsp.udiTiProfileVelocity := stTiOut.udiProfileVelocity;
GVL.diTiTargetPos := stTiOut.diTargetPosition;
GVL.diTiTargetAcc := stTiOut.udiProfileAcc;
GVL.diTiTargetDec := stTiOut.udiProfileDec;

(* 原AxisStatus和Modbus IR继续使用原变量。 *)
GVL.Axis1Status.bServo_Enable := stElStatus.xOperationEnabled;
GVL.Axis1Status.Disabled := NOT stElStatus.xOperationEnabled;
GVL.Axis1Status.Error := stElStatus.xFault;
GVL.Axis1Status.ErrorID := stElStatus.uiDriveErrorCode;
GVL.Axis1Status.Moving := NOT stElStatus.xVelocityZero;
GVL.Axis2Status.bServo_Enable := stAzStatus.xOperationEnabled;
GVL.Axis2Status.Disabled := NOT stAzStatus.xOperationEnabled;
GVL.Axis2Status.Error := stAzStatus.xFault;
GVL.Axis2Status.ErrorID := stAzStatus.uiDriveErrorCode;
GVL.Axis2Status.Moving := NOT stAzStatus.xVelocityZero;
GVL.Axis3Status.bServo_Enable := stTiStatus.xOperationEnabled;
GVL.Axis3Status.Disabled := NOT stTiStatus.xOperationEnabled;
GVL.Axis3Status.Error := stTiStatus.xFault;
GVL.Axis3Status.ErrorID := stTiStatus.uiDriveErrorCode;
GVL.Axis3Status.Moving := NOT stTiStatus.xVelocityZero;
GVL_LantaPpCsp.stElPpCspStatus := stElStatus;
GVL_LantaPpCsp.stAzPpCspStatus := stAzStatus;
GVL_LantaPpCsp.stTiPpCspStatus := stTiStatus;

IF GVL.Error_code = 0 THEN
	IF (stElStatus.udiErrorId = UDINT#16#C501) OR (stAzStatus.udiErrorId = UDINT#16#C501)
		OR (stTiStatus.udiErrorId = UDINT#16#C501) THEN
		GVL.Error_code := 501;
	ELSIF (stElStatus.udiErrorId = UDINT#16#C502) OR (stAzStatus.udiErrorId = UDINT#16#C502)
		OR (stTiStatus.udiErrorId = UDINT#16#C502) THEN
		GVL.Error_code := 502;
	ELSIF (stElStatus.udiErrorId = UDINT#16#C504) OR (stAzStatus.udiErrorId = UDINT#16#C504)
		OR (stTiStatus.udiErrorId = UDINT#16#C504) THEN
		GVL.Error_code := 504;
	END_IF
END_IF
