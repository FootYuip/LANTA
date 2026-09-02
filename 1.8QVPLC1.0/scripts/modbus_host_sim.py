#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟上位机 — 通过 Modbus TCP 控制天线（远控）。

基于 Modbus_Slave / SecurityCheck / *_ctrl_1 的 HR 映射实现。

子命令:
  status              读 IR 状态
  power-on            iMode=1 上电（俯仰+方位）
  power-off           iMode=0 下电
  halt                iMode=7 减速停
  point               iMode=2 指向指定 Az/El（PID 跟位）
  track               iMode=4 程引回放（可选真运动）

前置（CODESYS）:
  GVL.bLocalCtrl = FALSE
  程引时 GVL.bTimeSwich = TRUE
  现场安全、限位、人员清场后再使能运动

用法:
  python scripts/modbus_host_sim.py status
  python scripts/modbus_host_sim.py power-on --host 192.168.1.30
  python scripts/modbus_host_sim.py point --az 120 --el 100 --duration 30
  python scripts/modbus_host_sim.py track --input scripts/引导.txt --max-steps 500
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modbus_plc_codec import (  # noqa: E402
    CTRL_MOTION,
    DEFAULT_PLC_HOST,
    IR_REG_COUNT,
    MODE_CHENGYIN,
    MODE_HALT,
    MODE_POINT,
    MODE_POWER_OFF,
    MODE_POWER_ON,
    build_hr_block,
    clear_orbit_table,
    format_status,
    ir_to_feedback,
    read_ir,
    write_hr_block,
)
from modbus_replay_guidance import (  # noqa: E402
    load_guidance,
    prefill_orbit_table,
    replay,
    validate_spacing,
)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as e:
    raise SystemExit("请先安装: pip install pymodbus") from e


def connect(host: str, port: int) -> ModbusTcpClient:
    client = ModbusTcpClient(host, port=port)
    if not client.connect():
        raise SystemExit(f"无法连接 {host}:{port}")
    return client


def cmd_status(client: ModbusTcpClient) -> None:
    ir = read_ir(client, 0, IR_REG_COUNT)
    st = ir_to_feedback(ir)
    print(format_status(st))


def send_axes_mode(
    client: ModbusTcpClient,
    *,
    imode: int,
    az: float,
    el: float,
    ctrl: int,
    utc_ms: int | None = None,
    az_vel: float = 4.0,
    el_vel: float = 4.0,
) -> None:
    if utc_ms is None:
        utc_ms = int(time.time() * 1000)
    regs = build_hr_block(
        utc_pc_ms=utc_ms,
        utc_orbit_ms=None,
        az_deg=az,
        el_deg=el,
        ctrl_word=ctrl,
        imode_az=imode,
        imode_el=imode,
        az_vel_deg_s=az_vel,
        el_vel_deg_s=el_vel,
    )
    write_hr_block(client, regs, push_orbit=False)


def cmd_power_on(client: ModbusTcpClient, wait_s: float, az: float, el: float) -> None:
    print(f"上电 iMode=1，保持当前命令角 Az={az} El={el}，等待 {wait_s}s …")
    t_end = time.time() + wait_s
    while time.time() < t_end:
        send_axes_mode(
            client, imode=MODE_POWER_ON, az=az, el=el, ctrl=0
        )
        time.sleep(0.2)
    cmd_status(client)


def cmd_power_off(client: ModbusTcpClient) -> None:
    print("下电 iMode=0 …")
    for _ in range(15):
        send_axes_mode(client, imode=MODE_POWER_OFF, az=0, el=120, ctrl=0)
        time.sleep(0.2)
    cmd_status(client)


def cmd_halt(client: ModbusTcpClient, duration: float) -> None:
    print(f"halt iMode=7，持续 {duration}s …")
    t_end = time.time() + duration
    while time.time() < t_end:
        send_axes_mode(client, imode=MODE_HALT, az=0, el=120, ctrl=0)
        time.sleep(0.1)
    cmd_status(client)


def cmd_point(
    client: ModbusTcpClient,
    *,
    az: float,
    el: float,
    duration: float,
    interval: float,
    ctrl: int,
    az_vel: float,
    el_vel: float,
    tol: float,
) -> None:
    print(
        f"指向 iMode=2 → Az={az} El={el}，"
        f"Vel上限 Az={az_vel} El={el_vel} deg/s，持续 {duration}s"
    )
    t_end = time.time() + duration
    step = 0
    while time.time() < t_end:
        send_axes_mode(
            client,
            imode=MODE_POINT,
            az=az,
            el=el,
            ctrl=ctrl,
            az_vel=az_vel,
            el_vel=el_vel,
        )
        if step % max(1, int(1.0 / interval)) == 0:
            st = ir_to_feedback(read_ir(client, 0, IR_REG_COUNT))
            da = abs(st["az_deg"] - az)
            de = abs(st["el_deg"] - el)
            print(
                f"  t={st['ir_t_ms']:.0f}  "
                f"实际 Az={st['az_deg']:.3f} El={st['el_deg']:.3f}  "
                f"ΔAz={da:.3f} ΔEl={de:.3f}"
            )
            if da <= tol and de <= tol:
                print("  已到目标附近。")
        step += 1
        time.sleep(interval)
    cmd_status(client)


