#!/usr/bin/env python3
"""
斜面倾角分析：各方位 β = 90° - Y均值 为与水平面夹角，拟合三维平面并可视化。

用法:
  python analyze_survey.py records/survey_20250605_163000.csv
  python analyze_survey.py --demo
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "records"

DEMO_DATA: list[tuple[float, float, float]] = [
    (0.0, 0.720, 83.260),
    (30.0, 0.730, 83.280),
    (60.0, 0.734, 83.307),
    (90.0, 0.727, 83.330),
    (120.0, 0.699, 83.346),
    (150.0, 0.670, 83.347),
    (180.0, 0.640, 83.330),
    (-30.0, 0.704, 83.245),
    (-60.0, 0.680, 83.247),
    (-90.0, 0.660, 83.257),
    (-120.0, 0.632, 83.278),
    (-150.0, 0.630, 83.304),
]


@dataclass
class AzimuthMean:
    azimuth: float
    x_mean: float
    y_mean: float
    count: int = 0

    @property
    def ground_angle(self) -> float:
        """与大地水平面的夹角 β = 90° - Y均值。"""
        return 90.0 - self.y_mean

    @property
    def slope(self) -> float:
        return math.tan(math.radians(self.ground_angle))


@dataclass
class PlaneFit:
    """拟合 tan(β(ψ)) = t0 + p·cos(ψ) + q·sin(ψ)，平面 z = p·x + q·y + z0。"""
    t0: float
    p: float
    q: float
    beta_mean: float
    r_squared: float
    residual_std: float
    total_tilt: float
    dip_azimuth: float
    beta_at_zero: float
    x_at_zero: float

    def tan_beta(self, azimuth_deg: float) -> float:
        rad = math.radians(azimuth_deg)
        return self.t0 + self.p * math.cos(rad) + self.q * math.sin(rad)

    def ground_angle_at_azimuth(self, azimuth_deg: float) -> float:
        return math.degrees(math.atan(self.tan_beta(azimuth_deg)))

    def height(self, x: float, y: float) -> float:
        return self.p * x + self.q * y

    def upslope_unit_vector(self) -> tuple[float, float]:
        """上坡方向单位向量（XY 平面，0° 沿 X 轴）。"""
        rad = math.radians(self.dip_azimuth)
        return math.cos(rad), math.sin(rad)


def load_survey_csv(path: Path) -> list[AzimuthMean]:
    groups: dict[float, list[tuple[float, float]]] = {}

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        rows = list(reader)

    detail_start = None
    for i, row in enumerate(rows):
        if len(row) >= 4 and row[0] == "方位角(度)" and row[2] == "X(度)":
            detail_start = i + 1
            break

    if detail_start is None:
        raise ValueError(f"无法识别 CSV 格式: {path}")

    for row in rows[detail_start:]:
        if not row or row[0].startswith("---"):
            break
        try:
            az = float(row[0])
            x = float(row[2])
            y = float(row[3])
        except (ValueError, IndexError):
            continue
        groups.setdefault(az, []).append((x, y))

    if not groups:
        raise ValueError(f"CSV 中无有效数据: {path}")

    return [
        AzimuthMean(
            azimuth=az,
            x_mean=sum(p[0] for p in pts) / len(pts),
            y_mean=sum(p[1] for p in pts) / len(pts),
            count=len(pts),
        )
        for az, pts in sorted(groups.items())
    ]


def load_demo_data() -> list[AzimuthMean]:
    return [AzimuthMean(az, x, y, count=41) for az, x, y in DEMO_DATA]


def fit_plane_from_ground_angles(data: list[AzimuthMean]) -> PlaneFit:
    """
    拟合 tan(β(ψ)) = t0 + p·cos(ψ) + q·sin(ψ)。
    β = 90° - Y；p,q 为相对水平面的坡度变化，总倾角 θ = atan(√(p²+q²))。
    """
    if len(data) < 3:
        raise ValueError("至少需要 3 个方位角数据点")

    n = len(data)
    azimuths = [d.azimuth for d in data]
    tan_betas = [d.slope for d in data]
    beta_mean = sum(d.ground_angle for d in data) / len(data)

    fit = _harmonic_fit_3(azimuths, tan_betas)
    t0, p, q = fit.a0, fit.a1, fit.a2

    beta_pred = [math.degrees(math.atan(t0 + p * math.cos(math.radians(az))
                                + q * math.sin(math.radians(az))))
                 for az in azimuths]
    beta_meas = [d.ground_angle for d in data]
    residuals = [m - pr for m, pr in zip(beta_meas, beta_pred)]
    ss_res = sum(r * r for r in residuals)
    mean_b = sum(beta_meas) / n
    ss_tot = sum((b - mean_b) ** 2 for b in beta_meas)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    residual_std = math.sqrt(ss_res / (n - 3)) if n > 3 else 0.0

    total_tilt = math.degrees(math.atan(math.sqrt(p * p + q * q)))
    dip_az = math.degrees(math.atan2(q, p)) % 360.0

    at_zero = _nearest_azimuth(data, 0.0)
    beta_at_zero = at_zero.ground_angle if at_zero else beta_mean
    x_at_zero = at_zero.x_mean if at_zero else float("nan")

    return PlaneFit(
        t0=t0,
        p=p,
        q=q,
        beta_mean=beta_mean,
        r_squared=r_squared,
        residual_std=residual_std,
        total_tilt=total_tilt,
        dip_azimuth=dip_az,
        beta_at_zero=beta_at_zero,
        x_at_zero=x_at_zero,
    )


def _nearest_azimuth(data: list[AzimuthMean], target: float) -> AzimuthMean | None:
    if not data:
        return None
    return min(data, key=lambda d: abs((d.azimuth - target + 180) % 360 - 180))


@dataclass
class _Harmonic3:
    a0: float
    a1: float
    a2: float
    r_squared: float
    residual_std: float


def _harmonic_fit_3(azimuths: list[float], values: list[float]) -> _Harmonic3:
    n = len(azimuths)
    s_cc = s_ss = s_cs = s_c = s_s = 0.0
    sum_v = 0.0
    s_cv = s_sv = 0.0
    for az, v in zip(azimuths, values):
        c = math.cos(math.radians(az))
        s = math.sin(math.radians(az))
        s_cc += c * c
        s_ss += s * s
        s_cs += c * s
        s_c += c
        s_s += s
        sum_v += v
        s_cv += c * v
        s_sv += s * v

    ata = [[n, s_c, s_s], [s_c, s_cc, s_cs], [s_s, s_cs, s_ss]]
    atv = [sum_v, s_cv, s_sv]
    a0, a1, a2 = _solve_3x3(ata, atv)

    predicted = [a0 + a1 * math.cos(math.radians(az)) + a2 * math.sin(math.radians(az))
                 for az in azimuths]
    residuals = [v - pr for v, pr in zip(values, predicted)]
    ss_res = sum(r * r for r in residuals)
    mean_v = sum_v / n
    ss_tot = sum((v - mean_v) ** 2 for v in values)
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0
    residual_std = math.sqrt(ss_res / (n - 3)) if n > 3 else 0.0

    return _Harmonic3(a0, a1, a2, r_squared, residual_std)


def _solve_3x3(m: list[list[float]], b: list[float]) -> tuple[float, float, float]:
    a = [row[:] + [bi] for row, bi in zip(m, b)]
    for col in range(3):
        pivot = max(range(col, 3), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("拟合矩阵奇异，请检查方位角是否足够分散")
        a[col], a[pivot] = a[pivot], a[col]
        div = a[col][col]
        for j in range(4):
            a[col][j] /= div
        for row in range(3):
            if row == col:
                continue
            factor = a[row][col]
            for j in range(4):
                a[row][j] -= factor * a[col][j]
    return a[0][3], a[1][3], a[2][3]


def build_report(
    data: list[AzimuthMean],
    plane: PlaneFit,
    source: str,
    *,
    extra_header: str | None = None,
) -> str:
    lines: list[str] = []
    if extra_header:
        lines.append(extra_header)
        lines.append("")
    lines.append("斜面倾角分析报告")
    lines.append("=" * 60)
    lines.append(f"数据来源:   {source}")
    lines.append(f"分析时间:   {datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append(f"方位角数量: {len(data)}")
    lines.append("")
    lines.append("方法: 各方位 β = 90° - Y均值 为与水平面夹角")
    lines.append("      拟合平面 z = p·x + q·y（x 沿 0° 方位，y 沿 90° 方位）")
    lines.append("假设: 0° = 传感器 X 轴零位；绕铅垂轴旋转")
    lines.append("")

    betas = [d.ground_angle for d in data]
    lines.append("【结论摘要（以方位 0° = X 轴零位为准）】")
    lines.append(f"  1. 安装基准倾角（β 均值）: {plane.beta_mean:.4f}°")
    lines.append("     → 转一整圈后，90°-Y 的平均值，反映传感器安装后的整体偏角")
    lines.append(f"  2. 在方位 0° 处: β = {plane.beta_at_zero:.4f}°, X = {plane.x_at_zero:.3f}°")
    lines.append("     → 您定义的零位方向上，与水平面夹角 β = 90°-Y")
    lines.append(f"  3. 被测面相对倾角 θ: {plane.total_tilt:.4f}°")
    lines.append("     → 转台旋转时 β 的变化幅度，即被测面相对水平面的额外倾斜")
    lines.append(f"  4. 上坡方向 α: {plane.dip_azimuth:.1f}°（从方位 0° 逆时针转 α，为较高一侧）")
    lines.append("")
    lines.append("【如何看图】")
    lines.append("  · tilt_compass.png  俯视图：0° 方向 + 红色箭头 = 向哪边倾斜")
    lines.append("  · plane_3d.png      相对倾斜（已放大）：只看 θ 造成的斜面形状")
    lines.append("  · beta_vs_azimuth.png  各方位 β 变化曲线")
    lines.append("")

    lines.append("【拟合详情】")
    lines.append(f"  tan(β) 基准 t0: {plane.t0:.6f}")
    lines.append(f"  平面坡度 p:     {plane.p:.6f}")
    lines.append(f"  平面坡度 q:     {plane.q:.6f}")
    lines.append(f"  拟合 R2:        {plane.r_squared:.6f}")
    lines.append(f"  残差标准差:     {plane.residual_std:.6f}° (β 拟合残差)")
    lines.append(f"  各方位 β 范围:  {min(betas):.4f}° ~ {max(betas):.4f}°")
    lines.append("")

    lines.append("【各方位明细】")
    lines.append(
        f"{'方位(°)':>8} {'Y均值(°)':>10} {'β=90-Y(°)':>12} "
        f"{'β拟合(°)':>10} {'残差(°)':>9} {'X均值(°)':>9}"
    )
    lines.append("-" * 64)
    for d in sorted(data, key=lambda x: x.azimuth):
        beta = d.ground_angle
        beta_fit = plane.ground_angle_at_azimuth(d.azimuth)
        resid = beta - beta_fit
        lines.append(
            f"{d.azimuth:8.1f} {d.y_mean:10.3f} {beta:12.4f} "
            f"{beta_fit:10.4f} {resid:9.4f} {d.x_mean:9.3f}"
        )

    return "\n".join(lines)


def setup_chinese_plot() -> bool:
    """配置 matplotlib 中文字体（Windows 常用微软雅黑/黑体）。"""
    try:
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "SimSun", "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        return True
    except ImportError:
        return False


def save_2d_plot(data: list[AzimuthMean], plane: PlaneFit, output_path: Path) -> bool:
    if not setup_chinese_plot():
        return False
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    az_list = [d.azimuth for d in sorted(data, key=lambda x: x.azimuth)]
    beta_meas = [d.ground_angle for d in sorted(data, key=lambda x: x.azimuth)]
    beta_fit = [plane.ground_angle_at_azimuth(az) for az in az_list]

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.scatter(az_list, beta_meas, color="tab:blue", s=60, zorder=3, label="实测 β（90°-Y）")
    ax.plot(az_list, beta_fit, color="tab:orange", linewidth=1.5, marker="o", markersize=4,
            label="平面拟合")
    ax.set_xlabel("方位角（°）")
    ax.set_ylabel("与水平面夹角 β（°）")
    ax.set_title(f"β 随方位角变化  |  相对倾角 θ = {plane.total_tilt:.4f}°")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def save_compass_plot(data: list[AzimuthMean], plane: PlaneFit, output_path: Path) -> bool:
    """俯视图：以方位 0° 为参考，显示上坡方向。"""
    if not setup_chinese_plot():
        return False
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return False

    fig, ax = plt.subplots(figsize=(8, 8))

    circle = plt.Circle((0, 0), 1.0, fill=False, color="gray", linewidth=1.5, linestyle="--")
    ax.add_patch(circle)

    # 方位 0° / 90° / 180° / 270° 标注
    labels = [(0, "0°\n(方位零位)"), (90, "90°"), (180, "180°"), (-90, "270°")]
    for deg, text in labels:
        rad = math.radians(deg)
        ax.annotate(
            text,
            xy=(1.15 * math.cos(rad), 1.15 * math.sin(rad)),
            ha="center", va="center", fontsize=11, fontweight="bold" if deg == 0 else "normal",
        )
        ax.plot([0, math.cos(rad)], [0, math.sin(rad)], color="lightgray", linewidth=0.8)

    # 0° 方向粗箭头（X 轴零位）
    ax.annotate(
        "", xy=(1.0, 0), xytext=(0, 0),
        arrowprops=dict(arrowstyle="->", color="black", lw=2.5),
    )
    ax.text(0.55, -0.12, "X 轴 / 方位 0°", fontsize=11, ha="center")

    # 上坡方向（相对倾角 θ）
    ux, uy = plane.upslope_unit_vector()
    arrow_len = 0.85
    ax.annotate(
        "", xy=(ux * arrow_len, uy * arrow_len), xytext=(0, 0),
        arrowprops=dict(arrowstyle="->", color="red", lw=3),
    )
    ax.text(
        ux * 0.5 + 0.08, uy * 0.5 + 0.08,
        f"上坡方向 α={plane.dip_azimuth:.0f}°\n相对倾角 θ={plane.total_tilt:.4f}°",
        color="red", fontsize=11, fontweight="bold",
    )

    # 各方位实测 β 用颜色表示高低
    for d in data:
        rad = math.radians(d.azimuth)
        r = 0.75
        x, y = r * math.cos(rad), r * math.sin(rad)
        delta = d.ground_angle - plane.beta_mean
        color = plt.cm.RdYlBu_r((delta + 0.06) / 0.12)
        ax.scatter(x, y, s=80, c=[color], edgecolors="k", linewidths=0.5, zorder=5)
        ax.text(x * 1.08, y * 1.08, f"{d.azimuth:.0f}°", ha="center", va="center", fontsize=8)

    ax.set_xlim(-1.45, 1.45)
    ax.set_ylim(-1.45, 1.45)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    ax.set_xlabel("X 方向（0° 方位）")
    ax.set_ylabel("Y 方向（90° 方位）")
    ax.set_title(
        f"倾斜方向俯视图  |  安装基准 β均值={plane.beta_mean:.2f}°  "
        f"|  0°处 β={plane.beta_at_zero:.2f}°"
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def save_3d_plot(data: list[AzimuthMean], plane: PlaneFit, output_path: Path) -> bool:
    """三维图：显示相对倾斜（扣除安装基准，放大显示 θ）。"""
    if not setup_chinese_plot():
        return False
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401
        from matplotlib.lines import Line2D
    except ImportError:
        return False

    exaggerate = max(20.0, 1.0 / max(plane.total_tilt, 0.001))

    radius = 1.0
    xs_meas, ys_meas, zs_rel = [], [], []
    for d in data:
        rad = math.radians(d.azimuth)
        x = radius * math.cos(rad)
        y = radius * math.sin(rad)
        z = (d.ground_angle - plane.beta_mean) * exaggerate / 100.0
        xs_meas.append(x)
        ys_meas.append(y)
        zs_rel.append(z)

    lim = 1.0
    grid = np.linspace(-lim, lim, 30)
    gx, gy = np.meshgrid(grid, grid)
    gz = plane.p * gx + plane.q * gy
    gz = gz * exaggerate

    fig = plt.figure(figsize=(10, 8))
    ax = fig.add_subplot(111, projection="3d")

    ax.plot_surface(gx, gy, gz, alpha=0.55, color="steelblue", edgecolor="none")
    ax.plot_surface(gx, gy, np.zeros_like(gx), alpha=0.12, color="gray", edgecolor="none")

    ax.scatter(xs_meas, ys_meas, zs_rel, color="red", s=55, depthshade=True)
    for x, y, z in zip(xs_meas, ys_meas, zs_rel):
        ax.plot([x, x], [y, y], [0, z], color="red", alpha=0.35, linewidth=0.8)

    # 0° 方位标记
    ax.quiver(0, 0, 0, 0.9, 0, 0, color="black", arrow_length_ratio=0.08, linewidth=2)
    ax.text(1.0, 0, 0, " 0°", fontsize=11, fontweight="bold")

    # 上坡方向
    ux, uy = plane.upslope_unit_vector()
    ax.quiver(0, 0, 0, ux * 0.7, uy * 0.7, 0.02 * exaggerate,
              color="red", arrow_length_ratio=0.12, linewidth=2)

    ax.set_xlabel("X 轴（0° 方位，米）")
    ax.set_ylabel("Y 轴（90° 方位，米）")
    ax.set_zlabel(f"相对高度（×{exaggerate:.0f} 放大）")
    ax.set_title(
        f"相对斜面三维图（已扣除安装基准 {plane.beta_mean:.2f}°）\n"
        f"相对倾角 θ={plane.total_tilt:.4f}°  上坡方向 α={plane.dip_azimuth:.0f}°"
    )

    zmax = max(abs(float(np.max(gz))), abs(float(np.min(gz))), 0.001)
    ax.set_zlim(-zmax * 1.3, zmax * 1.3)
    ax.set_box_aspect([1, 1, 0.5])

    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="red", markersize=8,
               label="各方位相对高度"),
        Line2D([0], [0], color="steelblue", linewidth=4, label="拟合斜面"),
        Line2D([0], [0], color="gray", linewidth=4, alpha=0.4, label="水平参考"),
        Line2D([0], [0], color="black", linewidth=2, label="方位 0° 方向"),
    ]
    ax.legend(handles=legend_elements, loc="upper left", fontsize=9)

    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
    return True


def analyze(
    data: list[AzimuthMean],
    source: str,
    output_dir: Path,
    *,
    save_plots: bool = True,
    extra_header: str | None = None,
) -> tuple[PlaneFit, Path]:
    plane = fit_plane_from_ground_angles(data)
    report = build_report(data, plane, source, extra_header=extra_header)
    print(report)

    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = output_dir / f"analysis_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    report_path = run_dir / "report.txt"
    report_path.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {report_path}")

    if save_plots:
        img_dir = run_dir / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        plot2d = img_dir / "beta_vs_azimuth.png"
        plot3d = img_dir / "plane_3d.png"
        plot_compass = img_dir / "tilt_compass.png"
        if save_2d_plot(data, plane, plot2d):
            print(f"2D 图表: {plot2d}")
        if save_compass_plot(data, plane, plot_compass):
            print(f"倾斜方向俯视图: {plot_compass}")
        if save_3d_plot(data, plane, plot3d):
            print(f"3D 相对斜面图: {plot3d}")
        else:
            print("（未安装 matplotlib，跳过图表）")
        print(f"图片目录: {img_dir}")

    return plane, run_dir


def run_analysis(
    csv_path: Path,
    output_dir: Path = OUTPUT_DIR,
    *,
    save_plots: bool = True,
    extra_header: str | None = None,
) -> tuple[PlaneFit, Path]:
    """从 survey CSV 分析并写入 records/analysis_*。"""
    data = load_survey_csv(csv_path)
    return analyze(
        data,
        str(csv_path.resolve()),
        output_dir,
        save_plots=save_plots,
        extra_header=extra_header,
    )


TILT_SCAN_REPORT_NOTE = (
    "【扫描说明】本次 CSV 第一列「方位角(度)」实际为 PLC 倾斜轴目标角（Ti），"
    "非方位轴旋转；俯仰/方位在采集期间保持固定。"
    "下列「方位」相关结论请按倾斜扫描角理解。"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="斜面倾角分析（90-Y 法 + 三维平面）")
    parser.add_argument("csv_file", nargs="?", help="survey CSV 文件路径")
    parser.add_argument("--demo", action="store_true", help="使用内置示例数据")
    parser.add_argument("-o", "--output", type=Path, default=OUTPUT_DIR, help="输出目录")
    parser.add_argument("--no-plot", action="store_true", help="不生成图表")
    args = parser.parse_args()

    if args.demo:
        data = load_demo_data()
        source = "内置示例数据（12 方位角）"
    elif args.csv_file:
        path = Path(args.csv_file)
        if not path.exists():
            print(f"文件不存在: {path}", file=sys.stderr)
            sys.exit(1)
        data = load_survey_csv(path)
        source = str(path)
    else:
        parser.print_help()
        sys.exit(1)

    analyze(data, source, args.output, save_plots=not args.no_plot)


if __name__ == "__main__":
    main()
