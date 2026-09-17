FUNCTION F_LantaStatusWord : UINT
VAR_INPUT
	xBit0  : BOOL;
	xBit1  : BOOL;
	xBit2  : BOOL;
	xBit3  : BOOL;
	xBit10 : BOOL;
	xBit12 : BOOL;
END_VAR

F_LantaStatusWord := UINT#0;
IF xBit0 THEN F_LantaStatusWord := F_LantaStatusWord OR UINT#16#0001; END_IF
IF xBit1 THEN F_LantaStatusWord := F_LantaStatusWord OR UINT#16#0002; END_IF
IF xBit2 THEN F_LantaStatusWord := F_LantaStatusWord OR UINT#16#0004; END_IF
IF xBit3 THEN F_LantaStatusWord := F_LantaStatusWord OR UINT#16#0008; END_IF
IF xBit10 THEN F_LantaStatusWord := F_LantaStatusWord OR UINT#16#0400; END_IF
IF xBit12 THEN F_LantaStatusWord := F_LantaStatusWord OR UINT#16#1000; END_IF
