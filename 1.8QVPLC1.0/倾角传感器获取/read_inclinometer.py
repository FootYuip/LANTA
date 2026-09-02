#!/usr/bin/env python3
"""
BWM427S 双轴倾角传感器角度读取脚本（485 转以太网 / TCP）

默认连接: 192.168.1.168:10123（TCP Server 透传，发送 Modbus RTU）
寄存器 0x0001~0x0002 分别为 X、Y 轴角度（BWM 系列）
角度换算: (寄存器值 - 10000) / 100  → 单位: 度
"""

from __future__ import annotations

import argparse
import socket
import struct
import sys
import time

REG_ANGLE_X = 0x0001
DEFAULT_HOST = "192.168.1.168"
DEFAULT_PORT = 10123
DEFAULT_SLAVE = 0x01


def crc16_modbus(data: bytes) -> int:
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def parse_angle(raw: int) -> float:
    return (raw - 10000) / 100.0


def parse_angle_response(response: bytes, slave: int) -> tuple[float, float]:
    if len(response) < 9:
        raise TimeoutError(f"响应过短，仅收到 {len(response)} 字节")

    if response[1] == 0x03 and len(response) >= 9:
        # Modbus RTU: 地址 + 功能码 + 字节数 + 数据 + CRC
        addr, func, byte_count = response[0], response[1], response[2]
        if addr != slave:
            raise ValueError(f"从站地址不匹配: 期望 {slave:#04x}, 收到 {addr:#04x}")
        if func & 0x80:
            raise RuntimeError(f"Modbus 异常响应，异常码: {response[2]:#04x}")
        if byte_count != 4:
            raise ValueError(f"数据长度错误: {byte_count}")
        payload = response[:-2]
        recv_crc = struct.unpack("<H", response[-2:])[0]
        if crc16_modbus(payload) != recv_crc:
            raise ValueError("CRC 校验失败")
        raw_x, raw_y = struct.unpack(">HH", response[3:7])
        return parse_angle(raw_x), parse_angle(raw_y)

    if len(response) >= 13 and response[7] == 0x03:
        # Modbus TCP: MBAP(7) + 功能码 + 字节数 + 数据
        func = response[7]
        byte_count = response[8]
        if func & 0x80:
            raise RuntimeError(f"Modbus 异常响应，异常码: {response[8]:#04x}")
        if byte_count != 4:
            raise ValueError(f"数据长度错误: {byte_count}")
        raw_x, raw_y = struct.unpack(">HH", response[9:13])
        return parse_angle(raw_x), parse_angle(raw_y)

    raise ValueError(f"无法解析响应: {response.hex()}")


def build_modbus_tcp_read(slave: int, start: int, count: int, transaction_id: int = 1) -> bytes:
    return struct.pack(">HHHBBHH", transaction_id, 0, 6, slave, 0x03, start, count)


def build_modbus_rtu_read(slave: int, start: int, count: int) -> bytes:
    frame = struct.pack(">BBHH", slave, 0x03, start, count)
    return frame + struct.pack("<H", crc16_modbus(frame))


