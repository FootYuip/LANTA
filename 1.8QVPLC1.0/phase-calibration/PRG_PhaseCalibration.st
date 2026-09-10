PROGRAM PRG_PhaseCalibration
(* Called ONLY at the end of SecurityCheck, once per Canopen 10 ms cycle.
   Fixed position mode only. No writes to modes, enables, tracking or persistence.
   Loss of ownership gives command control back to the existing program immediately.
   This is not an emergency-stop/safety function. *)
VAR
    path : FB_PhaseTriangle;
    fit : FB_PhaseFit;
    startOld, startPulse, accepted, permit, ownership : BOOL;
    sample, finish, newRx, rxLock, doneOld, abortRun : BOOL;
    seq, lastSeq : UDINT;
    age : LREAL := 999;
    sampleTime : LREAL;
    ua, ue, eb, az, el, centerAz, centerEl : LREAL;
    baseAz, baseEl, phase : LREAL;
    direction : INT;
END_VAR

startPulse:=GVL_PhaseCal.xStart AND NOT startOld;
startOld:=GVL_PhaseCal.xStart;
accepted:=FALSE; sample:=FALSE; newRx:=FALSE;
age:=MIN(age+0.01,999.0);
sampleTime:=MIN(sampleTime+0.01,1.0);
seq:=GVL_PhaseCal.udiRxSeq;
IF seq<>lastSeq AND seq MOD 2=0 THEN
    ua:=GVL_PhaseCal.lrRxUa; ue:=GVL_PhaseCal.lrRxUe;
    eb:=GVL_PhaseCal.lrRxEbN0;
    az:=GVL_PhaseCal.lrRxAz; el:=GVL_PhaseCal.lrRxEl;
    rxLock:=GVL_PhaseCal.xRxLock;
    IF seq=GVL_PhaseCal.udiRxSeq THEN
        lastSeq:=seq; age:=0; newRx:=TRUE;
    END_IF;
END_IF;

ownership:=NOT GVL.bLocalCtrl AND GVL.Axis1Remote.iMode=2 AND
    GVL.Axis2Remote.iMode=2 AND NOT GVL.bStartTrack AND
    NOT GVL.bStartLocalAutoTrack AND NOT Modbus_Slave.bStartTrackAcu AND
    NOT Modbus_Slave.bSearch AND NOT SecurityCheck.bScanRun AND
    ABS(SecurityCheck.aztest)<0.00001 AND ABS(SecurityCheck.eltest)<0.00001;
permit:=ownership AND GVL.Axis1Status.bServo_Enable AND
    GVL.Axis2Status.bServo_Enable AND NOT GVL.Axis1Status.Error AND
    NOT GVL.Axis2Status.Error AND NOT GVL.Axis1Status.ErrorStop AND
    NOT GVL.Axis2Status.ErrorStop AND GVL.eAzErrorcode=0 AND GVL.eElErrorcode=0 AND
    NOT SecurityCheck.bPrelimit_1 AND NOT SecurityCheck.bPrelimit_2 AND
    NOT SecurityCheck.bFinallimit_1 AND NOT SecurityCheck.bFinallimit_2;
IF path.xBusy THEN
    (* Never mask a changed ACU target by holding the old calibration center. *)
    permit:=permit AND ABS(REAL_TO_LREAL(Modbus_Slave.rPosCmd_2)-baseAz)<0.00001 AND
        ABS(REAL_TO_LREAL(Modbus_Slave.rPosCmd_1)-baseEl)<0.00001;
END_IF;
(* Signal quality and initial pointing are assessed manually by the operator.
   Keep new-receive sampling; never manufacture samples from stale values. *)
GVL_PhaseCal.xReady:=permit AND
    NOT path.xBusy AND NOT GVL_PhaseCal.xFault AND NOT GVL_PhaseCal.xAbort AND
    ABS(REAL_TO_LREAL(Modbus_Slave.rPosCmd_2))<274.8 AND
    Modbus_Slave.rPosCmd_1>93.2 AND Modbus_Slave.rPosCmd_1<179.8;

IF GVL_PhaseCal.xReset AND NOT path.xBusy THEN
    GVL_PhaseCal.xFault:=FALSE; GVL_PhaseCal.uiError:=0;
END_IF;
IF startPulse AND NOT path.xBusy THEN
    GVL_PhaseCal.xDone:=FALSE;
    GVL_PhaseCal.xFitValid:=FALSE; GVL_PhaseCal.xSuggestedValid:=FALSE;
    IF NOT GVL_PhaseCal.xReady OR GVL_PhaseCal.lrCurrentPhaseDeg<0 OR
       GVL_PhaseCal.lrCurrentPhaseDeg>360 OR
       GVL_PhaseCal.lrRadiusDeg<=0 OR GVL_PhaseCal.lrRadiusDeg>0.1 OR
       GVL_PhaseCal.lrLegTimeSec<2 OR GVL_PhaseCal.lrLegTimeSec>60 OR
       GVL_PhaseCal.lrSettleSec<0.1 OR GVL_PhaseCal.lrSettleSec>30 THEN
        GVL_PhaseCal.uiError:=10; GVL_PhaseCal.xFault:=TRUE;
    ELSE
        baseAz:=REAL_TO_LREAL(Modbus_Slave.rPosCmd_2);
        baseEl:=REAL_TO_LREAL(Modbus_Slave.rPosCmd_1);
        centerAz:=-baseAz; centerEl:=baseEl-90;
        phase:=GVL_PhaseCal.lrCurrentPhaseDeg;
        direction:=GVL_PhaseCal.iPhaseDirection;
        accepted:=TRUE; sampleTime:=0;
        GVL_PhaseCal.uiError:=0; GVL_PhaseCal.xFault:=FALSE;
    END_IF;
