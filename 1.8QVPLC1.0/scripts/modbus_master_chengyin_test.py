#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modbus TCP Master — 程引插值联调（PLC=Slave 192.168.1.30:502）

用法:
  pip install pymodbus
  python scripts/modbus_master_chengyin_test.py
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modbus_plc_codec import (  # noqa: E402
    DEFAULT_PLC_HOST,
    IR_REG_COUNT,
    build_hr_block,
    ir_theory_degs,
    read_ir,
    regs_to_ulint,
    write_hr,
)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as e:
    raise SystemExit("请先安装: pip install pymodbus") from e


def phase_fill_table(
    client: ModbusTcpClient,
    t0_ms: int,
    steps: int,
    dt_ms: int,
    ctrl_word: int,
) -> tuple[int, int]:
    print(f"--- 阶段1: 填轨道表 {steps} 点，间隔 {dt_ms} ms ---")
    last_utc = t0_ms
    for step in range(steps):
        utc = t0_ms + step * dt_ms
        el = 100.0 + step * 0.5
        az = -20.0 - step * 0.3
        regs = build_hr_block(
            utc_pc_ms=utc,
            utc_orbit_ms=utc,
            el_deg=el,
            az_deg=az,
            ctrl_word=ctrl_word,
        )
        write_hr(client, 0, regs)
        last_utc = utc
        print(f"  [{step:02d}] UTC_Orbit={utc}  El_plc={el:.2f}  Az_plc={az:.2f}")
        time.sleep(max(0.1, dt_ms / 1000.0))
    return t0_ms, last_utc


def phase_sweep_time(
    client: ModbusTcpClient,
    t_start: int,
    t_end: int,
    sweep_steps: int,
    poll_s: float,
    ctrl_word: int,
    el0: float,
    az0: float,
) -> None:
    span = t_end - t_start
    print(
        f"--- 阶段2: 持续推轨道 {sweep_steps} 帧，间隔 {int(poll_s * 1000)} ms，"
        f"UTC [{t_start} .. {t_end}]（跨度 {span} ms）---"
    )
    print("  IR_t_ms = PLC 上报 (dRealTime-8h)，应与列 UTC 接近（差几十 ms 正常）")
    first_el, first_az = float("nan"), float("nan")
    last_el, last_az = float("nan"), float("nan")

    for i in range(sweep_steps):
        if sweep_steps <= 1:
            frac = 0
        else:
            frac = i / (sweep_steps - 1)
        utc = t_start + int(span * frac)
        el = el0 + i * 0.5
        az = az0 - i * 0.3
        regs = build_hr_block(
            utc_pc_ms=utc,
            utc_orbit_ms=utc,
            el_deg=el,
            az_deg=az,
            ctrl_word=ctrl_word,
        )
        write_hr(client, 0, regs)
        try:
            ir = read_ir(client, 0, IR_REG_COUNT)
            t_ms_approx = regs_to_ulint(ir[0:4]) / 1_000_000.0
            az_t, el_t = ir_theory_degs(ir)
            if i == 0:
                first_el, first_az = el_t, az_t
            if i == sweep_steps - 1:
                last_el, last_az = el_t, az_t
            delta_ms = t_ms_approx - utc
            print(
                f"  [{i:03d}] UTC_write={utc}  IR_t_ms={t_ms_approx:.0f}  "
                f"delta={delta_ms:+.0f}ms  theory_Az={az_t:.4f}  theory_El={el_t:.4f}"
            )
        except RuntimeError as e:
            print(f"  [{i:03d}] UTC={utc}  (IR 读取跳过: {e})")
        time.sleep(poll_s)

    if first_el == last_el and first_az == last_az:
        print()
        print("  [提示] 理论角全程不变 → 检查 bTimeSwich、mode4、aUTC_TIME")


def main() -> int:
    ap = argparse.ArgumentParser(description="程引插值 Modbus 联调（默认仅看插值）")
    ap.add_argument("--host", default=DEFAULT_PLC_HOST)
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--table-steps", type=int, default=10)
    ap.add_argument("--dt-ms", type=int, default=100)
    ap.add_argument("--sweep-steps", type=int, default=30)
    ap.add_argument("--poll", type=float, default=0.1)
    ap.add_argument("--enable-pid-bits", action="store_true")
    args = ap.parse_args()

    ctrl = (1 << 11) | (1 << 12) if args.enable_pid_bits else 0

    print(f"连接 PLC Modbus Slave: {args.host}:{args.port}")
    print("CODESYS: GVL.bLocalCtrl=FALSE, GVL.bTimeSwich=TRUE")
    print()

    client = ModbusTcpClient(args.host, port=args.port)
    if not client.connect():
        raise SystemExit(f"无法连接 {args.host}:{args.port}")

    try:
        t0 = int(time.time() * 1000)
        t_start, t_end = phase_fill_table(
            client, t0, args.table_steps, args.dt_ms, ctrl
        )
        phase_sweep_time(
            client, t_start, t_end, args.sweep_steps, args.poll, ctrl, 100.0, -20.0
        )
    finally:
        client.close()

    print("完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
