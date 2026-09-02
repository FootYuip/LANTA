#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
天线 Modbus 控制 — 三轴独立 Web 界面。

方位(Axis2/HR8) · 俯仰(Axis1/HR19) · 倾斜(Axis3/HR30)

  python scripts/modbus_web_app.py
  浏览器 http://127.0.0.1:8765
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "倾角传感器获取"))

from flask import Flask, jsonify, render_template, request

ROOT = Path(__file__).resolve().parent.parent

from modbus_plc_codec import (
    DEFAULT_PLC_HOST,
    IR_REG_COUNT,
    MODE_HALT,
    MODE_POINT,
    MODE_POWER_OFF,
    MODE_POWER_ON,
    build_ctrl_word,
    build_hr_block,
    ir_to_feedback,
    read_ir,
    write_hr_block,
)
from tilt_survey_job import TiltSurveyJob, TiltSurveyParams

try:
    from read_inclinometer import DEFAULT_HOST as SENSOR_DEFAULT_HOST
    from read_inclinometer import DEFAULT_PORT as SENSOR_DEFAULT_PORT
    from read_inclinometer import DEFAULT_SLAVE as SENSOR_DEFAULT_SLAVE
    from survey_record import OUTPUT_DIR as SURVEY_OUTPUT_DIR
except ImportError:
    SENSOR_DEFAULT_HOST = "192.168.1.168"
    SENSOR_DEFAULT_PORT = 10123
    SENSOR_DEFAULT_SLAVE = 0x50
    SURVEY_OUTPUT_DIR = ROOT / "倾角传感器获取" / "records"

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as e:
    raise SystemExit("请先安装: pip install pymodbus flask") from e

AxisName = Literal["az", "el", "ti"]
AXES: tuple[AxisName, ...] = ("az", "el", "ti")

APP_DIR = Path(__file__).resolve().parent
app = Flask(__name__, template_folder=str(APP_DIR / "templates"))


@dataclass
class AxisCmd:
    imode: int = MODE_POWER_OFF
    pos: float = 0.0
    vel: float = 4.0
    pid: bool = False


@dataclass
class HostState:
    az: AxisCmd = field(default_factory=lambda: AxisCmd(pos=0.0, vel=4.0))
    el: AxisCmd = field(default_factory=lambda: AxisCmd(pos=120.0, vel=4.0))
    ti: AxisCmd = field(default_factory=lambda: AxisCmd(pos=0.0, vel=2.0))

    def axis(self, name: AxisName) -> AxisCmd:
        return {"az": self.az, "el": self.el, "ti": self.ti}[name]

    def ctrl_word(self) -> int:
        return build_ctrl_word(
            az_pid=self.az.pid,
            el_pid=self.el.pid,
            ti_pid=self.ti.pid,
        )

    def to_dict(self) -> dict:
        def one(a: AxisCmd) -> dict:
            return {"imode": a.imode, "pos": a.pos, "vel": a.vel, "pid": a.pid}

        return {"az": one(self.az), "el": one(self.el), "ti": one(self.ti)}


