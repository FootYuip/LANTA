TYPE ST_AxisPdoOut :
STRUCT
	uiControlWord     : UINT;  (* 6040 *)
	siModeOfOperation : SINT;  (* 6060 *)
	diTargetPosition  : DINT;  (* 607A *)
	diTargetVelocity  : DINT;  (* 60FF *)
	udiProfileVelocity: UDINT; (* 6081 *)
	udiProfileAcc     : UDINT; (* 6083 *)
	udiProfileDec     : UDINT; (* 6084 *)
END_STRUCT
END_TYPE
