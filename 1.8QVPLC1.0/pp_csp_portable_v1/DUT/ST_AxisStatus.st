TYPE ST_AxisStatus :
STRUCT
	eState             : E_Cia402AxisState;
	xAvailable         : BOOL;
	xFault             : BOOL;
	xWarning           : BOOL;
	xInternalLimit     : BOOL;
	xOperationEnabled  : BOOL;
	xTargetReached     : BOOL;
	xVelocityZero      : BOOL;
	xPpReady           : BOOL;
	xCspReady          : BOOL;
	xCspHolding        : BOOL;
	xCspFollowing      : BOOL;
	xCspStepRejected   : BOOL;
	siModeDisplay      : SINT;
	uiStatusWord       : UINT;
	uiDriveErrorCode   : UINT;
	udiErrorId         : UDINT;
	diActualPosition   : DINT;
	diActualVelocity   : DINT;
	diCommandPosition  : DINT;
	diFollowingError   : DINT;
END_STRUCT
END_TYPE
