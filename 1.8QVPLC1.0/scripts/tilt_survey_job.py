#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""倾斜轴自动扫描后台任务（Web 一键执行）。"""

from __future__ import annotations

import sys
import threading
import time
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
SENSOR_DIR = ROOT / "倾角传感器获取"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SENSOR_DIR))

from analyze_survey import TILT_SCAN_REPORT_NOTE, run_analysis
from read_inclinometer import (
    DEFAULT_HOST as SENSOR_DEFAULT_HOST,
    DEFAULT_PORT as SENSOR_DEFAULT_PORT,
    DEFAULT_SLAVE,
    PersistentInclinometerReader,
)
from survey_record import (
    OUTPUT_DIR,
    AzimuthSegment,
    SurveySession,
    collect_for_duration,
    generate_tilt_stops,
    save_session,
)

from modbus_plc_codec import DEFAULT_PLC_HOST, MODE_POINT, MODE_POWER_OFF
from ti_only_plc import TiOnlyPlc, wait_ti_in_position

DEFAULT_TI_VEL = 2.0
POS_TOL = 0.05


@dataclass
class TiltSurveyParams:
    plc_host: str = DEFAULT_PLC_HOST
    plc_port: int = 502
    sensor_host: str = SENSOR_DEFAULT_HOST
    sensor_port: int = SENSOR_DEFAULT_PORT
    sensor_address: int = DEFAULT_SLAVE
    ti_vel: float = DEFAULT_TI_VEL
    step: int = 15
    dwell: float = 10.0
    interval: float = 0.5
    settle_timeout: float = 120.0
    output_dir: Path = field(default_factory=lambda: OUTPUT_DIR)
    run_analysis: bool = True
    save_plots: bool = True


def run_tilt_survey(
    plc: TiOnlyPlc,
    reader: PersistentInclinometerReader,
    *,
    stops: list[float],
    ti_vel: float,
    dwell: float,
    interval: float,
    settle_timeout: float,
    pos_tol: float = POS_TOL,
    cancel_event: threading.Event | None = None,
    on_progress: Callable[[dict], None] | None = None,
    log: Callable[[str], None] | None = None,
) -> SurveySession:
    """仅驱动倾斜轴扫描；方位/俯仰不做任何 Modbus 写入。"""

    def emit(phase: str, **extra: object) -> None:
        if on_progress:
            on_progress({"phase": phase, **extra})

    def say(msg: str) -> None:
        if log:
            log(msg)

    session = SurveySession()
    say("倾斜轴上电（约 3s）…")
    emit("power_on")
    plc.power_on_ti(seconds=3.0)
    plc.start_hold(interval=0.1)

    try:
        total = len(stops)
        for seg_id, tilt_deg in enumerate(stops, 1):
            if cancel_event and cancel_event.is_set():
                say("扫描已取消")
                break

            say(f"[{seg_id}/{total}] 目标 Ti = {tilt_deg:.1f}°")
            emit(
                "moving",
                segment=seg_id,
                total=total,
                target_ti=tilt_deg,
                collected=len(session.segments),
            )

            plc.set_command(imode=MODE_POINT, pos=tilt_deg, vel=ti_vel, pid=True)
            plc.write_ti_once()

            settled = wait_ti_in_position(
                plc,
                tilt_deg,
                pos_tol=pos_tol,
                timeout=settle_timeout,
                cancel_event=cancel_event,
            )
            st = plc.read_status()
            actual = st["ti_deg"]

            if not settled:
                say(
                    f"  到位超时 |Ti−目标|={abs(actual - tilt_deg):.3f}° > {pos_tol}°，跳过采集"
                )
                emit(
                    "settle_timeout",
                    segment=seg_id,
                    total=total,
                    target_ti=tilt_deg,
                    actual_ti=actual,
                )
                continue

            say(f"  已到位 Ti={actual:.3f}°，开始采集 {dwell}s")
            emit(
                "collecting",
                segment=seg_id,
                total=total,
                target_ti=tilt_deg,
                actual_ti=actual,
            )

            start = datetime.now()
            samples = collect_for_duration(reader, tilt_deg, dwell, interval)
            end = datetime.now()

            if cancel_event and cancel_event.is_set():
                say("扫描已取消")
                break

            if not samples:
                say("  本点无有效传感器数据，跳过")
                continue

            segment = AzimuthSegment(
                segment_id=seg_id,
                azimuth=tilt_deg,
                start=start,
                end=end,
                samples=samples,
            )
            session.segments.append(segment)
            emit(
                "segment_done",
                segment=seg_id,
                total=total,
                target_ti=tilt_deg,
                actual_ti=actual,
                sample_count=len(samples),
                collected=len(session.segments),
            )
    finally:
        plc.stop_hold()

    return session


