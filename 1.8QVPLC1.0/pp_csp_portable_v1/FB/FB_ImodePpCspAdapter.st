(*
	将现有上位机 iMode 转换为站点无关的轴需求。
	关键规则：进入 iMode=4 时只锁存一次 PP 预置绝对位置；
	CSP 准备/保持阶段绝不根据实际位置、上一拍目标或未来轨迹改写保持点。
*)
FUNCTION_BLOCK FB_ImodePpCspAdapter
VAR_INPUT
	iMode                : INT;
	diPositionCommand    : DINT;
	diVelocityCommand    : DINT;
	xTrajectoryActive    : BOOL;
	xTrajectoryValid     : BOOL;
	diTrajectoryPoint    : DINT;
	xMotionPermitted     : BOOL;
	xFaultReset          : BOOL;
	diCspEntryTolerance  : DINT := DINT#1000;
END_VAR
VAR_IN_OUT
	stAxisStatus         : ST_AxisStatus;
END_VAR
VAR_OUTPUT
	stDemand             : ST_AxisDemand;
	diLatchedPpTarget    : DINT;
	diLatchedCspHold     : DINT;
	xCspEntryAccepted    : BOOL;
	xCspEntryDenied      : BOOL;
END_VAR
VAR
	iPreviousMode        : INT;
	diPreviousPpCommand  : DINT;
	xPpMovePulse         : BOOL;
	xFirstScan           : BOOL := TRUE;
	xCspHoldValid        : BOOL;
END_VAR

stDemand.xEnable := FALSE;
stDemand.xDisable := FALSE;
stDemand.xHalt := FALSE;
stDemand.xFaultReset := xFaultReset;
stDemand.xRequestPP := FALSE;
stDemand.xRequestPV := FALSE;
stDemand.xPpMoveTrigger := FALSE;
stDemand.xRequestCSP := FALSE;
stDemand.xTrajectoryActive := FALSE;
stDemand.xTrajectoryValid := FALSE;
stDemand.diPpTargetPosition := diLatchedPpTarget;
stDemand.diTargetVelocity := diVelocityCommand;
stDemand.diCspHoldPosition := diLatchedCspHold;
stDemand.diCspTrajectoryPoint := diTrajectoryPoint;
xCspEntryAccepted := FALSE;
xPpMovePulse := FALSE;

IF xFirstScan THEN
	iPreviousMode := iMode;
	diPreviousPpCommand := diPositionCommand;
	diLatchedPpTarget := diPositionCommand;
	xFirstScan := FALSE;
END_IF

(* PP目标只在iMode=2中更新；持续重复写相同命令不会重复触发。 *)
IF iMode = 2 THEN
	IF (iPreviousMode <> 2) OR (diPositionCommand <> diPreviousPpCommand) THEN
		diLatchedPpTarget := diPositionCommand;
		diPreviousPpCommand := diPositionCommand;
		xPpMovePulse := TRUE;
	END_IF
END_IF

(* iMode=4入口：固定锁存PP预置点。入口必须已到位且速度稳定。 *)
IF (iMode = 4) AND (iPreviousMode <> 4) THEN
	xCspHoldValid := FALSE;
	xCspEntryDenied := FALSE;
	IF xMotionPermitted
		AND stAxisStatus.xTargetReached
		AND stAxisStatus.xVelocityZero
		AND (ABS(diLatchedPpTarget - stAxisStatus.diActualPosition) <= diCspEntryTolerance) THEN
		diLatchedCspHold := diLatchedPpTarget;
		xCspHoldValid := TRUE;
		xCspEntryAccepted := TRUE;
	ELSE
		xCspEntryDenied := TRUE;
	END_IF
END_IF

IF iMode <> 4 THEN
	xCspHoldValid := FALSE;
	xCspEntryDenied := FALSE;
END_IF

CASE iMode OF
	0:
		stDemand.xDisable := TRUE;
	1:
		stDemand.xEnable := xMotionPermitted;
	2:
		stDemand.xEnable := xMotionPermitted;
		stDemand.xRequestPP := xMotionPermitted;
		stDemand.xPpMoveTrigger := xPpMovePulse;
		stDemand.diPpTargetPosition := diLatchedPpTarget;
	3:
		stDemand.xEnable := xMotionPermitted;
		stDemand.xRequestPV := xMotionPermitted;
		stDemand.diTargetVelocity := diVelocityCommand;
	4:
		(* 只有锁存过合法保持点，才允许能力层进入CSP。 *)
		IF xCspHoldValid AND NOT xCspEntryDenied THEN
			stDemand.xEnable := xMotionPermitted;
			stDemand.xRequestCSP := xMotionPermitted;
			stDemand.diCspHoldPosition := diLatchedCspHold;
			stDemand.xTrajectoryActive := xTrajectoryActive;
			stDemand.xTrajectoryValid := xTrajectoryValid;
			stDemand.diCspTrajectoryPoint := diTrajectoryPoint;
		END_IF
	6:
		stDemand.xFaultReset := TRUE;
	7:
		stDemand.xHalt := TRUE;
ELSE
	stDemand.xHalt := TRUE;
END_CASE

(* 远控许可丢失、切到本控或安全互锁失败时，先受控Halt。 *)
IF (NOT xMotionPermitted) AND ((iMode = 1) OR (iMode = 2) OR (iMode = 4)) THEN
	stDemand.xEnable := FALSE;
	stDemand.xRequestPP := FALSE;
	stDemand.xRequestPV := FALSE;
	stDemand.xRequestCSP := FALSE;
	stDemand.xTrajectoryActive := FALSE;
	stDemand.xHalt := TRUE;
END_IF

iPreviousMode := iMode;
