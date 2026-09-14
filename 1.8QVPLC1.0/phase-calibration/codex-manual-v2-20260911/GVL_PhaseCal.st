{attribute 'qualified_only'}
VAR_GLOBAL
    (* Commands: non-retained. Never FORCE these or axis commands. *)
    xStart : BOOL;
    xAbort : BOOL;
    xReset : BOOL;
    (* Commissioning interlock: confirm aligned reads with the actual protocol first.
       recSize>=16 alone is NOT a frame/header/checksum verification. *)
    xRxAlignmentConfirmed : BOOL := FALSE;
    lrCurrentPhaseDeg : LREAL := 0;
    iPhaseDirection : INT := 0; (* unknown=0, CCW=+1, CW=-1 *)
    (* Manual configuration. HPBW is the FULL -3 dB width in degrees. *)
    lrBeamAzDeg : LREAL := 0; (* required *)
    lrBeamElDeg : LREAL := 0; (* required *)
    lrScanFraction : LREAL := 0.2;
    lrTargetVolt : LREAL := 1.0; (* at 0.2 HPBW, independent of scan fraction *)
    lrCurrentGainAz : LREAL := 1;
    lrCurrentGainEl : LREAL := 1;
    iGainUnit : INT := 0; (* 0=linear voltage multiplier; 1=20*log10 multiplier dB *)
    iGainOrder : INT := 0; (* required: 1=gains before common rotation; 2=after *)
    lrGainMin : LREAL := 0.01; (* limits in selected device gain units *)
    lrGainMax : LREAL := 100;
    lrLegTimeSec : LREAL := 1.1;
    lrSettleSec : LREAL := 0.6; (* total dwell, including delay/settling and collection *)
    lrRxDelaySec : LREAL := 0.15; (* measured upper bound of receiver/filter delay *)
    lrStableSec : LREAL := 0.10;
    lrSampleIntervalSec : LREAL := 0.02;
    lrPositionToleranceDeg : LREAL := 0.002; (* mechanical per-axis *)
    lrMaxAxisOffsetDeg : LREAL := 0.1; (* commissioning ceiling; explicitly review if changed *)
    lrMaxVelocityDegSec : LREAL := 0; (* required mechanical per-axis limit *)
    lrMaxAccelerationDegSec2 : LREAL := 0; (* required mechanical per-axis limit *)
    lrMinCosEl : LREAL := 0.1; (* reject near zenith *)
    lrMaxOrthErrorDeg : LREAL := 3;
    lrMinEbN0 : LREAL := 29; (* legacy compatibility; no new EbN0 gate *)

    xGainValid : BOOL;
    lrGainFactorAz, lrGainFactorEl : LREAL;
    lrSuggestedGainAz, lrSuggestedGainEl : LREAL;
    lrSensitivityAz, lrSensitivityEl : LREAL; (* V/degree after proposed rotation, before new gain *)
    lrTargetSlopeAz, lrTargetSlopeEl : LREAL;
    lrPlannedTimeSec, lrCenterElevationDeg, lrProjectionCos : LREAL;
    lrPlannedAzOffsetDeg, lrPlannedElOffsetDeg : LREAL;
    lrCenterUa, lrCenterUe : LREAL; (* fitted center voltages, NOT proven electronic zero *)
    udiCenterSamples, udiElSamples, udiAzSamples, udiReturnSamples : UDINT;

    xReady, xBusy, xDone, xFault, xAborted : BOOL;
    xFitValid, xSuggestedValid : BOOL;
    uiError, uiFitError, uiState : UINT;
    udiSamples : UDINT;
    lrAzBias, lrElBias, lrRxAgeSec : LREAL;
    lrResponseAngleDeg, lrCorrectionDeg, lrSuggestedDeg : LREAL;
    lrCandidatePlusDeg, lrCandidateMinusDeg : LREAL;
    lrOrthErrorDeg, lrResidualAz, lrResidualEl : LREAL;
    lrKaa, lrKae, lrKea, lrKee : LREAL;

    (* SerialCom single writer; Canopen single reader. Even/odd sequence lock.
       Positions are PLC feedback at receive time, not sender timestamps. *)
    udiRxSeq : UDINT;
    uiReadSize, uiSerialError : UINT;
    udiReadCount, udiShortReadCount : UDINT;
    lrRxUa, lrRxUe, lrRxEbN0, lrRxAz, lrRxEl : LREAL;
    xRxLock : BOOL;
END_VAR
