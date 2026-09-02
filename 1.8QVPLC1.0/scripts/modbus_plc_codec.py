#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Modbus HR/IR 编解码，与 Modbus_Slave.st 字序一致。"""

from __future__ import annotations

from typing import Iterable

try:
    from pymodbus.client import ModbusTcpClient
except ImportError as e:
    raise ImportError("请先安装: pip install pymodbus") from e

DEFAULT_PLC_HOST = "192.168.1.30"
MODE_POWER_OFF = 0
MODE_POWER_ON = 1
MODE_POINT = 2
MODE_VEL = 3
MODE_CHENGYIN = 4
MODE_HALT = 7
IR_REG_COUNT = 79
HR_ORBIT_START = 45
HR_CORE_LEN = HR_ORBIT_START  # HR[0..44]，不含轨道 UTC

# HR[7] 控制字（Modbus_Slave CtrlBool）
CTRL_PID_TI = 1 << 11
CTRL_PID_EL = 1 << 12
CTRL_PID_AZ = 1 << 13
CTRL_COMM_RESET = 1 << 14
CTRL_MOTION = CTRL_PID_EL | CTRL_PID_AZ | CTRL_PID_TI

# Modbus HR 区段（Modbus_Slave 段 C）
# 方位 = Axis2Remote  HR[8..18]   IR 模式[10] 位置[13..14]
# 俯仰 = Axis1Remote  HR[19..29]  IR 模式[27] 位置[30..31]
# 倾斜 = Axis3Remote  HR[30..39]  IR 模式[44] 位置[47..48]
HR_AZ_MODE, HR_AZ_POS = 8, 9
HR_EL_MODE, HR_EL_POS = 19, 20
HR_TI_MODE, HR_TI_POS = 30, 31
HR_AZ_VEL, HR_EL_VEL, HR_TI_VEL = 61, 62, 63


def ulint_to_regs(val: int) -> list[int]:
    val &= (1 << 64) - 1
    return [
        (val >> 48) & 0xFFFF,
        (val >> 32) & 0xFFFF,
        (val >> 16) & 0xFFFF,
        (val >> 0) & 0xFFFF,
    ]


def regs_to_ulint(words4: list[int]) -> int:
    if len(words4) < 4:
        return 0
    return (
        ((words4[0] & 0xFFFF) << 48)
        | ((words4[1] & 0xFFFF) << 32)
        | ((words4[2] & 0xFFFF) << 16)
        | (words4[3] & 0xFFFF)
    )


def dint_to_reg_pair(dint_val: int) -> tuple[int, int]:
    dint_val = int(dint_val)
    if dint_val < 0:
        dint_val += 1 << 32
    return (dint_val >> 16) & 0xFFFF, dint_val & 0xFFFF


def el_pos_to_dint(el_rposcmd: float) -> int:
    """文件/命令值为 PLC rPosCmd_1（与 aPosCmd_1 一致），ST 解码为 dint/1e5+90。"""
    return int(round((el_rposcmd - 90.0) * 100_000))


def az_pos_to_dint(az_plc: float) -> int:
    """PLC 方位坐标，ST: rPosCmd_2 = -dint/1e5。"""
    return int(round(-az_plc * 100_000))


def ti_pos_to_dint(ti_plc: float) -> int:
    """PLC 倾斜坐标，ST: rPosCmd_3 = -dint/1e5（与方位编码相同）。"""
    return int(round(-ti_plc * 100_000))


def pos_from_dint_az_el_ti(az_dint: int, el_dint: int, ti_dint: int) -> tuple[float, float, float]:
    return (-az_dint / 100_000.0, el_dint / 100_000.0 + 90.0, -ti_dint / 100_000.0)


def build_ctrl_word(*, az_pid: bool = True, el_pid: bool = True, ti_pid: bool = True) -> int:
    w = 0
    if ti_pid:
        w |= CTRL_PID_TI
    if el_pid:
        w |= CTRL_PID_EL
    if az_pid:
        w |= CTRL_PID_AZ
    return w


