(*
	CiA-402 PP/CSP能力层。本FB必须是该轴PDO的唯一写入者，
	并且应在与CANopen SYNC相同周期的任务中调用。
*)
FUNCTION_BLOCK FB_Cia402PpCspAxis
VAR_INPUT
	stDemand      : ST_AxisDemand;
	stPdoIn       : ST_AxisPdoIn;
	stConfig      : ST_AxisConfig;
END_VAR
VAR_OUTPUT
	stPdoOut      : ST_AxisPdoOut;
	stStatus      : ST_AxisStatus;
END_VAR
VAR
	eState           : E_Cia402AxisState;
	eStateBeforeHalt : E_Cia402AxisState;
	udiStateMs       : UDINT;
	udiCycleMs       : UDINT;
	xFaultResetOld   : BOOL;
	diFixedCspHold   : DINT;
	diLastCspCommand : DINT;
	diLastPpTarget   : DINT;
	diDelta          : DINT;
	xPpMovePending   : BOOL;
	xCapabilityFault : BOOL;
	xStepRejectedLatched : BOOL;
	udiLatchedErrorId: UDINT;
END_VAR

udiCycleMs := stConfig.udiCycleUs / UDINT#1000;
IF udiCycleMs = UDINT#0 THEN udiCycleMs := UDINT#1; END_IF

stPdoOut.uiControlWord := UINT#0;
stPdoOut.siModeOfOperation := SINT#0;
stPdoOut.diTargetPosition := stPdoIn.diActualPosition;
stPdoOut.diTargetVelocity := DINT#0;
stPdoOut.udiProfileVelocity := stConfig.udiProfileVelocity;
stPdoOut.udiProfileAcc := stConfig.udiProfileAcc;
stPdoOut.udiProfileDec := stConfig.udiProfileDec;