def finalize_session(
    session: SurveySession,
    output_dir: Path,
    *,
    run_analysis_flag: bool,
    save_plots: bool,
    log: Callable[[str], None] | None = None,
) -> dict:
    def say(msg: str) -> None:
        if log:
            log(msg)

    result: dict = {"txt_path": None, "csv_path": None, "analysis_dir": None}
    if not session.segments:
        say("无采集数据，不保存")
        return result

    say("保存 survey 数据…")
    paths = save_session(session, output_dir)
    if not paths:
        return result
    txt_path, csv_path = paths
    result["txt_path"] = str(txt_path)
    result["csv_path"] = str(csv_path)
    say(f"  {txt_path}")
    say(f"  {csv_path}")

    if run_analysis_flag:
        say("自动分析…")
        _, analysis_dir = run_analysis(
            csv_path,
            output_dir,
            save_plots=save_plots,
            extra_header=TILT_SCAN_REPORT_NOTE,
        )
        result["analysis_dir"] = str(analysis_dir)
        say(f"分析目录: {analysis_dir}")

    return result


class TiltSurveyJob:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._state: dict = {"running": False, "phase": "idle", "log": [], "result": None}

    def snapshot(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _append_log(self, msg: str) -> None:
        with self._lock:
            logs = self._state.setdefault("log", [])
            logs.append(f"{datetime.now().strftime('%H:%M:%S')} {msg}")
            if len(logs) > 200:
                del logs[: len(logs) - 200]

    def _set_state(self, **kwargs: object) -> None:
        with self._lock:
            self._state.update(kwargs)

    def running(self) -> bool:
        with self._lock:
            return bool(self._state.get("running"))

    def start(self, params: TiltSurveyParams, *, stop_main_hold: Callable[[], None] | None = None) -> None:
        with self._lock:
            if self._state.get("running"):
                raise RuntimeError("倾斜扫描已在运行")
            self._cancel.clear()
            self._state = {
                "running": True,
                "phase": "starting",
                "log": [],
                "result": None,
                "progress": {},
                "error": None,
            }

        def worker() -> None:
            plc = TiOnlyPlc()
            session = SurveySession()
            try:
                if stop_main_hold:
                    stop_main_hold()
                self._append_log(
                    f"连接 PLC {params.plc_host}:{params.plc_port}（仅倾斜轴 HR）"
                )
                plc.connect(params.plc_host, params.plc_port)
                stops = generate_tilt_stops(params.step)
                self._set_state(
                    phase="running",
                    total=len(stops),
                    collected=0,
                    step=params.step,
                    dwell=params.dwell,
                )
                self._append_log(
                    f"扫描 {len(stops)} 点，步距 {params.step}°，到位阈值 {POS_TOL}°"
                )

                with PersistentInclinometerReader(
                    params.sensor_host,
                    params.sensor_port,
                    slave=params.sensor_address,
                ) as reader:
                    self._append_log(
                        f"传感器 {params.sensor_host}:{params.sensor_port} 已连接"
                    )

                    def on_progress(info: dict) -> None:
                        self._set_state(phase=info.get("phase", "running"), progress=info)

                    session = run_tilt_survey(
                        plc,
                        reader,
                        stops=stops,
                        ti_vel=params.ti_vel,
                        dwell=params.dwell,
                        interval=params.interval,
                        settle_timeout=params.settle_timeout,
                        cancel_event=self._cancel,
                        on_progress=on_progress,
                        log=self._append_log,
                    )
            except Exception as exc:
                self._append_log(f"错误: {exc}")
                self._set_state(error=str(exc), phase="error")
                traceback.print_exc()
            finally:
                try:
                    plc.stop_hold()
                    if plc.connected:
                        self._append_log("倾斜轴下电")
                        plc.power_off_ti()
                except Exception:
                    pass
                try:
                    plc.disconnect()
                except Exception:
                    pass

            if self._cancel.is_set():
                self._set_state(phase="cancelled")
                self._append_log("任务已停止")

            result = finalize_session(
                session,
                params.output_dir,
                run_analysis_flag=params.run_analysis and not self._cancel.is_set(),
                save_plots=params.save_plots,
                log=self._append_log,
            )
            self._set_state(
                running=False,
                phase="done" if not self._cancel.is_set() else "cancelled",
                result=result,
                collected=len(session.segments),
            )

        self._thread = threading.Thread(target=worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._cancel.set()
        self._append_log("正在停止…")