def recv_modbus_response(sock: socket.socket, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    chunks: list[bytes] = []
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        sock.settimeout(max(remaining, 0.05))
        try:
            part = sock.recv(256)
        except TimeoutError:
            continue
        except OSError as exc:
            if getattr(exc, "errno", None) in (10060, 11):
                continue
            raise
        if not part:
            break
        chunks.append(part)
        data = b"".join(chunks)
        if len(data) >= 9 and data[1] == 0x03:
            return data[:9]
        if len(data) >= 13 and data[7] == 0x03:
            return data[:13]
    data = b"".join(chunks)
    if not data:
        raise TimeoutError("响应超时")
    raise TimeoutError(f"响应不完整，收到 {len(data)} 字节: {data.hex()}")


def drain_socket(sock: socket.socket) -> None:
    sock.settimeout(0.05)
    try:
        while sock.recv(256):
            pass
    except (TimeoutError, OSError):
        pass


class PersistentInclinometerReader:
    """长连接读取：TCP 只建立一次，反复发送 Modbus RTU 请求。"""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        slave: int = DEFAULT_SLAVE,
        timeout: float = 3.0,
        gap: float = 0.15,
    ) -> None:
        self.host = host
        self.port = port
        self.slave = slave
        self.timeout = timeout
        self.gap = gap
        self._sock: socket.socket | None = None
        self._request = build_modbus_rtu_read(slave, REG_ANGLE_X, 2)

    def connect(self) -> None:
        self.close()
        self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        drain_socket(self._sock)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

    def __enter__(self) -> PersistentInclinometerReader:
        self.connect()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def read_angles(self) -> tuple[float, float]:
        if self._sock is None:
            self.connect()
        assert self._sock is not None

        drain_socket(self._sock)
        time.sleep(self.gap)
        try:
            self._sock.sendall(self._request)
            response = recv_modbus_response(self._sock, self.timeout)
            return parse_angle_response(response, self.slave)
        except (TimeoutError, ValueError, OSError) as exc:
            self.close()
            raise exc

    def read_angles_with_retry(self, retries: int = 2) -> tuple[float, float]:
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                return self.read_angles()
            except Exception as exc:
                last_error = exc
                if attempt + 1 < retries:
                    time.sleep(0.3)
                    try:
                        self.connect()
                    except OSError:
                        pass
        assert last_error is not None
        raise last_error


def tcp_exchange(host: str, port: int, request: bytes, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(request)
        time.sleep(0.1)
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            sock.settimeout(max(remaining, 0.05))
            try:
                part = sock.recv(256)
            except TimeoutError:
                continue
            except OSError as exc:
                if exc.errno not in (10060, 11):  # WSAETIMEDOUT / EAGAIN
                    raise
                continue
            if not part:
                break
            chunks.append(part)
            data = b"".join(chunks)
            if len(data) >= 9 and data[1] == 0x03:
                break
            if len(data) >= 13 and data[7] == 0x03:
                break
        data = b"".join(chunks)
        if not data:
            raise TimeoutError("响应超时")
        return data


def run_benchmark(
    reader: PersistentInclinometerReader,
    duration: float,
    interval: float,
    retries: int,
) -> None:
    print(f"长连接测试 {duration:.0f}s，间隔 {interval}s")
    print("-" * 50)
    start = time.time()
    attempts = 0
    success = 0
    failures = 0
    samples: list[tuple[float, float, float]] = []

    while time.time() - start < duration:
        attempts += 1
        t0 = time.time()
        try:
            x_deg, y_deg = reader.read_angles_with_retry(retries=retries)
            elapsed = time.time() - t0
            success += 1
            samples.append((x_deg, y_deg, elapsed))
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] #{success:3d} OK  X={x_deg:+.3f}  Y={y_deg:+.3f}  ({elapsed:.2f}s)")
        except Exception as exc:
            failures += 1
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] FAIL #{failures:3d}  {exc}", file=sys.stderr)

        spent = time.time() - t0
        sleep_t = max(0, interval - spent)
        if time.time() - start + sleep_t < duration:
            time.sleep(sleep_t)

    total = time.time() - start
    print("-" * 50)
    print(f"测试时长: {total:.1f}s")
    print(f"总尝试: {attempts}  成功: {success}  失败: {failures}")
    if attempts:
        print(f"成功率: {success / attempts * 100:.1f}%")
    if success:
        xs = [s[0] for s in samples]
        ys = [s[1] for s in samples]
        print(f"X 范围: {min(xs):+.3f} ~ {max(xs):+.3f}")
        print(f"Y 范围: {min(ys):+.3f} ~ {max(ys):+.3f}")
        avg_t = sum(s[2] for s in samples) / len(samples)
        print(f"单次成功平均耗时: {avg_t:.2f}s")