stStatus.xAvailable := stPdoIn.xNodeOperational AND stPdoIn.xHeartbeatOk;
stStatus.xFault := ((stPdoIn.uiStatusWord AND UINT#16#0008) <> UINT#0) OR xCapabilityFault;
stStatus.xWarning := (stPdoIn.uiStatusWord AND UINT#16#0080) <> UINT#0;
stStatus.xInternalLimit := (stPdoIn.uiStatusWord AND UINT#16#0800) <> UINT#0;
stStatus.xOperationEnabled := (stPdoIn.uiStatusWord AND UINT#16#006F) = UINT#16#0027;
stStatus.xTargetReached := (stPdoIn.uiStatusWord AND UINT#16#0400) <> UINT#0;
stStatus.xVelocityZero := ABS(stPdoIn.diActualVelocity) <= stConfig.diVelocityZeroLimit;
stStatus.xCspStepRejected := xStepRejectedLatched;
stStatus.siModeDisplay := stPdoIn.siModeDisplay;
stStatus.uiStatusWord := stPdoIn.uiStatusWord;
stStatus.uiDriveErrorCode := stPdoIn.uiDriveErrorCode;
stStatus.diActualPosition := stPdoIn.diActualPosition;
stStatus.diActualVelocity := stPdoIn.diActualVelocity;
stStatus.udiErrorId := udiLatchedErrorId;

(* PP命令在模式尚未Ready时也不会丢：能力层保留pending。 *)
IF stDemand.xRequestPP AND
	(stDemand.xPpMoveTrigger OR (stDemand.diPpTargetPosition <> diLastPpTarget)) THEN
	diLastPpTarget := stDemand.diPpTargetPosition;
	xPpMovePending := TRUE;
END_IF

(* 高优先级状态请求。6040.Bit7只产生一个扫描周期的高电平。 *)
IF stStatus.xFault AND stDemand.xFaultReset AND NOT xFaultResetOld THEN
	xCapabilityFault := FALSE;
	xStepRejectedLatched := FALSE;
	udiLatchedErrorId := UDINT#0;
	eState := eAxisFaultResetHigh;
	udiStateMs := UDINT#0;
ELSIF stStatus.xFault AND (eState <> eAxisFaultResetHigh) AND (eState <> eAxisFaultResetLow) THEN
	eState := eAxisError;
	udiLatchedErrorId := UDINT#16#C402;
ELSIF stDemand.xDisable AND (eState <> eAxisOff) THEN
	eState := eAxisDisabling;
	udiStateMs := UDINT#0;
ELSIF stDemand.xHalt AND (eState <> eAxisHalting) AND (eState <> eAxisOff) THEN
	eStateBeforeHalt := eState;
	eState := eAxisHalting;
	udiStateMs := UDINT#0;
END_IF

CASE eState OF
	eAxisOff:
		stPdoOut.uiControlWord := UINT#0;
		IF stDemand.xFaultReset AND NOT xFaultResetOld THEN
			eState := eAxisFaultResetHigh;
		ELSIF stDemand.xRequestPP OR stDemand.xRequestPV OR stDemand.xRequestCSP OR stDemand.xEnable THEN
			eState := eAxisSetMode;
		END_IF

	eAxisFaultResetHigh:
		stPdoOut.uiControlWord := UINT#16#0080;
		eState := eAxisFaultResetLow;

	eAxisFaultResetLow:
		stPdoOut.uiControlWord := UINT#0;
		udiStateMs := udiStateMs + udiCycleMs;
		IF NOT stStatus.xFault THEN
			eState := eAxisOff;
		ELSIF udiStateMs >= stConfig.udiEnableTimeoutMs THEN
			eState := eAxisError;
			xCapabilityFault := TRUE;
			udiLatchedErrorId := UDINT#16#C403;
		END_IF

	eAxisSetMode:
		(* PP已稳定时切CSP；同一拍直接进入Shutdown，避免默认控制字0。 *)
		stPdoOut.uiControlWord := UINT#16#0006;
		IF stDemand.xRequestCSP THEN
			stPdoOut.siModeOfOperation := SINT#8;
			diFixedCspHold := stDemand.diCspHoldPosition;
			diLastCspCommand := diFixedCspHold;
			stPdoOut.diTargetPosition := diFixedCspHold;
		ELSIF stDemand.xRequestPV THEN
			stPdoOut.siModeOfOperation := SINT#3;
			stPdoOut.diTargetVelocity := stDemand.diTargetVelocity;
		ELSE
			stPdoOut.siModeOfOperation := SINT#1;
			stPdoOut.diTargetPosition := stDemand.diPpTargetPosition;
		END_IF
		eState := eAxisShutdown;
		udiStateMs := UDINT#0;

	eAxisShutdown:
		stPdoOut.uiControlWord := UINT#16#0006;
		IF stDemand.xRequestCSP THEN
			stPdoOut.siModeOfOperation := SINT#8;
			stPdoOut.diTargetPosition := diFixedCspHold;
		ELSIF stDemand.xRequestPV THEN
			stPdoOut.siModeOfOperation := SINT#3;
			stPdoOut.diTargetVelocity := stDemand.diTargetVelocity;
		ELSE
			stPdoOut.siModeOfOperation := SINT#1;
			stPdoOut.diTargetPosition := stDemand.diPpTargetPosition;
		END_IF
		IF (stPdoIn.uiStatusWord AND UINT#16#006F) = UINT#16#0021 THEN
			eState := eAxisSwitchOn;
		END_IF

	eAxisSwitchOn:
		stPdoOut.uiControlWord := UINT#16#0007;
		IF stDemand.xRequestCSP THEN
			stPdoOut.siModeOfOperation := SINT#8;
			stPdoOut.diTargetPosition := diFixedCspHold;
		ELSIF stDemand.xRequestPV THEN
			stPdoOut.siModeOfOperation := SINT#3;
			stPdoOut.diTargetVelocity := stDemand.diTargetVelocity;
		ELSE
			stPdoOut.siModeOfOperation := SINT#1;
			stPdoOut.diTargetPosition := stDemand.diPpTargetPosition;
		END_IF
		IF (stPdoIn.uiStatusWord AND UINT#16#006F) = UINT#16#0023 THEN
			eState := eAxisEnableOperation;
		END_IF

	eAxisEnableOperation:
		stPdoOut.uiControlWord := UINT#16#000F;
		IF stDemand.xRequestCSP THEN
			stPdoOut.siModeOfOperation := SINT#8;
			stPdoOut.diTargetPosition := diFixedCspHold;
		ELSIF stDemand.xRequestPV THEN
			stPdoOut.siModeOfOperation := SINT#3;
			stPdoOut.diTargetVelocity := stDemand.diTargetVelocity;
		ELSE
			stPdoOut.siModeOfOperation := SINT#1;
			stPdoOut.diTargetPosition := stDemand.diPpTargetPosition;
		END_IF
		IF stStatus.xOperationEnabled THEN
			eState := eAxisServoSettling;
			udiStateMs := UDINT#0;
		END_IF

	eAxisServoSettling:
		stPdoOut.uiControlWord := UINT#16#000F;
		udiStateMs := udiStateMs + udiCycleMs;
		IF stDemand.xRequestCSP THEN
			stPdoOut.siModeOfOperation := SINT#8;
			stPdoOut.diTargetPosition := diFixedCspHold;
			IF (udiStateMs >= stConfig.udiServoSettleMs) AND
				((NOT stConfig.xRequireModeDisplay) OR (stPdoIn.siModeDisplay = SINT#8)) THEN
				eState := eAxisReadyCSPHold;
			END_IF
		ELSIF stDemand.xRequestPV THEN
			stPdoOut.siModeOfOperation := SINT#3;
			stPdoOut.diTargetVelocity := stDemand.diTargetVelocity;
			IF (udiStateMs >= stConfig.udiServoSettleMs) AND
				((NOT stConfig.xRequireModeDisplay) OR (stPdoIn.siModeDisplay = SINT#3)) THEN
				eState := eAxisReadyPV;
			END_IF
		ELSE
			stPdoOut.siModeOfOperation := SINT#1;
			stPdoOut.diTargetPosition := stDemand.diPpTargetPosition;
			IF (udiStateMs >= stConfig.udiServoSettleMs) AND
				((NOT stConfig.xRequireModeDisplay) OR (stPdoIn.siModeDisplay = SINT#1)) THEN
				eState := eAxisReadyPP;
			END_IF
		END_IF

	eAxisReadyPP:
		stPdoOut.uiControlWord := UINT#16#000F;
		stPdoOut.siModeOfOperation := SINT#1;
		stPdoOut.diTargetPosition := stDemand.diPpTargetPosition;
		IF stDemand.xRequestCSP THEN
			eState := eAxisSetMode;
		ELSIF stDemand.xRequestPV THEN
			eState := eAxisSetMode;
		ELSIF xPpMovePending THEN
			eState := eAxisPpTriggerHigh;
		END_IF

	eAxisPpTriggerHigh:
		stPdoOut.uiControlWord := UINT#16#001F;
		stPdoOut.siModeOfOperation := SINT#1;
		stPdoOut.diTargetPosition := diLastPpTarget;
		xPpMovePending := FALSE;
		eState := eAxisPpTriggerLow;

	eAxisPpTriggerLow:
		stPdoOut.uiControlWord := UINT#16#000F;
		stPdoOut.siModeOfOperation := SINT#1;
		stPdoOut.diTargetPosition := diLastPpTarget;
		eState := eAxisReadyPP;

	eAxisReadyPV:
		stPdoOut.uiControlWord := UINT#16#000F;
		stPdoOut.siModeOfOperation := SINT#3;
		stPdoOut.diTargetVelocity := stDemand.diTargetVelocity;
		IF NOT stDemand.xRequestPV THEN
			eState := eAxisSetMode;
		END_IF

	eAxisReadyCSPHold:
		stPdoOut.uiControlWord := UINT#16#000F;
		stPdoOut.siModeOfOperation := SINT#8;
		(* 保持阶段永远重复写进入CSP时锁存的PP预置绝对点。 *)
		stPdoOut.diTargetPosition := diFixedCspHold;
		diLastCspCommand := diFixedCspHold;
		IF NOT stDemand.xRequestCSP THEN
			eState := eAxisSetMode;
		ELSIF stDemand.xTrajectoryActive AND stDemand.xTrajectoryValid THEN
			diDelta := stDemand.diCspTrajectoryPoint - diFixedCspHold;
			IF ABS(diDelta) <= stConfig.diMaxCspStep THEN
				diLastCspCommand := stDemand.diCspTrajectoryPoint;
				eState := eAxisReadyCSPFollow;
			ELSE
				xStepRejectedLatched := TRUE;
				xCapabilityFault := TRUE;
				udiLatchedErrorId := UDINT#16#C501;
				eState := eAxisError;
			END_IF
		END_IF

	eAxisReadyCSPFollow:
		stPdoOut.uiControlWord := UINT#16#000F;
		stPdoOut.siModeOfOperation := SINT#8;
		stPdoOut.diTargetPosition := diLastCspCommand;
		IF NOT stDemand.xRequestCSP THEN
			eStateBeforeHalt := eState;
			eState := eAxisHalting;
		ELSIF NOT stDemand.xTrajectoryActive OR NOT stDemand.xTrajectoryValid THEN
			(* 已跟随后不能跳回原预置点；冻结最后接受点并报告轨迹中断。 *)
			xCapabilityFault := TRUE;
			udiLatchedErrorId := UDINT#16#C502;
			eState := eAxisError;
		ELSE
			diDelta := stDemand.diCspTrajectoryPoint - diLastCspCommand;
			IF ABS(diDelta) <= stConfig.diMaxCspStep THEN
				diLastCspCommand := stDemand.diCspTrajectoryPoint;
				stPdoOut.diTargetPosition := diLastCspCommand;
			ELSE
				xStepRejectedLatched := TRUE;
				xCapabilityFault := TRUE;
				udiLatchedErrorId := UDINT#16#C501;
				eState := eAxisError;
			END_IF
		END_IF

	eAxisHalting:
		stPdoOut.uiControlWord := UINT#16#010F;
		IF (eStateBeforeHalt = eAxisReadyCSPHold) OR (eStateBeforeHalt = eAxisReadyCSPFollow) THEN
			stPdoOut.siModeOfOperation := SINT#8;
			stPdoOut.diTargetPosition := diLastCspCommand;
		ELSE
			stPdoOut.siModeOfOperation := SINT#1;
			stPdoOut.diTargetPosition := stPdoIn.diActualPosition;
		END_IF
		udiStateMs := udiStateMs + udiCycleMs;
		IF stStatus.xVelocityZero THEN
			udiStateMs := UDINT#0;
			IF stDemand.xDisable THEN
				eState := eAxisDisabling;
			ELSIF NOT stDemand.xHalt AND (stDemand.xRequestPP OR stDemand.xRequestPV OR stDemand.xRequestCSP OR stDemand.xEnable) THEN
				eState := eAxisSetMode;
			END_IF
		ELSIF udiStateMs >= stConfig.udiHaltTimeoutMs THEN
			eState := eAxisError;
			xCapabilityFault := TRUE;
			udiLatchedErrorId := UDINT#16#C504;
		END_IF

	eAxisDisabling:
		IF NOT stStatus.xVelocityZero THEN
			stPdoOut.uiControlWord := UINT#16#010F;
		ELSE
			stPdoOut.uiControlWord := UINT#0;
			eState := eAxisOff;
		END_IF

	eAxisError:
		(* 冻结最后安全位置并Halt；急停仍由外部安全层最高优先级处理。 *)
		stPdoOut.uiControlWord := UINT#16#010F;
		IF stPdoIn.siModeDisplay = SINT#8 THEN
			stPdoOut.siModeOfOperation := SINT#8;
			stPdoOut.diTargetPosition := diLastCspCommand;
		ELSE
			stPdoOut.siModeOfOperation := stPdoIn.siModeDisplay;
			stPdoOut.diTargetPosition := stPdoIn.diActualPosition;
		END_IF
END_CASE

stStatus.eState := eState;
stStatus.xPpReady := eState = eAxisReadyPP;
stStatus.xCspReady := (eState = eAxisReadyCSPHold) OR (eState = eAxisReadyCSPFollow);
stStatus.xCspHolding := eState = eAxisReadyCSPHold;
stStatus.xCspFollowing := eState = eAxisReadyCSPFollow;
stStatus.diCommandPosition := stPdoOut.diTargetPosition;
stStatus.diFollowingError := stPdoOut.diTargetPosition - stPdoIn.diActualPosition;
stStatus.xFault := ((stPdoIn.uiStatusWord AND UINT#16#0008) <> UINT#0) OR xCapabilityFault;
stStatus.xCspStepRejected := xStepRejectedLatched;
stStatus.udiErrorId := udiLatchedErrorId;
xFaultResetOld := stDemand.xFaultReset;
