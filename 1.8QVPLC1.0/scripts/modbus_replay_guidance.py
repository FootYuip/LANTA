#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
上位机引导文件 Modbus 回放 — 驱动 PLC 程引插值并落盘 CSV。

列映射（Tab 分隔）:
  第 1 列 (0): Unix 毫秒时间
  第 4 列 (3): 方位（PLC 坐标，原样）
  第 5 列 (4): 俯仰（PLC rPosCmd/aPosCmd 坐标，原样）

用法:
  pip install pymodbus
  python scripts/modbus_replay_guidance.py --input "path/to/引导.txt"
"""

from __future__ import annotations

import argparse
import bisect
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from modbus_plc_codec import (  # noqa: E402
    DEFAULT_PLC_HOST,
    IR_REG_COUNT,
    build_hr_block,
    clear_orbit_table,
    ir_to_inter_pos,
    read_ir,
    write_hr_block,
)

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as e:
    raise SystemExit("请先安装: pip install pymodbus") from e


@dataclass(frozen=True)
class GuidanceRow:
    line_no: int
    t_ms: int
    az: float
    el: float


def load_guidance(path: Path) -> list[GuidanceRow]:
    rows: list[GuidanceRow] = []
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 5:
                raise ValueError(f"行 {line_no}: 列数不足 5")
            rows.append(
                GuidanceRow(
                    line_no=line_no,
                    t_ms=int(parts[0]),
                    az=float(parts[3]),
                    el=float(parts[4]),
                )
            )
    if not rows:
        raise ValueError("引导文件无有效行")
    return rows


def validate_spacing(rows: list[GuidanceRow], expect_ms: int = 100) -> None:
    bad = []
    for i in range(1, len(rows)):
        d = rows[i].t_ms - rows[i - 1].t_ms
        if d != expect_ms:
            bad.append((rows[i].line_no, d))
    if bad:
        print(f"[警告] 共 {len(bad)} 处时间间隔不是 {expect_ms}ms，首条: {bad[:3]}")


def prefill_orbit_table(
    client: ModbusTcpClient,
    rows: list[GuidanceRow],
    *,
    ctrl_word: int,
    n_points: int = 10,
    gap_s: float = 0.02,
) -> None:
    """快速推入前 n 个引导点，填满 10 点 FIFO 后再做 10ms 实时回放。"""
    n = min(n_points, len(rows))
    print(f"--- 预填轨道表 {n} 点（间隔 {gap_s*1000:.0f}ms）---")
    for i in range(n):
        r = rows[i]
        regs = build_hr_block(
            utc_pc_ms=r.t_ms,
            utc_orbit_ms=r.t_ms,
            el_deg=r.el,
            az_deg=r.az,
            ctrl_word=ctrl_word,
        )
        write_hr_block(client, regs, push_orbit=True)
        time.sleep(gap_s)
        print(f"  [{i:02d}] UTC_Orbit={r.t_ms}  Az={r.az:.4f}  El={r.el:.4f}")


def index_at_time(times: list[int], t_play: int) -> int:
    """最后一个 times[i] <= t_play 的下标。"""
    i = bisect.bisect_right(times, t_play) - 1
    return max(0, min(i, len(times) - 1))


def replay(
    client: ModbusTcpClient,
    rows: list[GuidanceRow],
    *,
    interval_s: float,
    max_steps: int | None,
    ctrl_word: int,
    writer: csv.DictWriter,
    out_fp,
    flush_every: int,
) -> int:
    times = [r.t_ms for r in rows]
    time_set = set(times)
    t0 = times[0]
    t_end = times[-1]
    total_steps = (t_end - t0) // 10 + 1
    if max_steps is not None:
        total_steps = min(total_steps, max_steps)

    print(f"引导: {len(rows)} 点, t=[{t0} .. {t_end}], 回放步数≈{total_steps}, 间隔={interval_s*1000:.0f}ms")

    last_inter_az = last_inter_el = None
    step = 0

    for k in range(total_steps):
        t_play = t0 + k * 10
        t_loop_start = time.perf_counter()

        idx = index_at_time(times, t_play)
        row = rows[idx]
        push_orbit = t_play in time_set
        utc_orbit = t_play if push_orbit else None

        regs = build_hr_block(
            utc_pc_ms=t_play,
            utc_orbit_ms=utc_orbit,
            el_deg=row.el,
            az_deg=row.az,
            ctrl_word=ctrl_word,
        )
        write_hr_block(client, regs, push_orbit=push_orbit)

        note = "orbit" if push_orbit else ""
        ir_t_ms = r_az = r_el = float("nan")
        delta_ms = float("nan")
        try:
            ir = read_ir(client, 0, IR_REG_COUNT)
            ir_t_ms, r_az, r_el = ir_to_inter_pos(ir)
            delta_ms = ir_t_ms - t_play
            if last_inter_az is not None and r_az == last_inter_az and r_el == last_inter_el:
                if not note:
                    note = "clamp?"
        except RuntimeError as exc:
            note = f"ir_err:{exc}"

        last_inter_az, last_inter_el = r_az, r_el

        writer.writerow(
            {
                "step": k,
                "t_play_ms": t_play,
                "file_row": row.line_no,
                "file_t_ms": row.t_ms,
                "az_cmd": row.az,
                "el_cmd": row.el,
                "orbit_push": int(push_orbit),
                "ir_t_ms": ir_t_ms,
                "rInterAz": r_az,
                "rInterEl": r_el,
                "delta_ms": delta_ms,
                "note": note,
            }
        )
        if flush_every and (k + 1) % flush_every == 0:
            out_fp.flush()

        step = k + 1
        if step % 500 == 0:
            print(f"  step {step}/{total_steps}  t={t_play}  rInterAz={r_az:.4f}  rInterEl={r_el:.4f}")

        elapsed = time.perf_counter() - t_loop_start
        sleep_s = interval_s - elapsed
        if sleep_s > 0:
            time.sleep(sleep_s)

    return step


def main() -> int:
    ap = argparse.ArgumentParser(description="引导文件 Modbus 回放并记录插值结果")
    ap.add_argument("--input", "-i", required=True, type=Path, help="引导 TXT 路径")
    ap.add_argument("--output", "-o", type=Path, help="输出 CSV（默认 scripts/output/）")
    ap.add_argument("--host", default=DEFAULT_PLC_HOST)
    ap.add_argument("--port", type=int, default=502)
    ap.add_argument("--interval", type=float, default=0.01, help="步进间隔 s，默认 0.01=10ms 实时")
    ap.add_argument("--max-steps", type=int, default=None, help="调试用：最多跑 N 步")
    ap.add_argument("--enable-pid-bits", action="store_true")
    ap.add_argument(
        "--no-reset-table",
        action="store_true",
        help="跳过清表/预填（仅当表中已是本文件递增 UTC 时用）",
    )
    args = ap.parse_args()

    if not args.input.is_file():
        raise SystemExit(f"文件不存在: {args.input}")

    out = args.output
    if out is None:
        stem = args.input.stem[:40].replace(" ", "_")
        out = Path(__file__).resolve().parent / "output" / f"guidance_replay_{stem}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = load_guidance(args.input)
    validate_spacing(rows)
    r0 = rows[0]
    print(
        f"引导首点: t={r0.t_ms}  Az={r0.az:.4f}  El={r0.el:.4f}  "
        f"(若 IR 一直是 -20/100，多为联调残留表未更新)"
    )

    ctrl = (1 << 11) | (1 << 12) if args.enable_pid_bits else 0

    print(f"连接 PLC: {args.host}:{args.port}")
    print("CODESYS: GVL.bLocalCtrl=FALSE, GVL.bTimeSwich=TRUE, 伺服勿使能")
    print(f"输出: {out}")
    print()

    client = ModbusTcpClient(args.host, port=args.port)
    if not client.connect():
        raise SystemExit(f"无法连接 {args.host}:{args.port}")

    if not args.no_reset_table:
        print("--- 清空旧轨道表（iMode=0）---")
        clear_orbit_table(client, ctrl_word=ctrl)
        time.sleep(0.1)
        prefill_orbit_table(client, rows, ctrl_word=ctrl)
        try:
            ir = read_ir(client, 0, IR_REG_COUNT)
            _, az, el = ir_to_inter_pos(ir)
            print(f"预填后 IR 角: Az={az:.4f}  El={el:.4f}  (应接近首点 {r0.az:.4f}/{r0.el:.4f})")
        except RuntimeError as exc:
            print(f"预填后读 IR 跳过: {exc}")
        print()

    fieldnames = [
        "step",
        "t_play_ms",
        "file_row",
        "file_t_ms",
        "az_cmd",
        "el_cmd",
        "orbit_push",
        "ir_t_ms",
        "rInterAz",
        "rInterEl",
        "delta_ms",
        "note",
    ]

    try:
        with out.open("w", newline="", encoding="utf-8") as fp:
            w = csv.DictWriter(fp, fieldnames=fieldnames)
            w.writeheader()
            n = replay(
                client,
                rows,
                interval_s=args.interval,
                max_steps=args.max_steps,
                ctrl_word=ctrl,
                writer=w,
                out_fp=fp,
                flush_every=200,
            )
            fp.flush()
    finally:
        client.close()

    print(f"完成，共 {n} 步，已写入 {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
