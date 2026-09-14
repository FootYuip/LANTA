FUNCTION_BLOCK FB_PhaseFit
(* Offline candidate. Feed ONE coherent, validated sample per xSample pulse.
   Coordinates: positive Az=right, positive El=up. Desired response is -I.
   eAz/eEl must already have consistent signed engineering units.
   Do not subtract 2.5 from the existing signed serial values without protocol proof. *)
VAR_INPUT
    xReset : BOOL;
    xSample : BOOL;
    xFinish : BOOL;
    lrAz : LREAL;
    lrEl : LREAL;
    lrUa : LREAL;
    lrUe : LREAL;
    lrCurrentPhaseDeg : LREAL;
    (* +1: increasing hardware phase rotates measured response CCW; -1: CW; 0: unknown *)
    iPhaseDirection : INT;
END_VAR
VAR_OUTPUT
    xFitValid : BOOL;
    xSuggestedValid : BOOL;
    uiError : UINT;
    udiSamples : UDINT;
    lrKaa, lrKae, lrKea, lrKee : LREAL;
    lrInterceptAz, lrInterceptEl : LREAL;
    lrResponseAngleDeg : LREAL;
    lrCorrectionDeg, lrSuggestedDeg : LREAL;
    lrCandidatePlusDeg, lrCandidateMinusDeg : LREAL;
    lrOrthErrorDeg : LREAL;
    lrResidualAz, lrResidualEl : LREAL;
    lrCrossAz, lrCrossEl : LREAL;
END_VAR
VAR
    sx, sy, su, sv, sxx, syy, sxy, sxu, syu, sxv, syv, suu, svv : LREAL;
    n, xx, yy, xy, xu, yu, xv, yv, uu, vv, det : LREAL;
    ga, lrElGain, dot, a, b, phi, pi, base, sse : LREAL;
    finishOld : BOOL;
END_VAR

pi := 3.141592653589793;
IF xReset THEN
    sx:=0; sy:=0; su:=0; sv:=0; sxx:=0; syy:=0; sxy:=0;
    sxu:=0; syu:=0; sxv:=0; syv:=0; suu:=0; svv:=0;
    udiSamples:=0; uiError:=0; xFitValid:=FALSE; xSuggestedValid:=FALSE;
    lrKaa:=0; lrKae:=0; lrKea:=0; lrKee:=0;
    lrInterceptAz:=0; lrInterceptEl:=0; lrResponseAngleDeg:=0;
    lrCorrectionDeg:=0; lrSuggestedDeg:=0;
    lrCandidatePlusDeg:=0; lrCandidateMinusDeg:=0;
    lrOrthErrorDeg:=0; lrResidualAz:=0; lrResidualEl:=0;
    lrCrossAz:=0; lrCrossEl:=0;
ELSIF xSample AND NOT xFinish THEN
    IF udiSamples < 100000 THEN
        udiSamples:=udiSamples+1;
        sx:=sx+lrAz; sy:=sy+lrEl; su:=su+lrUa; sv:=sv+lrUe;
        sxx:=sxx+lrAz*lrAz; syy:=syy+lrEl*lrEl; sxy:=sxy+lrAz*lrEl;
        sxu:=sxu+lrAz*lrUa; syu:=syu+lrEl*lrUa;
        sxv:=sxv+lrAz*lrUe; syv:=syv+lrEl*lrUe;
        suu:=suu+lrUa*lrUa; svv:=svv+lrUe*lrUe;
    ELSE
        uiError:=1;
    END_IF;
END_IF;

