"""Čitanje sistemskih statistika na Linuxu (bez spoljnih servisa).

Koristi /proc i /sys. NVIDIA GPU se čita preko nvidia-smi ako postoji.
"""

from __future__ import annotations

import glob
import math
import os
import platform
import re
import shutil
import socket
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Deque, List, Optional

try:
    import psutil  # samo kao rezervna opcija na ne-Linux sistemima
except Exception:  # pragma: no cover
    psutil = None


@dataclass
class GpuStats:
    name: str
    pct: Optional[float] = None
    temp: Optional[float] = None
    mem_used: Optional[int] = None
    mem_total: Optional[int] = None
    fan: Optional[float] = None


@dataclass
class DiskStats:
    mount: str
    label: str
    used: int = 0
    total: int = 0
    free: int = 0


@dataclass
class Stats:
    hostname: str = ""
    kernel: str = ""
    distro: str = ""
    now: datetime = field(default_factory=datetime.now)
    uptime_s: float = 0.0

    cpu_pct: float = 0.0
    cpu_temp: Optional[float] = None
    cpu_freq_ghz: Optional[float] = None
    cpu_cores: int = 1
    load: tuple = (0.0, 0.0, 0.0)

    mem_used: int = 0
    mem_total: int = 0
    swap_used: int = 0
    swap_total: int = 0

    gpu: Optional[GpuStats] = None

    net_iface: str = "-"
    net_ip: str = "-"
    net_rx: float = 0.0
    net_tx: float = 0.0
    net_rx_total: int = 0
    net_tx_total: int = 0

    disk_used: int = 0
    disk_total: int = 0
    disk_free: int = 0
    disks: List[DiskStats] = field(default_factory=list)

    fan_rpm: Optional[float] = None
    nvme_temp: Optional[float] = None
    procs: int = 0

    cpu_history: List[float] = field(default_factory=list)
    mem_history: List[float] = field(default_factory=list)
    net_rx_history: List[float] = field(default_factory=list)
    net_tx_history: List[float] = field(default_factory=list)


