TYPE ST_AxisPdoIn :
STRUCT
	uiStatusWord      : UINT;  (* 6041 *)
	siModeDisplay     : SINT;  (* 6061 *)
	diActualPosition  : DINT;  (* 6064 *)
	diActualVelocity  : DINT;  (* 606C *)
	uiDriveErrorCode  : UINT;  (* 603F; 若未映射可置0 *)
	xNodeOperational  : BOOL;
	xHeartbeatOk      : BOOL;
END_STRUCT
END_TYPE