def read_angles_tcp(
    host: str,
    port: int,
    *,
    slave: int = DEFAULT_SLAVE,
    protocol: str = "rtu",
    timeout: float = 3.0,
    retries: int = 3,
) -> tuple[float, float]:
    errors: list[str] = []

    if protocol in ("auto", "tcp"):
        request = build_modbus_tcp_read(slave, REG_ANGLE_X, 2)
        for attempt in range(retries):
            try:
                response = tcp_exchange(host, port, request, timeout)
                return parse_angle_response(response, slave)
            except Exception as exc:
                errors.append(f"Modbus TCP#{attempt + 1}: {exc}")
                if attempt + 1 < retries:
                    time.sleep(0.3)
        if protocol == "tcp":
            raise RuntimeError("; ".join(errors))

    if protocol in ("auto", "rtu"):
        request = build_modbus_rtu_read(slave, REG_ANGLE_X, 2)
        for attempt in range(retries):
            try:
                response = tcp_exchange(host, port, request, timeout)
                return parse_angle_response(response, slave)
            except Exception as exc:
                errors.append(f"Modbus RTU#{attempt + 1}: {exc}")
                if attempt + 1 < retries:
                    time.sleep(0.3)
        if protocol == "rtu":
            raise RuntimeError("; ".join(errors))

    raise RuntimeError("读取失败: " + "; ".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="读取 BWM427S 倾角传感器 X/Y 轴角度（485 转以太网 TCP）"
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"设备 IP，默认 {DEFAULT_HOST}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TCP 端口，默认 {DEFAULT_PORT}",
    )
    parser.add_argument(
        "-a", "--address",
        type=lambda x: int(x, 0),
        default=DEFAULT_SLAVE,
        help=f"Modbus 从站地址，默认 {DEFAULT_SLAVE}",
    )
    parser.add_argument(
        "--protocol",
        choices=["auto", "tcp", "rtu"],
        default="rtu",
        help="通信协议: rtu=RTU 透传（TCP Server + 关闭网络数据头时用）, tcp=Modbus TCP, auto=自动尝试",
    )
    parser.add_argument(
        "-i", "--interval",
        type=float,
        default=0.5,
        help="连续读取间隔（秒），默认 0.5",
    )
    parser.add_argument(
        "-n", "--count",
        type=int,
        default=0,
        help="读取次数，0 表示持续读取（Ctrl+C 停止）",
    )
    parser.add_argument(
        "-t", "--timeout",
        type=float,
        default=3.0,
        help="TCP 响应超时（秒），默认 3.0",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="单次读取失败时的重试次数，默认 2",
    )
    parser.add_argument(
        "--short-lived",
        action="store_true",
        help="每次读取重新建立 TCP 连接（旧模式）",
    )
    parser.add_argument(
        "--benchmark",
        type=float,
        metavar="SECONDS",
        help="长连接连续测试指定秒数并输出统计",
    )
    args = parser.parse_args()

    if args.benchmark:
        print(f"连接 {args.host}:{args.port}，从站地址 {args.address:#04x}（长连接）")
        with PersistentInclinometerReader(
            args.host,
            args.port,
            slave=args.address,
            timeout=args.timeout,
        ) as reader:
            run_benchmark(reader, args.benchmark, args.interval, args.retries)
        return

    print(f"连接 {args.host}:{args.port}，从站地址 {args.address:#04x}（长连接）")

    read_num = 0
    try:
        with PersistentInclinometerReader(
            args.host,
            args.port,
            slave=args.address,
            timeout=args.timeout,
        ) as reader:
            while True:
                read_num += 1
                try:
                    if args.short_lived:
                        x_deg, y_deg = read_angles_tcp(
                            args.host,
                            args.port,
                            slave=args.address,
                            protocol=args.protocol,
                            timeout=args.timeout,
                            retries=args.retries,
                        )
                    else:
                        x_deg, y_deg = reader.read_angles_with_retry(retries=args.retries)
                    ts = time.strftime("%H:%M:%S")
                    print(f"[{ts}] X = {x_deg:+.3f}°   Y = {y_deg:+.3f}°")
                except (TimeoutError, ValueError, RuntimeError, OSError) as exc:
                    print(f"读取失败: {exc}", file=sys.stderr)

                if args.count > 0 and read_num >= args.count:
                    break
                if args.count == 0 or read_num < args.count:
                    time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n已停止")


if __name__ == "__main__":
    main()
