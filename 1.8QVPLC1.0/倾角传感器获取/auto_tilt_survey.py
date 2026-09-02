#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
倾斜轴自动扫描 + BWM427S 倾角采集 + 自动分析。

仅驱动 PLC 倾斜轴（Ti）按 -180°→0°→180°、步距 15° 停驻采集；
方位/俯仰不做任何 Modbus 操作。到位 |实际−目标| < 0.05° 后才开始采集。

用法:
  pip install pymodbus
  python auto_tilt_survey.py --dry-run
  python auto_tilt_survey.py --plc-host 192.168.1.30 --sensor-host 192.168.1.168
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(ROOT / "scripts"))

from read_inclinometer import (
    DEFAULT_HOST as SENSOR_DEFAULT_HOST,
    DEFAULT_PORT as SENSOR_DEFAULT_PORT,
    DEFAULT_SLAVE,
    PersistentInclinometerReader,
)
from survey_record import OUTPUT_DIR, generate_tilt_stops

from modbus_plc_codec import DEFAULT_PLC_HOST
from ti_only_plc import TiOnlyPlc
from tilt_survey_job import (
    DEFAULT_TI_VEL,
    TiltSurveyParams,
    finalize_session,
    run_tilt_survey,
)


def main() -> int:
    ap = argparse.ArgumentParser(description="倾斜轴自动扫描 + 倾角采集（仅 Ti）")
    ap.add_argument("--plc-host", default=DEFAULT_PLC_HOST)
    ap.add_argument("--plc-port", type=int, default=502)
    ap.add_argument("--sensor-host", default=SENSOR_DEFAULT_HOST)
    ap.add_argument("--sensor-port", type=int, default=SENSOR_DEFAULT_PORT)
    ap.add_argument("-a", "--sensor-address", type=lambda x: int(x, 0), default=DEFAULT_SLAVE)
    ap.add_argument("--ti-vel", type=float, default=DEFAULT_TI_VEL, help="倾斜指向速度上限 °/s")
    ap.add_argument("--step", type=int, default=15, help="倾斜扫描步距（度）")
    ap.add_argument("-d", "--dwell", type=float, default=10.0, help="每点停驻采集秒数")
    ap.add_argument("-i", "--interval", type=float, default=0.5, help="传感器采样间隔秒")
    ap.add_argument("--settle-timeout", type=float, default=120.0, help="每点到位超时秒")
    ap.add_argument("-o", "--output", type=Path, default=OUTPUT_DIR)
    ap.add_argument("--dry-run", action="store_true", help="只打印扫描角序列")
    ap.add_argument("--no-analysis", action="store_true")
    ap.add_argument("--no-plot", action="store_true")
    args = ap.parse_args()

    stops = generate_tilt_stops(args.step)
    print("倾斜轴自动扫描 + 倾角采集（仅 Ti，不写 Az/El HR）")
    print(f"扫描点: {len(stops)} 个  步距 {args.step}°  每点停 {args.dwell}s  到位 < 0.05°")
    print(f"Ti 速度上限={args.ti_vel}°/s")
    print(f"PLC {args.plc_host}:{args.plc_port}  传感器 {args.sensor_host}:{args.sensor_port}")
    print("前置: GVL.bLocalCtrl=FALSE；原上位机 Modbus 勿同时写 HR\n")

    if args.dry_run:
        print("扫描序列:", stops)
        return 0

    plc = TiOnlyPlc()
    session = None

    def log(msg: str) -> None:
        print(msg)

    try:
        print("连接 PLC…")
        plc.connect(args.plc_host, args.plc_port)
        print("连接倾角传感器…")
        with PersistentInclinometerReader(
            args.sensor_host,
            args.sensor_port,
            slave=args.sensor_address,
        ) as reader:
            print("传感器长连接已建立。\n")
            session = run_tilt_survey(
                plc,
                reader,
                stops=stops,
                ti_vel=args.ti_vel,
                dwell=args.dwell,
                interval=args.interval,
                settle_timeout=args.settle_timeout,
                log=log,
            )
    except KeyboardInterrupt:
        print("\n\n用户中断，保存已采集数据…", file=sys.stderr)
    finally:
        try:
            plc.stop_hold()
            plc.power_off_ti()
        except Exception:
            pass
        try:
            plc.disconnect()
        except Exception:
            pass

    if session:
        finalize_session(
            session,
            args.output,
            run_analysis_flag=not args.no_analysis,
            save_plots=not args.no_plot,
            log=log,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