IF xFinish AND NOT finishOld AND NOT xReset THEN
    xFitValid:=FALSE; xSuggestedValid:=FALSE;
    IF udiSamples < 30 OR uiError <> 0 THEN
        uiError:=2;
    ELSE
        n:=UDINT_TO_LREAL(udiSamples);
        xx:=sxx-sx*sx/n; yy:=syy-sy*sy/n; xy:=sxy-sx*sy/n;
        xu:=sxu-sx*su/n; yu:=syu-sy*su/n;
        xv:=sxv-sx*sv/n; yv:=syv-sy*sv/n;
        uu:=suu-su*su/n; vv:=svv-sv*sv/n;
        det:=xx*yy-xy*xy;
        IF xx <= 1E-12 OR yy <= 1E-12 OR det <= 0.01*xx*yy THEN
            uiError:=3; (* insufficient two-axis excitation *)
        ELSE
            lrKaa:=(xu*yy-yu*xy)/det;
            lrKae:=(yu*xx-xu*xy)/det;
            lrKea:=(xv*yy-yv*xy)/det;
            lrKee:=(yv*xx-xv*xy)/det;
            lrInterceptAz:=(su-lrKaa*sx-lrKae*sy)/n;
            lrInterceptEl:=(sv-lrKea*sx-lrKee*sy)/n;
            ga:=SQRT(lrKaa*lrKaa+lrKea*lrKea);
            lrElGain:=SQRT(lrKae*lrKae+lrKee*lrKee);
            sse:=MAX(0.0,uu-lrKaa*xu-lrKae*yu);
            lrResidualAz:=SQRT(sse/n);
            sse:=MAX(0.0,vv-lrKea*xv-lrKee*yv);
            lrResidualEl:=SQRT(sse/n);
            IF ga < 1E-6 OR lrElGain < 1E-6 OR (uu+vv) < 1E-10 THEN
                uiError:=4; (* no usable response *)
            ELSIF (lrKaa*lrKee-lrKae*lrKea) <= 0 THEN
                uiError:=5; (* reflection/polarity mismatch; common rotation cannot fix *)
            ELSE
                dot:=(lrKaa*lrKae+lrKea*lrKee)/(ga*lrElGain);
                dot:=LIMIT(-1.0,dot,1.0);
                lrOrthErrorDeg:=ABS(90.0-ACOS(dot)*180.0/pi);
                (* Normalize columns to prevent unequal axis gains dominating angle.
                   For M=R(phi)*diag(-ga,-lrElGain), a=2*cos(phi), b=2*sin(phi). *)
                a:=-lrKaa/ga-lrKee/lrElGain;
                b:=-lrKea/ga+lrKae/lrElGain;
                IF ABS(a)+ABS(b)<1E-9 THEN
                    uiError:=6;
                ELSE
                    IF ABS(a)<1E-12 THEN
                        IF b>=0 THEN phi:=pi/2; ELSE phi:=-pi/2; END_IF;
                    ELSE
                        phi:=ATAN(b/a);
                        IF a<0 THEN
                            IF b>=0 THEN phi:=phi+pi; ELSE phi:=phi-pi; END_IF;
                        END_IF;
                    END_IF;
                    lrResponseAngleDeg:=phi*180.0/pi;
                    (* Finite diagnostic ratio; 1E6 means a vanishing main channel. *)
                    lrCrossAz:=ABS(lrKea)/MAX(ABS(lrKaa),ga*1E-6);
                    lrCrossEl:=ABS(lrKae)/MAX(ABS(lrKee),lrElGain*1E-6);
                    (* Orthogonality is diagnostic only during commissioning.
                       xFitValid means rotation-estimate checks passed, NOT full calibration.
                       Keep residual rejection and all other validity checks unchanged. *)
                    IF (lrResidualAz*lrResidualAz+lrResidualEl*lrResidualEl)*n > 0.1*(uu+vv) THEN
                        uiError:=7; (* residual too large; correction rejected *)
                    ELSIF lrCurrentPhaseDeg<0 OR lrCurrentPhaseDeg>360 THEN
                        uiError:=8;
                    ELSE
                        xFitValid:=TRUE;
                        base:=lrCurrentPhaseDeg;
                        lrCandidatePlusDeg:=base+lrResponseAngleDeg;
                        lrCandidateMinusDeg:=base-lrResponseAngleDeg;
                        IF lrCandidatePlusDeg<0 THEN lrCandidatePlusDeg:=lrCandidatePlusDeg+360; END_IF;
                        IF lrCandidatePlusDeg>=360 THEN lrCandidatePlusDeg:=lrCandidatePlusDeg-360; END_IF;
                        IF lrCandidateMinusDeg<0 THEN lrCandidateMinusDeg:=lrCandidateMinusDeg+360; END_IF;
                        IF lrCandidateMinusDeg>=360 THEN lrCandidateMinusDeg:=lrCandidateMinusDeg-360; END_IF;
                        IF iPhaseDirection=1 OR iPhaseDirection=-1 THEN
                            lrCorrectionDeg:=-lrResponseAngleDeg/INT_TO_LREAL(iPhaseDirection);
                            lrSuggestedDeg:=base+lrCorrectionDeg;
                            IF lrSuggestedDeg<0 THEN lrSuggestedDeg:=lrSuggestedDeg+360; END_IF;
                            IF lrSuggestedDeg>=360 THEN lrSuggestedDeg:=lrSuggestedDeg-360; END_IF;
                            xSuggestedValid:=TRUE;
                        END_IF;
                    END_IF;
                END_IF;
            END_IF;
        END_IF;
    END_IF;
END_IF;
finishOld:=xFinish AND NOT xReset;
END_FUNCTION_BLOCK