class ModbusController:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.client: ModbusTcpClient | None = None
        self.host = DEFAULT_PLC_HOST
        self.port = 502
        self.state = HostState()
        self._hold_stop = threading.Event()
        self._hold_thread: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self.client is not None

    def connect(self, host: str, port: int) -> None:
        self.stop_hold()
        with self._lock:
            if self.client:
                self.client.close()
            client = ModbusTcpClient(host, port=port)
            if not client.connect():
                raise ConnectionError(f"无法连接 {host}:{port}")
            self.client = client
            self.host = host
            self.port = port

    def disconnect(self) -> None:
        self.stop_hold()
        with self._lock:
            if self.client:
                self.client.close()
                self.client = None

    def stop_hold(self) -> None:
        self._hold_stop.set()
        t = self._hold_thread
        if t and t.is_alive():
            t.join(timeout=2.5)
        with self._lock:
            self._hold_thread = None

    def _require_client(self) -> ModbusTcpClient:
        if not self.client:
            raise RuntimeError("未连接 PLC")
        return self.client

    def _write_state(self, client: ModbusTcpClient) -> None:
        s = self.state
        utc_ms = int(time.time() * 1000)
        regs = build_hr_block(
            utc_pc_ms=utc_ms,
            utc_orbit_ms=None,
            az_deg=s.az.pos,
            el_deg=s.el.pos,
            ti_deg=s.ti.pos,
            ctrl_word=s.ctrl_word(),
            imode_az=s.az.imode,
            imode_el=s.el.imode,
            imode_ti=s.ti.imode,
            az_vel_deg_s=s.az.vel,
            el_vel_deg_s=s.el.vel,
            ti_vel_deg_s=s.ti.vel,
        )
        write_hr_block(client, regs, push_orbit=False)

    def send_once(self) -> None:
        with self._lock:
            self._write_state(self._require_client())

    def read_status(self) -> dict:
        with self._lock:
            ir = read_ir(self._require_client(), 0, IR_REG_COUNT)
            st = ir_to_feedback(ir)
            st["connected"] = True
            st["host"] = self.host
            st["port"] = self.port
            st["command"] = self.state.to_dict()
            st["holding"] = self._hold_thread is not None and self._hold_thread.is_alive()
            return st

    def start_hold(self, interval: float = 0.1) -> None:
        self.stop_hold()
        self._hold_stop.clear()

        def loop() -> None:
            while not self._hold_stop.is_set():
                try:
                    with self._lock:
                        if not self.client:
                            break
                        self._write_state(self.client)
                except Exception:
                    break
                if self._hold_stop.wait(timeout=interval):
                    break

        self._hold_thread = threading.Thread(target=loop, daemon=True)
        self._hold_thread.start()

    def apply_axis(
        self,
        axis: AxisName,
        *,
        imode: int | None = None,
        pos: float | None = None,
        vel: float | None = None,
        pid: bool | None = None,
    ) -> None:
        cmd = self.state.axis(axis)
        if imode is not None:
            cmd.imode = imode
        if pos is not None:
            cmd.pos = pos
        if vel is not None:
            cmd.vel = vel
        if pid is not None:
            cmd.pid = pid

    def power_on_axis(self, axis: AxisName, seconds: float = 3.0) -> dict:
        self.apply_axis(axis, imode=MODE_POWER_ON, pid=False)
        self.send_once()
        self.start_hold(interval=0.2)
        time.sleep(seconds)
        self.stop_hold()
        return self.read_status()

    def power_on_all(self, seconds: float = 3.0) -> dict:
        for ax in AXES:
            self.apply_axis(ax, imode=MODE_POWER_ON, pid=False)
        self.send_once()
        self.start_hold(interval=0.2)
        time.sleep(seconds)
        self.stop_hold()
        return self.read_status()

    def power_off_axis(self, axis: AxisName) -> None:
        self.apply_axis(axis, imode=MODE_POWER_OFF, pid=False)
        self.send_once()

    def power_off_all(self) -> None:
        for ax in AXES:
            self.apply_axis(ax, imode=MODE_POWER_OFF, pid=False)
        for _ in range(5):
            self.send_once()
            time.sleep(0.2)

    def point_axis(self, axis: AxisName, pos: float, vel: float, pid: bool = True) -> None:
        self.apply_axis(axis, imode=MODE_POINT, pos=pos, vel=vel, pid=pid)
        self.start_hold(interval=0.1)

    def halt_axis(self, axis: AxisName, seconds: float = 2.0) -> None:
        self.apply_axis(axis, imode=MODE_HALT, pid=False)
        self.start_hold(interval=0.1)
        time.sleep(seconds)
        self.stop_hold()

    def halt_all(self, seconds: float = 2.0) -> None:
        for ax in AXES:
            self.apply_axis(ax, imode=MODE_HALT, pid=False)
        self.start_hold(interval=0.1)
        time.sleep(seconds)
        self.stop_hold()


ctrl = ModbusController()
tilt_job = TiltSurveyJob()


def _parse_body() -> dict:
    return request.get_json(silent=True) or {}


def _axis_from_body(data: dict) -> AxisName:
    name = str(data.get("axis", "")).lower()
    if name not in AXES:
        raise ValueError("axis 须为 az / el / ti")
    return name  # type: ignore[return-value]


@app.route("/")
def index():
    return render_template("antenna_control.html", default_host=DEFAULT_PLC_HOST)