def write_hr(client: ModbusTcpClient, start: int, words: Iterable[int]) -> None:
    rr = client.write_registers(start, list(words), device_id=1)
    if rr.isError():
        raise RuntimeError(f"write_registers({start}) failed: {rr}")


def read_hr(client: ModbusTcpClient, start: int, count: int) -> list[int]:
    rr = client.read_holding_registers(start, count=count, device_id=1)
    if rr.isError():
        raise RuntimeError(f"read_holding_registers({start},{count}) failed: {rr}")
    return list(rr.registers)


def write_hr_ti_only(
    client: ModbusTcpClient,
    *,
    imode_ti: int,
    ti_deg: float,
    ti_vel_deg_s: float = 2.0,
    ti_pid: bool | None = None,
) -> None:
    """仅写倾斜轴 HR[30..32]、HR[63]；可选 RMW HR[7] 的 B11，不碰方位/俯仰寄存器。"""
    if ti_pid is not None:
        hr7 = read_hr(client, 7, 1)[0]
        if ti_pid:
            hr7 |= CTRL_PID_TI
        else:
            hr7 &= ~CTRL_PID_TI
        write_hr(client, 7, [hr7 & 0xFFFF])
    write_hr(client, HR_TI_MODE, [imode_ti & 0xFFFF])
    ti_hi, ti_lo = dint_to_reg_pair(ti_pos_to_dint(ti_deg))
    write_hr(client, HR_TI_POS, [ti_hi, ti_lo])
    write_hr(client, HR_TI_VEL, [int(round(ti_vel_deg_s * 1000)) & 0xFFFF])


def read_ir(client: ModbusTcpClient, start: int, count: int) -> list[int]:
    if start + count > IR_REG_COUNT:
        raise ValueError(
            f"IR 请求越界: start={start} count={count}, PLC 仅映射 {IR_REG_COUNT} 个"
        )
    rr = client.read_input_registers(start, count=count, device_id=1)
    if rr.isError():
        raise RuntimeError(f"read_input_registers({start},{count}) failed: {rr}")
    return list(rr.registers)


def build_hr_block(
    *,
    utc_pc_ms: int,
    utc_orbit_ms: int | None,
    el_deg: float,
    az_deg: float,
    ctrl_word: int,
    imode_el: int = MODE_CHENGYIN,
    imode_az: int = MODE_CHENGYIN,
    imode_ti: int = MODE_POWER_OFF,
    ti_deg: float = 0.0,
    az_vel_deg_s: float = 4.0,
    el_vel_deg_s: float = 4.0,
    ti_vel_deg_s: float = 2.0,
) -> list[int]:
    regs = [0] * 80
    for i, w in enumerate(ulint_to_regs(utc_pc_ms)):
        regs[i] = w
    regs[7] = ctrl_word & 0xFFFF
    # 方位 Axis2
    regs[HR_AZ_MODE] = imode_az
    az_hi, az_lo = dint_to_reg_pair(az_pos_to_dint(az_deg))
    regs[HR_AZ_POS], regs[HR_AZ_POS + 1] = az_hi, az_lo
    # 俯仰 Axis1
    regs[HR_EL_MODE] = imode_el
    el_hi, el_lo = dint_to_reg_pair(el_pos_to_dint(el_deg))
    regs[HR_EL_POS], regs[HR_EL_POS + 1] = el_hi, el_lo
    # 倾斜 Axis3
    regs[HR_TI_MODE] = imode_ti
    ti_hi, ti_lo = dint_to_reg_pair(ti_pos_to_dint(ti_deg))
    regs[HR_TI_POS], regs[HR_TI_POS + 1] = ti_hi, ti_lo
    if utc_orbit_ms is not None:
        for i, w in enumerate(ulint_to_regs(utc_orbit_ms)):
            regs[45 + i] = w
    regs[HR_AZ_VEL] = int(round(az_vel_deg_s * 1000)) & 0xFFFF
    regs[HR_EL_VEL] = int(round(el_vel_deg_s * 1000)) & 0xFFFF
    regs[HR_TI_VEL] = int(round(ti_vel_deg_s * 1000)) & 0xFFFF
    return regs


