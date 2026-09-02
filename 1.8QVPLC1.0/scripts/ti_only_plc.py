#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仅操作 PLC 倾斜轴 HR，不写方位/俯仰寄存器。"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from modbus_plc_codec import (
    DEFAULT_PLC_HOST,
    IR_REG_COUNT,
    MODE_POINT,
    MODE_POWER_OFF,
    MODE_POWER_ON,
    ir_to_feedback,
    read_ir,
    write_hr_ti_only,
)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as e:
    raise ImportError("请先安装: pip install pymodbus") from e


@dataclass
class TiCommand:
    imode: int = MODE_POWER_OFF
    pos: float = 0.0
    vel: float = 2.0
    pid: bool = False


class TiOnlyPlc:
    """倾斜轴专用 Modbus 客户端：全程不写入 Az/El 相关 HR。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.client: ModbusTcpClient | None = None
        self.host = DEFAULT_PLC_HOST
        self.port = 502
        self.cmd = TiCommand()
        self._hold_stop = threading.Event()
        self._hold_thread: threading.Thread | None = None

    @property
    def connected(self) -> bool:
        return self.client is not None

    def connect(self, host: str, port: int = 502) -> None:
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

    def set_command(
        self,
        *,
        imode: int | None = None,
        pos: float | None = None,
        vel: float | None = None,
        pid: bool | None = None,
    ) -> None:
        if imode is not None:
            self.cmd.imode = imode
        if pos is not None:
            self.cmd.pos = pos
        if vel is not None:
            self.cmd.vel = vel
        if pid is not None:
            self.cmd.pid = pid

    def write_ti_once(self) -> None:
        with self._lock:
            client = self._require_client()
            write_hr_ti_only(
                client,
                imode_ti=self.cmd.imode,
                ti_deg=self.cmd.pos,
                ti_vel_deg_s=self.cmd.vel,
                ti_pid=self.cmd.pid,
            )

    def read_status(self) -> dict:
        with self._lock:
            ir = read_ir(self._require_client(), 0, IR_REG_COUNT)
            st = ir_to_feedback(ir)
            st["host"] = self.host
            st["port"] = self.port
            return st

    def _require_client(self) -> ModbusTcpClient:
        if not self.client:
            raise RuntimeError("未连接 PLC")
        return self.client

    def stop_hold(self) -> None:
        self._hold_stop.set()
        t = self._hold_thread
        if t and t.is_alive():
            t.join(timeout=2.5)
        with self._lock:
            self._hold_thread = None

    def start_hold(self, interval: float = 0.1) -> None:
        self.stop_hold()
        self._hold_stop.clear()

        def loop() -> None:
            while not self._hold_stop.is_set():
                try:
                    self.write_ti_once()
                except Exception:
                    break
                if self._hold_stop.wait(timeout=interval):
                    break

        self._hold_thread = threading.Thread(target=loop, daemon=True)
        self._hold_thread.start()

    def power_on_ti(self, seconds: float = 3.0) -> None:
        self.set_command(imode=MODE_POWER_ON, pid=False)
        self.write_ti_once()
        self.start_hold(0.2)
        time.sleep(seconds)
        self.stop_hold()

    def power_off_ti(self) -> None:
        self.set_command(imode=MODE_POWER_OFF, pid=False)
        for _ in range(3):
            self.write_ti_once()
            time.sleep(0.2)


def wait_ti_in_position(
    plc: TiOnlyPlc,
    target: float,
    *,
    pos_tol: float = 0.05,
    timeout: float = 120.0,
    poll: float = 0.2,
    cancel_event: threading.Event | None = None,
) -> bool:
    """|实际 Ti − 目标| < pos_tol 后返回 True。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cancel_event and cancel_event.is_set():
            return False
        st = plc.read_status()
        if abs(st["ti_deg"] - target) < pos_tol:
            return True
        time.sleep(poll)
    return False
