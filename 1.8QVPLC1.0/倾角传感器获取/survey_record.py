#!/usr/bin/env python3
"""
倾角传感器方位采集程序

流程（循环，输入 q 结束并统一保存）：
  1. 输入方位角
  2. 自动采集 20 秒数据
  3. 处理并显示该方位结果
  4. 等待输入下一个方位角，重复
  5. 输入 q → 停止采集，将所有数据一次性存入 txt + csv

用法: python survey_record.py
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from read_inclinometer import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_SLAVE,
    PersistentInclinometerReader,
)

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "records"


@dataclass
class Sample:
    azimuth: float
    time: datetime
    x: float
    y: float


@dataclass
class AzimuthSegment:
    segment_id: int
    azimuth: float
    start: datetime
    end: datetime
    samples: list[Sample] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.samples)

    @property
    def avg_x(self) -> float:
        return sum(s.x for s in self.samples) / self.count

    @property
    def avg_y(self) -> float:
        return sum(s.y for s in self.samples) / self.count

    @property
    def duration(self) -> float:
        return (self.end - self.start).total_seconds()


@dataclass
class SurveySession:
    segments: list[AzimuthSegment] = field(default_factory=list)

    @property
    def all_samples(self) -> list[Sample]:
        result: list[Sample] = []
        for seg in self.segments:
            result.extend(seg.samples)
        return result


def generate_tilt_stops(step: int = 15) -> list[float]:
    """倾斜扫描角序列：-180→0（含 0），再 15→180（0 不重复）。"""
    if step <= 0 or 360 % step != 0:
        raise ValueError("step 须为正且 360 可被整除")
    first = [float(x) for x in range(-180, 1, step)]
    second = [float(x) for x in range(15, 181, step)]
    return first + second


def prompt_azimuth() -> float | None:
    while True:
        raw = input("\n请输入方位角（度），输入 q 结束并保存: ").strip()
        if raw.lower() == "q":
            return None
        try:
            return float(raw)
        except ValueError:
            print("请输入有效数字，例如: 45.5")


def collect_for_duration(
    reader: PersistentInclinometerReader,
    azimuth: float,
    duration: float,
    interval: float,
) -> list[Sample]:
    samples: list[Sample] = []
    start = time.time()
    index = 0

    print(f"\n方位角 {azimuth:.3f}° — 自动采集 {duration:.0f} 秒...\n")
    while time.time() - start < duration:
        t0 = time.time()
        index += 1
        try:
            x, y = reader.read_angles_with_retry(retries=2)
            now = datetime.now()
            samples.append(Sample(azimuth, now, x, y))
            elapsed = time.time() - start
            print(
                f"  [{elapsed:5.1f}s] #{index:3d}  "
                f"方位={azimuth:.1f}°  X={x:+.3f}°  Y={y:+.3f}°",
                flush=True,
            )
        except Exception as exc:
            print(f"  读取失败: {exc}", file=sys.stderr)

        spent = time.time() - t0
        sleep_t = max(0.0, interval - spent)
        if time.time() + sleep_t < start + duration:
            time.sleep(sleep_t)

    return samples


def show_segment_result(segment: AzimuthSegment) -> None:
    xs = [s.x for s in segment.samples]
    ys = [s.y for s in segment.samples]

    print("\n" + "-" * 50)
    print(f"方位角 {segment.azimuth:.3f}°  处理结果")
    print("-" * 50)
    print(f"  采集时段:   {segment.start:%H:%M:%S} ~ {segment.end:%H:%M:%S}")
    print(f"  采集时长:   {segment.duration:.1f} 秒")
    print(f"  有效条数:   {segment.count}")
    print(f"  X 平均值:   {segment.avg_x:+.3f}°")
    print(f"  Y 平均值:   {segment.avg_y:+.3f}°")
    print(f"  X 范围:     {min(xs):+.3f}° ~ {max(xs):+.3f}°")
    print(f"  Y 范围:     {min(ys):+.3f}° ~ {max(ys):+.3f}°")
    print("-" * 50)


def save_session(session: SurveySession, output_dir: Path) -> tuple[Path, Path] | None:
    if not session.segments:
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = output_dir / f"survey_{stamp}"

    txt_path = base.with_suffix(".txt")
    csv_path = base.with_suffix(".csv")
    all_samples = session.all_samples

    with txt_path.open("w", encoding="utf-8") as f:
        f.write("倾角传感器方位采集记录（完整会话）\n")
        f.write("=" * 60 + "\n")
        f.write(f"方位角数量: {len(session.segments)}\n")
        f.write(f"总数据条数: {len(all_samples)}\n")
        f.write(f"保存时间:   {datetime.now():%Y-%m-%d %H:%M:%S}\n\n")

        f.write("各方位角汇总\n")
        f.write("-" * 60 + "\n")
        for seg in session.segments:
            f.write(
                f"方位角 {seg.azimuth:.3f}°  "
                f"条数={seg.count}  "
                f"X均值={seg.avg_x:+.3f}°  Y均值={seg.avg_y:+.3f}°  "
                f"时段 {seg.start:%H:%M:%S}~{seg.end:%H:%M:%S}\n"
            )

        f.write("\n全部明细数据\n")
        f.write("-" * 60 + "\n")
        f.write(f"{'时间':<22} {'方位角(°)':>10} {'X(°)':>10} {'Y(°)':>10}\n")
        f.write("-" * 60 + "\n")
        for s in all_samples:
            ts = s.time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            f.write(f"{ts:<22} {s.azimuth:10.3f} {s.x:10.3f} {s.y:10.3f}\n")

    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["方位角(度)", "时间", "X(度)", "Y(度)"])
        for s in all_samples:
            writer.writerow([
                f"{s.azimuth:.3f}",
                s.time.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                f"{s.x:.3f}",
                f"{s.y:.3f}",
            ])

        writer.writerow([])
        writer.writerow(["--- 各方位角汇总 ---"])
        writer.writerow([
            "方位角(度)", "条数", "X平均值(度)", "Y平均值(度)",
            "开始时间", "结束时间",
        ])
        for seg in session.segments:
            writer.writerow([
                f"{seg.azimuth:.3f}",
                seg.count,
                f"{seg.avg_x:.3f}",
                f"{seg.avg_y:.3f}",
                seg.start.strftime("%Y-%m-%d %H:%M:%S"),
                seg.end.strftime("%Y-%m-%d %H:%M:%S"),
            ])

    return txt_path, csv_path


def run_session(
    reader: PersistentInclinometerReader,
    collect_seconds: float,
    interval: float,
    output_dir: Path,
) -> None:
    session = SurveySession()
    segment_id = 1

    while True:
        azimuth = prompt_azimuth()
        if azimuth is None:
            break

        start = datetime.now()
        samples = collect_for_duration(reader, azimuth, collect_seconds, interval)
        end = datetime.now()

        if not samples:
            print("本次未采集到有效数据，请重新输入方位角。", file=sys.stderr)
            continue

        segment = AzimuthSegment(
            segment_id=segment_id,
            azimuth=azimuth,
            start=start,
            end=end,
            samples=samples,
        )
        session.segments.append(segment)
        segment_id += 1

        show_segment_result(segment)
        print(f"（已缓存 {len(session.all_samples)} 条，输入 q 结束并保存）")

    if not session.segments:
        print("\n未采集任何数据，不保存文件。")
        return

    print("\n正在保存全部数据...")
    paths = save_session(session, output_dir)
    if paths:
        txt_path, csv_path = paths
        print(f"\n会话结束，共 {len(session.segments)} 个方位角，"
              f"{len(session.all_samples)} 条数据")
        print(f"  {txt_path}")
        print(f"  {csv_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="倾角传感器方位采集（长连接）")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("-a", "--address", type=lambda x: int(x, 0), default=DEFAULT_SLAVE)
    parser.add_argument(
        "-d", "--duration",
        type=float,
        default=20.0,
        help="每个方位角自动采集时长（秒），默认 20",
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=0.5,
        help="采样间隔（秒），默认 0.5",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=OUTPUT_DIR,
        help="数据保存目录",
    )
    args = parser.parse_args()

    print("倾角传感器方位采集程序")
    print(f"设备: {args.host}:{args.port}  保存目录: {args.output}")
    print(f"每个方位角自动采集 {args.duration:.0f} 秒，输入 q 结束并统一保存\n")

    try:
        with PersistentInclinometerReader(
            args.host,
            args.port,
            slave=args.address,
        ) as reader:
            print("传感器长连接已建立。")
            run_session(reader, args.duration, args.interval, args.output)
    except KeyboardInterrupt:
        print("\n\n程序已中断")
    finally:
        print("连接已关闭，再见。")


if __name__ == "__main__":
    main()