def write_hr_block(
    client: ModbusTcpClient,
    regs: list[int],
    *,
    push_orbit: bool,
) -> None:
    """写 HR[0..44]；仅 push_orbit 时写 HR[45..48]，避免把 UTC_Orbit 清成 0。"""
    write_hr(client, 0, regs[:HR_CORE_LEN])
    if push_orbit:
        write_hr(client, HR_ORBIT_START, regs[HR_ORBIT_START : HR_ORBIT_START + 4])


def clear_orbit_table(client: ModbusTcpClient, ctrl_word: int = 0) -> None:
    """双轴 iMode≠4 时 PLC 会清空 aUTC_TIME[]（见 Modbus_Slave）。"""
    regs = build_hr_block(
        utc_pc_ms=0,
        utc_orbit_ms=None,
        el_deg=0,
        az_deg=0,
        ctrl_word=ctrl_word,
        imode_el=0,
        imode_az=0,
    )
    write_hr_block(client, regs, push_orbit=False)


def write_utc_pc_only(client: ModbusTcpClient, utc_pc_ms: int) -> None:
    write_hr(client, 0, ulint_to_regs(utc_pc_ms))


def dword_from_two_words(high: int, low: int) -> int:
    v = ((high & 0xFFFF) << 16) | (low & 0xFFFF)
    if v >= 1 << 31:
        v -= 1 << 32
    return v


def ir_to_inter_pos(ir: list[int]) -> tuple[float, float, float]:
    """返回 (ir_t_ms, rInterAz, rInterEl)。IR 理论角反算 rInter*。"""
    if len(ir) < 79:
        return float("nan"), float("nan"), float("nan")
    t_us = regs_to_ulint(ir[0:4])
    ir_t_ms = t_us / 1_000_000.0
    az_dint = dword_from_two_words(ir[75], ir[76])
    el_dint = dword_from_two_words(ir[77], ir[78])
    r_inter_az = -az_dint / 100_000.0
    r_inter_el = el_dint / 100_000.0 + 90.0
    return ir_t_ms, r_inter_az, r_inter_el


def ir_theory_degs(ir: list[int]) -> tuple[float, float]:
    _, az, el = ir_to_inter_pos(ir)
    return az, el


def ir_to_feedback(ir: list[int]) -> dict:
    """解析 IR：三轴独立模式/位置/速度。"""
    if len(ir) < 79:
        raise ValueError("IR 长度不足")
    az_dint = dword_from_two_words(ir[13], ir[14])
    el_dint = dword_from_two_words(ir[30], ir[31])
    ti_dint = dword_from_two_words(ir[47], ir[48])
    az_deg, el_deg, ti_deg = pos_from_dint_az_el_ti(az_dint, el_dint, ti_dint)

    def _vel(word: int) -> float:
        if word >= 1 << 15:
            word -= 1 << 16
        return word / 1000.0

    ir_t_ms, r_az, r_el = ir_to_inter_pos(ir)
    return {
        "ir_t_ms": ir_t_ms,
        "az_mode": ir[10],
        "el_mode": ir[27],
        "ti_mode": ir[44],
        "az_deg": az_deg,
        "el_deg": el_deg,
        "ti_deg": ti_deg,
        "az_vel_deg_s": _vel(ir[17]),
        "el_vel_deg_s": _vel(ir[34]),
        "ti_vel_deg_s": _vel(ir[51]),
        "r_inter_az": r_az,
        "r_inter_el": r_el,
        "error_code": ir[5],
        "di1": ir[6],
        "di2": ir[7],
    }


def format_status(st: dict) -> str:
    return (
        f"  时间(ms)={st['ir_t_ms']:.0f}  Err={st['error_code']}\n"
        f"  模式 方位/俯仰/倾斜={st['az_mode']}/{st['el_mode']}/{st['ti_mode']}\n"
        f"  实际 Az={st['az_deg']:.4f}  El={st['el_deg']:.4f}  Ti={st['ti_deg']:.4f}\n"
        f"  插值 Az={st['r_inter_az']:.4f}  El={st['r_inter_el']:.4f}"
    )