def cmd_track(
    client: ModbusTcpClient,
    *,
    path: Path,
    output: Path | None,
    interval: float,
    max_steps: int | None,
    motion: bool,
    no_reset: bool,
) -> None:
    import csv

    rows = load_guidance(path)
    validate_spacing(rows)
    ctrl = CTRL_MOTION if motion else 0
    if motion:
        print("程引 iMode=4 + HR[7] PID 使能 — 天线将跟随插值运动")
    else:
        print("程引 iMode=4，仅插值验证（未置 PID 使能位）")

    if not no_reset:
        print("清表 + 预填 …")
        clear_orbit_table(client)
        time.sleep(0.1)
        prefill_orbit_table(client, rows, ctrl_word=ctrl)

    out = output
    if out is None:
        stem = path.stem[:40].replace(" ", "_")
        out = Path(__file__).resolve().parent / "output" / f"host_track_{stem}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "step", "t_play_ms", "file_row", "file_t_ms", "az_cmd", "el_cmd",
        "orbit_push", "ir_t_ms", "rInterAz", "rInterEl", "delta_ms", "note",
    ]
    with out.open("w", newline="", encoding="utf-8") as fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        n = replay(
            client,
            rows,
            interval_s=interval,
            max_steps=max_steps,
            ctrl_word=ctrl,
            writer=w,
            out_fp=fp,
            flush_every=200,
        )
    print(f"程引完成 {n} 步，CSV: {out}")


def main() -> int:
    ap = argparse.ArgumentParser(description="模拟上位机 Modbus 控制天线")
    ap.add_argument("--host", default=DEFAULT_PLC_HOST)
    ap.add_argument("--port", type=int, default=502)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="读 IR 反馈")

    p_on = sub.add_parser("power-on", help="远控上电 iMode=1")
    p_on.add_argument("--wait", type=float, default=3.0, help="上电保持秒数")
    p_on.add_argument("--az", type=float, default=0.0, help="上电阶段命令方位(PLC坐标)")
    p_on.add_argument("--el", type=float, default=120.0, help="上电阶段命令俯仰(PLC坐标)")

    sub.add_parser("power-off", help="远控下电 iMode=0")
    p_halt = sub.add_parser("halt", help="减速停 iMode=7")
    p_halt.add_argument("--duration", type=float, default=3.0)

    p_pt = sub.add_parser("point", help="指向模式 iMode=2")
    p_pt.add_argument("--az", type=float, required=True)
    p_pt.add_argument("--el", type=float, required=True)
    p_pt.add_argument("--duration", type=float, default=60.0)
    p_pt.add_argument("--interval", type=float, default=0.1)
    p_pt.add_argument("--az-vel", type=float, default=4.0, help="HR[61] 方位指向速度上限 deg/s")
    p_pt.add_argument("--el-vel", type=float, default=4.0, help="HR[62] 俯仰指向速度上限 deg/s")
    p_pt.add_argument("--tolerance", type=float, default=0.05, help="到位判据 deg")
    p_pt.add_argument(
        "--no-pid-bits",
        action="store_true",
        help="不写 HR[7] PID 使能（仅验证命令下发）",
    )

    p_tr = sub.add_parser("track", help="程引 iMode=4 + 引导文件")
    p_tr.add_argument("--input", "-i", type=Path, required=True)
    p_tr.add_argument("--output", "-o", type=Path)
    p_tr.add_argument("--interval", type=float, default=0.01)
    p_tr.add_argument("--max-steps", type=int)
    p_tr.add_argument("--motion", action="store_true", help="置 HR[7] PID 使能，天线真动")
    p_tr.add_argument("--no-reset-table", action="store_true")

    args = ap.parse_args()
    print(f"连接 {args.host}:{args.port}")
    print("确认: GVL.bLocalCtrl=FALSE；运动前现场安全")
    print()

    client = connect(args.host, args.port)
    try:
        if args.cmd == "status":
            cmd_status(client)
        elif args.cmd == "power-on":
            cmd_power_on(client, args.wait, args.az, args.el)
        elif args.cmd == "power-off":
            cmd_power_off(client)
        elif args.cmd == "halt":
            cmd_halt(client, args.duration)
        elif args.cmd == "point":
            ctrl = 0 if args.no_pid_bits else CTRL_MOTION
            cmd_point(
                client,
                az=args.az,
                el=args.el,
                duration=args.duration,
                interval=args.interval,
                ctrl=ctrl,
                az_vel=args.az_vel,
                el_vel=args.el_vel,
                tol=args.tolerance,
            )
        elif args.cmd == "track":
            cmd_track(
                client,
                path=args.input,
                output=args.output,
                interval=args.interval,
                max_steps=args.max_steps,
                motion=args.motion,
                no_reset=args.no_reset_table,
            )
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