@app.route("/api/connect", methods=["POST"])
def api_connect():
    data = _parse_body()
    try:
        ctrl.connect(str(data.get("host", DEFAULT_PLC_HOST)), int(data.get("port", 502)))
        return jsonify({"ok": True, "status": ctrl.read_status()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/disconnect", methods=["POST"])
def api_disconnect():
    ctrl.disconnect()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    if not ctrl.connected:
        return jsonify({"ok": True, "connected": False})
    try:
        return jsonify({"ok": True, "connected": True, "status": ctrl.read_status()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/axis/power-on", methods=["POST"])
def api_axis_power_on():
    if not ctrl.connected:
        return jsonify({"ok": False, "error": "未连接 PLC"}), 400
    data = _parse_body()
    try:
        axis = _axis_from_body(data)
        wait = float(data.get("wait", 3))
        if "pos" in data:
            ctrl.apply_axis(axis, pos=float(data["pos"]))
        st = ctrl.power_on_axis(axis, wait)
        labels = {"az": "方位", "el": "俯仰", "ti": "倾斜"}
        return jsonify({
            "ok": True,
            "message": f"{labels[axis]} 上电完成（iMode=1，{wait}s）",
            "status": st,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/power-on-all", methods=["POST"])
def api_power_on_all():
    if not ctrl.connected:
        return jsonify({"ok": False, "error": "未连接 PLC"}), 400
    data = _parse_body()
    try:
        for ax in AXES:
            if f"{ax}_pos" in data:
                ctrl.apply_axis(ax, pos=float(data[f"{ax}_pos"]))
        wait = float(data.get("wait", 3))
        st = ctrl.power_on_all(wait)
        return jsonify({"ok": True, "message": f"三轴上电完成（{wait}s）", "status": st})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/axis/point", methods=["POST"])
def api_axis_point():
    if not ctrl.connected:
        return jsonify({"ok": False, "error": "未连接 PLC"}), 400
    data = _parse_body()
    try:
        axis = _axis_from_body(data)
        pos = float(data["pos"])
        vel = float(data.get("vel", ctrl.state.axis(axis).vel))
        pid = not data.get("no_pid", False)
        ctrl.point_axis(axis, pos, vel, pid=pid)
        labels = {"az": "方位", "el": "俯仰", "ti": "倾斜"}
        return jsonify({"ok": True, "message": f"{labels[axis]} 指向 {pos}° 持续下发中"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/axis/power-off", methods=["POST"])
def api_axis_power_off():
    if not ctrl.connected:
        return jsonify({"ok": False, "error": "未连接 PLC"}), 400
    data = _parse_body()
    try:
        axis = _axis_from_body(data)
        ctrl.power_off_axis(axis)
        labels = {"az": "方位", "el": "俯仰", "ti": "倾斜"}
        return jsonify({"ok": True, "message": f"{labels[axis]} 下电已发送"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/power-off-all", methods=["POST"])
def api_power_off_all():
    if not ctrl.connected:
        return jsonify({"ok": False, "error": "未连接 PLC"}), 400
    try:
        ctrl.stop_hold()
        ctrl.power_off_all()
        return jsonify({"ok": True, "message": "三轴下电已发送"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/axis/halt", methods=["POST"])
def api_axis_halt():
    if not ctrl.connected:
        return jsonify({"ok": False, "error": "未连接 PLC"}), 400
    data = _parse_body()
    try:
        if data.get("all"):
            ctrl.halt_all(2.0)
            st = ctrl.read_status()
            return jsonify({"ok": True, "message": "三轴 Halt 完成", "status": st})
        axis = _axis_from_body(data)
        ctrl.halt_axis(axis, 2.0)
        labels = {"az": "方位", "el": "俯仰", "ti": "倾斜"}
        st = ctrl.read_status()
        return jsonify({"ok": True, "message": f"{labels[axis]} Halt 完成", "status": st})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@app.route("/api/stop-hold", methods=["POST"])
def api_stop_hold():
    ctrl.stop_hold()
    return jsonify({"ok": True, "message": "已停止持续下发"})


@app.route("/api/tilt-survey/start", methods=["POST"])
def api_tilt_survey_start():
    if tilt_job.running():
        return jsonify({"ok": False, "error": "倾斜扫描已在运行"}), 409
    data = _parse_body()
    try:
        params = TiltSurveyParams(
            plc_host=str(data.get("plc_host", ctrl.host if ctrl.connected else DEFAULT_PLC_HOST)),
            plc_port=int(data.get("plc_port", ctrl.port if ctrl.connected else 502)),
            sensor_host=str(data.get("sensor_host", SENSOR_DEFAULT_HOST)),
            sensor_port=int(data.get("sensor_port", SENSOR_DEFAULT_PORT)),
            sensor_address=int(data.get("sensor_address", SENSOR_DEFAULT_SLAVE)),
            ti_vel=float(data.get("ti_vel", 2.0)),
            step=int(data.get("step", 15)),
            dwell=float(data.get("dwell", 10.0)),
            interval=float(data.get("interval", 0.5)),
            settle_timeout=float(data.get("settle_timeout", 120.0)),
            output_dir=Path(data.get("output_dir", str(SURVEY_OUTPUT_DIR))),
            run_analysis=not data.get("no_analysis", False),
            save_plots=not data.get("no_plot", False),
        )
        tilt_job.start(params, stop_main_hold=ctrl.stop_hold)
        return jsonify({"ok": True, "message": "倾斜扫描已启动（仅 Ti，不写 Az/El）"})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@app.route("/api/tilt-survey/status")
def api_tilt_survey_status():
    return jsonify({"ok": True, "survey": tilt_job.snapshot()})


@app.route("/api/tilt-survey/stop", methods=["POST"])
def api_tilt_survey_stop():
    if not tilt_job.running():
        return jsonify({"ok": True, "message": "当前无运行中的扫描"})
    tilt_job.stop()
    return jsonify({"ok": True, "message": "正在停止倾斜扫描…"})


def main() -> int:
    ap = argparse.ArgumentParser(description="三轴 Modbus Web 控制")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()
    print(f"打开浏览器: http://{args.host}:{args.port}")
    print("轴映射: 方位=Axis2/HR8  俯仰=Axis1/HR19  倾斜=Axis3/HR30")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
