
(* PHASE_CAL_RX_BEGIN: passive diagnostics; original decoder above is unchanged.
   Assumes each eligible read starts at original recBuf[0]. Not a frame parser.
   Admission requires separate operator protocol/alignment confirmation. *)
GVL_PhaseCal.uiReadSize:=recSize;
GVL_PhaseCal.uiSerialError:=m_uiError;
IF recSize>0 THEN
    IF GVL_PhaseCal.udiReadCount>=4294967294 THEN
        GVL_PhaseCal.udiReadCount:=0;
    END_IF;
    GVL_PhaseCal.udiReadCount:=GVL_PhaseCal.udiReadCount+1;
    IF recSize<16 THEN
        IF GVL_PhaseCal.udiShortReadCount>=4294967294 THEN
            GVL_PhaseCal.udiShortReadCount:=0;
        END_IF;
        GVL_PhaseCal.udiShortReadCount:=GVL_PhaseCal.udiShortReadCount+1;
    END_IF;
END_IF;
IF recSize>=16 AND recSize<=20 AND m_uiError=0 AND
   ABS(INT_TO_REAL(iUa)*5/2048)<=5 AND
   ABS(INT_TO_REAL(iUe)*5/2048)<=5 AND
   ABS(WORD_TO_REAL(wAGC)*5/76)<=5 THEN
    IF GVL_PhaseCal.udiRxSeq>=4294967294 THEN
        GVL_PhaseCal.udiRxSeq:=1;
    ELSE
        GVL_PhaseCal.udiRxSeq:=GVL_PhaseCal.udiRxSeq+1;
    END_IF;
    GVL_PhaseCal.lrRxUa:=REAL_TO_LREAL(GVL.Chan1Ua);
    GVL_PhaseCal.lrRxUe:=REAL_TO_LREAL(GVL.Chan1Ue);
    GVL_PhaseCal.lrRxEbN0:=REAL_TO_LREAL(Chan1EB_N0);
    GVL_PhaseCal.lrRxAz:=-REAL_TO_LREAL(GVL.rFctPosReal_2);
    GVL_PhaseCal.lrRxEl:=REAL_TO_LREAL(GVL.rFctPosReal_1)-90;
    GVL_PhaseCal.xRxLock:=(recBuf[1]=1);
    GVL_PhaseCal.udiRxSeq:=GVL_PhaseCal.udiRxSeq+1;
END_IF;
(* PHASE_CAL_RX_END *)
