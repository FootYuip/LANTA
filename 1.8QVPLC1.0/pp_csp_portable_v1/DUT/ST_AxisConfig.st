TYPE ST_AxisConfig :
STRUCT
	udiCycleUs          : UDINT := UDINT#10000;
	udiServoSettleMs    : UDINT := UDINT#500;
	udiEnableTimeoutMs  : UDINT := UDINT#3000;
	udiHaltTimeoutMs    : UDINT := UDINT#5000;
	diVelocityZeroLimit : DINT := DINT#50;
	diPositionTolerance : DINT := DINT#100;
	diMaxCspStep        : DINT := DINT#2000;
	udiProfileVelocity  : UDINT := UDINT#10000;
	udiProfileAcc       : UDINT := UDINT#10000;
	udiProfileDec       : UDINT := UDINT#10000;
	xRequireModeDisplay : BOOL := TRUE;
END_STRUCT
END_TYPE