END_IF;

abortRun:=GVL_PhaseCal.xAbort;
IF path.xBusy AND path.uiState<>800 AND path.uiState<>900 THEN
    IF ABS(-REAL_TO_LREAL(GVL.rFctPosReal_2)-centerAz-path.lrAzBias)>0.1 OR
       ABS(REAL_TO_LREAL(GVL.rFctPosReal_1)-90-centerEl-path.lrElBias)>0.1 THEN
        abortRun:=TRUE; GVL_PhaseCal.uiError:=21; GVL_PhaseCal.xFault:=TRUE;
    END_IF;
END_IF;
path(xStart:=accepted, xAbort:=abortRun, xPermit:=permit,
    xResetHeld:=GVL_PhaseCal.xReset AND NOT GVL.Axis1Status.bServo_Enable AND
        NOT GVL.Axis2Status.bServo_Enable,
    lrDtSec:=0.01, lrRadiusDeg:=GVL_PhaseCal.lrRadiusDeg,
    lrLegTimeSec:=GVL_PhaseCal.lrLegTimeSec, lrSettleSec:=GVL_PhaseCal.lrSettleSec);
IF path.xFault THEN
    GVL_PhaseCal.xFault:=TRUE; GVL_PhaseCal.uiError:=22;
END_IF;
IF path.xBusy AND permit AND path.uiState<>900 THEN
    (* Same signs as existing eltest/aztest target offsets. *)
    GVL.Axis1Remote.rPosCmd:=LREAL_TO_REAL(baseEl+path.lrElBias);
    GVL.Axis2Remote.rPosCmd:=LREAL_TO_REAL(baseAz-path.lrAzBias);
END_IF;
IF path.xBusy AND path.xCollect AND
   newRx AND sampleTime>=0.05 AND NOT GVL_PhaseCal.xFault AND NOT path.xAborted THEN
    sample:=TRUE; sampleTime:=0;
END_IF;
finish:=path.xDone AND NOT doneOld AND NOT GVL_PhaseCal.xFault;
IF finish AND (ABS(-REAL_TO_LREAL(GVL.rFctPosReal_2)-centerAz)>0.01 OR
              ABS(REAL_TO_LREAL(GVL.rFctPosReal_1)-90-centerEl)>0.01) THEN
    finish:=FALSE; GVL_PhaseCal.xFault:=TRUE; GVL_PhaseCal.uiError:=31;
END_IF;
doneOld:=path.xDone;
fit(xReset:=accepted, xSample:=sample, xFinish:=finish,
    lrAz:=az-centerAz, lrEl:=el-centerEl, lrUa:=ua, lrUe:=ue,
    lrCurrentPhaseDeg:=phase, iPhaseDirection:=direction);
IF finish THEN
    GVL_PhaseCal.xDone:=TRUE;
    GVL_PhaseCal.xFitValid:=fit.xFitValid;
    GVL_PhaseCal.xSuggestedValid:=fit.xSuggestedValid;
    IF NOT fit.xFitValid THEN
        GVL_PhaseCal.xFault:=TRUE; GVL_PhaseCal.uiError:=30;
    END_IF;
END_IF;
GVL_PhaseCal.xBusy:=path.xBusy; GVL_PhaseCal.xAborted:=path.xAborted;
GVL_PhaseCal.uiState:=path.uiState; GVL_PhaseCal.uiFitError:=fit.uiError;
GVL_PhaseCal.lrAzBias:=path.lrAzBias; GVL_PhaseCal.lrElBias:=path.lrElBias;
GVL_PhaseCal.lrRxAgeSec:=age; GVL_PhaseCal.udiSamples:=fit.udiSamples;
GVL_PhaseCal.lrResponseAngleDeg:=fit.lrResponseAngleDeg;
GVL_PhaseCal.lrCorrectionDeg:=fit.lrCorrectionDeg;
GVL_PhaseCal.lrSuggestedDeg:=fit.lrSuggestedDeg;
GVL_PhaseCal.lrCandidatePlusDeg:=fit.lrCandidatePlusDeg;
GVL_PhaseCal.lrCandidateMinusDeg:=fit.lrCandidateMinusDeg;
GVL_PhaseCal.lrOrthErrorDeg:=fit.lrOrthErrorDeg;
GVL_PhaseCal.lrResidualAz:=fit.lrResidualAz; GVL_PhaseCal.lrResidualEl:=fit.lrResidualEl;
GVL_PhaseCal.lrKaa:=fit.lrKaa; GVL_PhaseCal.lrKae:=fit.lrKae;
GVL_PhaseCal.lrKea:=fit.lrKea; GVL_PhaseCal.lrKee:=fit.lrKee;
END_PROGRAM