def _read(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _read_int(path: str) -> Optional[int]:
    value = _read(path)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _fmt_iface_default() -> str:
    raw = _read("/proc/net/route")
    if not raw:
        return ""
    best = ""
    best_metric = 1 << 30
    for line in raw.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 8:
            continue
        iface, dest, _gw, _flags, _ref, _use, metric, _mask = parts[:8]
        if dest != "00000000":
            continue
        try:
            metric_i = int(metric)
        except ValueError:
            metric_i = 0
        if metric_i < best_metric:
            best, best_metric = iface, metric_i
    return best


def _local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.settimeout(0.1)
        sock.connect(("1.1.1.1", 80))
        return sock.getsockname()[0]
    except OSError:
        return "-"
    finally:
        sock.close()


class Sampler:
    """Drži prethodna očitanja da bi izračunao procente i brzine."""

    def __init__(self, history_len: int = 90):
        self.cpu_history: Deque[float] = deque(maxlen=history_len)
        self.mem_history: Deque[float] = deque(maxlen=history_len)
        self.net_rx_history: Deque[float] = deque(maxlen=history_len)
        self.net_tx_history: Deque[float] = deque(maxlen=history_len)
        self._prev_cpu = self._cpu_times()
        self._prev_net = self._net_bytes()
        self._prev_tick = time.monotonic()
        self._hwmon_cache = None
        self._hwmon_tick = 0.0
        self._gpu_cache: Optional[GpuStats] = None
        self._gpu_tick = 0.0
        self._net_iface = _fmt_iface_default()
        self._ip = _local_ip()
        self._ip_tick = 0.0
        self.hostname = socket.gethostname()
        self.kernel = platform.release()
        self.distro = self._distro()
        self.cores = os.cpu_count() or 1
        self._nvidia = shutil.which("nvidia-smi")

    # ------------------------------------------------------------------ util
    @staticmethod
    def _distro() -> str:
        raw = _read("/etc/os-release") or ""
        for line in raw.splitlines():
            if line.startswith("PRETTY_NAME="):
                return line.split("=", 1)[1].strip().strip('"')
        return "Linux"

    @staticmethod
    def _cpu_times():
        raw = _read("/proc/stat")
        if not raw:
            return (0, 0)
        parts = raw.splitlines()[0].split()
        try:
            values = [int(v) for v in parts[1:]]
        except ValueError:
            return (0, 0)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        return (sum(values), idle)

    def _net_bytes(self):
        raw = _read("/proc/net/dev")
        total_rx = total_tx = 0
        if not raw:
            return (0, 0)
        for line in raw.splitlines()[2:]:
            if ":" not in line:
                continue
            iface, data = line.split(":", 1)
            if iface.strip() == "lo":
                continue
            parts = data.split()
            if len(parts) < 9:
                continue
            try:
                total_rx += int(parts[0])
                total_tx += int(parts[8])
            except ValueError:
                continue
        return (total_rx, total_tx)

    # --------------------------------------------------------------- hwmon
    def _scan_hwmon(self):
        temps = []
        fans = []
        for directory in glob.glob("/sys/class/hwmon/hwmon*"):
            name = (_read(os.path.join(directory, "name")) or "").lower()
            for path in glob.glob(os.path.join(directory, "temp*_input")):
                value = _read_int(path)
                if value is None:
                    continue
                label_path = path.replace("_input", "_label")
                label = (_read(label_path) or "").lower()
                temps.append((name, label, value / 1000.0))
            for path in glob.glob(os.path.join(directory, "fan*_input")):
                value = _read_int(path)
                if value:
                    fans.append(float(value))
        return {"temps": temps, "fans": fans}

    def _sensors(self):
        now = time.monotonic()
        if self._hwmon_cache is None or now - self._hwmon_tick > 10:
            self._hwmon_cache = self._scan_hwmon()
            self._hwmon_tick = now
        return self._hwmon_cache

    def _cpu_temp(self):
        sensors = self._sensors()
        preferred_names = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")
        preferred_labels = ("package", "tctl", "tdie", "cpu")
        candidates = []
        for name, label, value in sensors["temps"]:
            if name in preferred_names or any(key in label for key in preferred_labels):
                candidates.append(value)
        if candidates:
            return max(candidates)
        # fallback: x86 paket
        for zone in glob.glob("/sys/class/thermal/thermal_zone*"):
            kind = (_read(os.path.join(zone, "type")) or "").lower()
            if "x86" in kind or "cpu" in kind:
                value = _read_int(os.path.join(zone, "temp"))
                if value:
                    return value / 1000.0
        if sensors["temps"]:
            return max(value for _n, _l, value in sensors["temps"])
        return None

    def _nvme_temp(self):
        sensors = self._sensors()
        values = [
            value
            for name, label, value in sensors["temps"]
            if name.startswith("nvme") and ("composite" in label or not label)
        ]
        return max(values) if values else None

    def _fans(self):
        sensors = self._sensors()
        return max(sensors["fans"]) if sensors["fans"] else None

    # ------------------------------------------------------------------ cpu
    def _cpu_pct(self):
        total, idle = self._cpu_times()
        prev_total, prev_idle = self._prev_cpu
        self._prev_cpu = (total, idle)
        delta_total = total - prev_total
        delta_idle = idle - prev_idle
        if delta_total <= 0:
            return 0.0
        return max(0.0, min(100.0, 100.0 * (1.0 - delta_idle / delta_total)))

    def _cpu_freq(self):
        freqs = []
        for path in glob.glob("/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq"):
            value = _read_int(path)
            if value:
                freqs.append(value / 1_000_000.0)
        if freqs:
            return sum(freqs) / len(freqs)
        raw = _read("/proc/cpuinfo") or ""
        match = re.search(r"cpu MHz\s*:\s*([0-9.]+)", raw)
        return float(match.group(1)) / 1000.0 if match else None

    # ------------------------------------------------------------------ mem
    @staticmethod
    def _meminfo():
        info = {}
        raw = _read("/proc/meminfo") or ""
        for line in raw.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            parts = value.split()
            try:
                info[key] = int(parts[0]) * 1024
            except (ValueError, IndexError):
                continue
        total = info.get("MemTotal", 0)
        available = info.get("MemAvailable", info.get("MemFree", 0))
        return max(0, total - available), total

    # ------------------------------------------------------------------ gpu
    def _gpu_nvidia(self) -> Optional[GpuStats]:
        if not self._nvidia:
            return None
        try:
            result = subprocess.run(
                [
                    self._nvidia,
                    "--query-gpu=name,utilization.gpu,temperature.gpu,"
                    "memory.used,memory.total,fan.speed",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=0.8,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6:
            return None

        def num(value):
            try:
                return float(value)
            except ValueError:
                return None

        return GpuStats(
            name=parts[0],
            pct=num(parts[1]),
            temp=num(parts[2]),
            mem_used=int(num(parts[3]) * 1024 * 1024) if num(parts[3]) is not None else None,
            mem_total=int(num(parts[4]) * 1024 * 1024) if num(parts[4]) is not None else None,
            fan=num(parts[5]),
        )

    def _gpu_amd(self) -> Optional[GpuStats]:
        for card in glob.glob("/sys/class/drm/card[0-9]"):
            busy = _read_int(os.path.join(card, "device", "gpu_busy_percent"))
            if busy is None:
                continue
            name = _read(os.path.join(card, "device", "product_name")) or "AMD GPU"
            used = _read_int(os.path.join(card, "device", "mem_info_vram_used"))
            total = _read_int(os.path.join(card, "device", "mem_info_vram_total"))
            temp = None
            for hwmon in glob.glob(os.path.join(card, "device", "hwmon", "hwmon*")):
                for path in glob.glob(os.path.join(hwmon, "temp*_input")):
                    value = _read_int(path)
                    if value:
                        temp = value / 1000.0
                        break
                if temp:
                    break
            return GpuStats(
                name=name,
                pct=float(busy),
                temp=temp,
                mem_used=used,
                mem_total=total,
            )
        return None

    def _gpu(self) -> Optional[GpuStats]:
        now = time.monotonic()
        if self._gpu_cache is None or now - self._gpu_tick > 2:
            self._gpu_cache = self._gpu_nvidia() or self._gpu_amd()
            self._gpu_tick = now
        return self._gpu_cache

    # ------------------------------------------------------------------ net
    def _net(self):
        now = time.monotonic()
        current = self._net_bytes()
        prev = self._prev_net
        self._prev_net = current
        elapsed = max(1e-3, now - self._prev_tick)
        self._prev_tick = now
        rx = max(0.0, (current[0] - prev[0]) / elapsed)
        tx = max(0.0, (current[1] - prev[1]) / elapsed)
        if now - self._ip_tick > 30:
            self._ip = _local_ip()
            self._ip_tick = now
        return rx, tx, current[0], current[1]

    # --------------------------------------------------------------- diskovi
    @staticmethod
    def _disks() -> List[DiskStats]:
        """Svi stvarni montirani diskovi (root + /mnt, /media, ...).

        Preskaču se pseudo i sistemski mountovi (snap, boot, efi, tmpfs...).
        """
        skip = (
            "/boot",
            "/snap",
            "/sys",
            "/proc",
            "/run",
            "/dev",
            "/var/lib/snapd",
            "/var/snap",
        )
        found: List[DiskStats] = []
        seen_mounts = set()
        seen_devices = set()
        try:
            with open("/proc/mounts", "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.read().splitlines()
        except OSError:
            lines = []

        for line in lines:
            parts = line.split()
            if len(parts) < 3:
                continue
            device, mount, fstype = parts[0], parts[1], parts[2]
            mount = mount.replace("\\040", " ")
            if not device.startswith("/dev/"):
                continue
            if fstype in (
                "squashfs",
                "tmpfs",
                "devtmpfs",
                "proc",
                "sysfs",
                "cgroup",
                "cgroup2",
                "overlay",
                "efivarfs",
                "autofs",
            ):
                continue
            if any(mount == prefix or mount.startswith(prefix + "/") for prefix in skip):
                continue
            if mount in seen_mounts or device in seen_devices:
                continue
            try:
                usage = shutil.disk_usage(mount)
            except OSError:
                continue
            if usage.total < 512 * 1024**2:
                continue
            seen_mounts.add(mount)
            seen_devices.add(device)
            if mount == "/":
                label = "DISK"
            else:
                label = os.path.basename(mount.rstrip("/")).upper()[:6] or "DATA"
            found.append(
                DiskStats(
                    mount=mount,
                    label=label,
                    used=usage.used,
                    total=usage.total,
                    free=usage.free,
                )
            )

        found.sort(key=lambda disk: (disk.mount != "/", disk.mount))
        return found

    # --------------------------------------------------------------- sample
    def sample(self) -> Stats:
        stats = Stats()
        stats.hostname = self.hostname
        stats.kernel = self.kernel
        stats.distro = self.distro
        stats.now = datetime.now()
        stats.cpu_pct = self._cpu_pct()
        self.cpu_history.append(stats.cpu_pct)
        stats.cpu_temp = self._cpu_temp()
        stats.cpu_freq_ghz = self._cpu_freq()
        stats.cpu_cores = self.cores
        try:
            stats.load = tuple(float(x) for x in (_read("/proc/loadavg") or "0 0 0").split()[:3])
        except ValueError:
            stats.load = (0.0, 0.0, 0.0)

        stats.mem_used, stats.mem_total = self._meminfo()
        mem_pct = (stats.mem_used / stats.mem_total * 100) if stats.mem_total else 0.0
        self.mem_history.append(mem_pct)
        raw = _read("/proc/meminfo") or ""
        swap_total = swap_free = 0
        for line in raw.splitlines():
            if line.startswith("SwapTotal:"):
                try:
                    swap_total = int(line.split()[1]) * 1024
                except (ValueError, IndexError):
                    pass
            elif line.startswith("SwapFree:"):
                try:
                    swap_free = int(line.split()[1]) * 1024
                except (ValueError, IndexError):
                    pass
        stats.swap_total = swap_total
        stats.swap_used = max(0, swap_total - swap_free)

        stats.gpu = self._gpu()

        iface = _fmt_iface_default() or self._net_iface
        self._net_iface = iface
        stats.net_iface = iface or "-"
        stats.net_ip = self._ip
        stats.net_rx, stats.net_tx, stats.net_rx_total, stats.net_tx_total = self._net()
        self.net_rx_history.append(stats.net_rx)
        self.net_tx_history.append(stats.net_tx)

        disks = self._disks()
        if not disks:
            try:
                usage = shutil.disk_usage("/")
                disks = [DiskStats(mount="/", label="DISK", used=usage.used, total=usage.total, free=usage.free)]
            except OSError:
                disks = []
        stats.disks = disks
        stats.disk_used = sum(disk.used for disk in disks)
        stats.disk_total = sum(disk.total for disk in disks)
        stats.disk_free = sum(disk.free for disk in disks)

        stats.fan_rpm = self._fans()
        stats.nvme_temp = self._nvme_temp()
        try:
            stats.procs = sum(1 for entry in os.listdir("/proc") if entry.isdigit())
            uptime = float((_read("/proc/uptime") or "0").split()[0])
        except (OSError, ValueError, IndexError):
            uptime = 0.0
        stats.uptime_s = uptime
        stats.cpu_history = list(self.cpu_history)
        stats.mem_history = list(self.mem_history)
        stats.net_rx_history = list(self.net_rx_history)
        stats.net_tx_history = list(self.net_tx_history)
        return stats


class DemoSampler:
    """Lažni podaci za razvoj izgleda bez Linuxa/displeja."""

    def __init__(self, history_len: int = 90):
        self.t = 0.0
        self.history: Deque[float] = deque(maxlen=history_len)
        self.mem_history: Deque[float] = deque(maxlen=history_len)
        self.net_rx_history: Deque[float] = deque(maxlen=history_len)
        self.net_tx_history: Deque[float] = deque(maxlen=history_len)
        # popuni istoriju da sparkline odmah izgleda „živo" u preview-u
        for index in range(history_len):
            value = 34 + 18 * math.sin(index / 4) + 6 * math.sin(index / 1.3)
            self.history.append(max(2.0, min(99.0, value)))
            self.mem_history.append(58 + 6 * math.sin(index / 6 + 1))
            self.net_rx_history.append((11 + 5 * math.sin(index / 3)) * 1024**2)
            self.net_tx_history.append((1.1 + 0.6 * math.sin(index / 2.5 + 1)) * 1024**2)
        self.hostname = "blackbox"
        self.kernel = "6.8.0-45-generic"
        self.distro = "Ubuntu 24.04.1 LTS"
        self.cores = 12

    def sample(self) -> Stats:
        self.t += 1.0
        stats = Stats()
        stats.hostname = self.hostname
        stats.kernel = self.kernel
        stats.distro = self.distro
        stats.now = datetime.now()
        stats.uptime_s = 3 * 86400 + 4 * 3600 + 12 * 60
        stats.cpu_pct = 34 + 18 * math.sin(self.t / 4) + 6 * math.sin(self.t / 1.3)
        stats.cpu_pct = max(2.0, min(99.0, stats.cpu_pct))
        self.history.append(stats.cpu_pct)
        stats.cpu_history = list(self.history)
        stats.cpu_temp = 52 + 6 * math.sin(self.t / 9)
        stats.cpu_freq_ghz = 4.4 + 0.4 * math.sin(self.t / 7)
        stats.cpu_cores = self.cores
        stats.load = (1.24, 0.98, 0.81)
        stats.mem_total = 32 * 1024**3
        stats.mem_used = int(19.6 * 1024**3)
        self.mem_history.append(stats.mem_used / stats.mem_total * 100)
        stats.mem_history = list(self.mem_history)
        stats.swap_total = 8 * 1024**3
        stats.swap_used = int(1.2 * 1024**3)
        stats.gpu = GpuStats(
            name="NVIDIA GeForce RTX 4070",
            pct=45 + 25 * math.sin(self.t / 5),
            temp=61,
            mem_used=int(6.4 * 1024**3),
            mem_total=int(12 * 1024**3),
            fan=42,
        )
        stats.net_iface = "enp5s0"
        stats.net_ip = "192.168.1.42"
        stats.net_rx = 12.4 * 1024**2
        stats.net_tx = 1.2 * 1024**2
        stats.net_rx_total = int(1.24 * 1024**4)
        stats.net_tx_total = int(340 * 1024**3)
        self.net_rx_history.append(stats.net_rx)
        self.net_tx_history.append(stats.net_tx)
        stats.net_rx_history = list(self.net_rx_history)
        stats.net_tx_history = list(self.net_tx_history)
        stats.disks = [
            DiskStats(
                mount="/",
                label="DISK",
                used=int(16.2 * 1024**3),
                total=int(214 * 1024**3),
                free=int(197.8 * 1024**3),
            ),
            DiskStats(
                mount="/mnt/podaci",
                label="PODACI",
                used=int(0.3 * 1024**3),
                total=int(110 * 1024**3),
                free=int(109.7 * 1024**3),
            ),
        ]
        stats.disk_used = sum(disk.used for disk in stats.disks)
        stats.disk_total = sum(disk.total for disk in stats.disks)
        stats.disk_free = sum(disk.free for disk in stats.disks)
        stats.fan_rpm = 1240
        stats.nvme_temp = 41
        stats.procs = 318
        return stats
