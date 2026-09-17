TYPE ST_AxisDemand :
STRUCT
	xEnable             : BOOL;
	xDisable            : BOOL;
	xHalt               : BOOL;
	xFaultReset         : BOOL;
	xRequestPP          : BOOL;
	xRequestPV          : BOOL;
	xPpMoveTrigger      : BOOL;
	xRequestCSP         : BOOL;
	xTrajectoryActive   : BOOL;
	xTrajectoryValid    : BOOL;
	diPpTargetPosition  : DINT;
	diTargetVelocity    : DINT;
	diCspHoldPosition   : DINT;
	diCspTrajectoryPoint: DINT;
END_STRUCT
END_TYPE
