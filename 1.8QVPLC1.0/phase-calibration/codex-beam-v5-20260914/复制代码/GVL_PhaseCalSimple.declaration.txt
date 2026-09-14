{attribute 'qualified_only'}
VAR_GLOBAL
    (* 日常只填写以下四项。波束宽度为两轴共用的半功率全宽，单位度。 *)
    lrBeamWidthDeg : LREAL := 0;
    lrAzGain : LREAL := 1; (* 接收机当前方位增益，线性倍数，必须大于0 *)
    lrElGain : LREAL := 1; (* 接收机当前俯仰增益，线性倍数，必须大于0 *)
    lrPhaseDeg : LREAL := 0; (* 接收机当前公共旋转角，度 *)
    (* 操作命令，普通写值，不强制。开始需要 FALSE→TRUE。 *)
    xStart, xAbort, xReset : BOOL;
    (* 以下只读，不填写。详细诊断仍在 GVL_PhaseCal。 *)
    xReady, xBusy, xDone, xFault, xAborted, xResultValid : BOOL;
    wsMessage : WSTRING(160);
    lrNewPhaseDeg, lrNewAzGain, lrNewElGain : LREAL;
    lrOrthErrorDeg, lrPlannedTimeSec : LREAL;
END_VAR
