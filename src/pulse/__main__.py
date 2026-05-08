#!/usr/bin/env python3
"""
PULSE — Real-time system resource monitor with terminal visualization.
Leo built this. Go ship.
"""

import argparse
import curses
import time
import math
import sys
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime

try:
    import psutil
except ImportError:
    print("❌ psutil required: pip install psutil")
    sys.exit(1)


@dataclass
class Sample:
    ts: float
    cpu: float
    mem: float
    disk: float
    net_up: float
    net_down: float
    temp: Optional[float] = None


class RingBuffer:
    """Rolling history buffer."""
    def __init__(self, size: int):
        self.size = size
        self.buf: List[Optional[Sample]] = [None] * size
        self.head = 0
        self.count = 0

    def push(self, s: Sample):
        self.buf[self.head] = s
        self.head = (self.head + 1) % self.size
        if self.count < self.size:
            self.count += 1

    def get(self) -> List[Sample]:
        if self.count == 0:
            return []
        start = (self.head - self.count) % self.size
        if start + self.count <= self.size:
            return self.buf[start:start + self.count]
        return self.buf[start:] + self.buf[:self.head]


def bar_graph(values: List[float], width: int, height: int, low_color: int, high_color: int) -> List[str]:
    """Render a sparkline bar graph. Values 0-100."""
    if not values:
        return [" " * width]
    n = len(values)
    rows = []
    for row in range(height - 1, -1, -1):
        line = ""
        for v in values:
            slot = int((v / 100) * height)
            if slot >= height - row:
                line += "█"
            else:
                b = int((v / 100) * 5)
                if b == 0:
                    line += " "
                else:
                    line += str(b)
        rows.append(line)
    return rows


def sparkline(values: List[float], width: int) -> str:
    """Single-line Unicode sparkline."""
    if not values:
        return " " * width
    mn, mx = min(values), max(values)
    rng = mx - mn if mx - mn > 0 else 1
    result = []
    for v in values:
        pos = int(((v - mn) / rng) * (width - 1))
        result.append(pos)
    out = [" "] * width
    for pos in result:
        out[pos] = "●"
    # Connect with dots between
    line = ""
    for i in range(width):
        if out[i] == "●":
            line += "●"
        else:
            # Find neighbors
            left = i - 1
            right = i + 1
            connected = False
            while left >= 0 and out[left] == "●":
                left -= 1
            while right < width and out[right] == "●":
                right += 1
            if left >= 0 and right < width:
                line += "·"
            else:
                line += " "
    return line


def get_processes() -> List[dict]:
    """Top CPU processes."""
    proc_list = []
    for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
        try:
            pinfo = p.info
            if pinfo['cpu_percent'] is None:
                pinfo['cpu_percent'] = 0.0
            if pinfo['memory_percent'] is None:
                pinfo['memory_percent'] = 0.0
            proc_list.append(pinfo)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return sorted(proc_list, key=lambda x: x['cpu_percent'], reverse=True)[:8]


def hsv_to_rgb(h: float, s: float, v: float) -> tuple:
    """HSV to RGB tuple 0-255."""
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return int(r * 255), int(g * 255), int(b * 255)


def heat_color(pct: float) -> str:
    """Return ANSI color for percentage 0-100."""
    if pct < 30:
        return "\033[92m"   # green
    elif pct < 60:
        return "\033[93m"   # yellow
    elif pct < 80:
        return "\033[38;5;214m"  # orange
    else:
        return "\033[91m"   # red


def resource_color(pct: float) -> int:
    """Return ANSI color code for resource percentage."""
    if pct < 30:
        return 40   # green bg
    elif pct < 60:
        return 43   # yellow bg
    elif pct < 80:
        return 208  # orange
    else:
        return 196  # red


def get_temp() -> Optional[float]:
    """Get CPU temperature if available."""
    try:
        temps = psutil.sensors_temperatures()
        for name, entries in temps.items():
            for entry in entries:
                if entry.current:
                    return entry.current
    except Exception:
        pass
    return None


class PulseMonitor:
    def __init__(self, stdscr, args):
        self.stdscr = stdscr
        self.args = args
        self.history = RingBuffer(120)
        self.last_net = psutil.net_io_counters()
        self.last_net_ts = time.time()
        self.running = True
        self.pause = False
        self.view = "main"  # main | procs | net | disk

        curses.curs_set(0)
        self.stdscr.nodelay(True)
        self.stdscr.timeout(1000 if not args.flush else 100)

        # Color setup
        curses.start_color()
        curses.use_default_colors()
        for i in range(1, 8):
            curses.init_pair(i, i, -1)

        self.cpu_history: List[float] = []
        self.mem_history: List[float] = []

    def collect(self) -> Sample:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory().percent
        disk = psutil.disk_usage('/').percent

        now = time.time()
        net = psutil.net_io_counters()
        dt = now - self.last_net_ts
        up = (net.bytes_sent - self.last_net.bytes_sent) / dt / 1024 if dt > 0 else 0
        down = (net.bytes_recv - self.last_net.bytes_recv) / dt / 1024 if dt > 0 else 0
        self.last_net = net
        self.last_net_ts = now

        temp = get_temp()

        return Sample(
            ts=now, cpu=cpu, mem=mem, disk=disk,
            net_up=up, net_down=down, temp=temp
        )

    def render(self, sample: Sample):
        h, w = self.stdscr.getmaxyx()
        if h < 20 or w < 60:
            self.stdscr.addstr(0, 0, "Terminal too small (min 60x20)")
            return

        self.stdscr.clear()

        # ─── Header ───────────────────────────────────────────
        now_str = datetime.now().strftime("%a %b %d %H:%M:%S %Y")
        uptime = datetime.now() - datetime.fromtimestamp(psutil.boot_time())
        up_str = str(uptime).split(".")[0]

        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.addstr(0, 0, f"  PULSE ", curses.color_pair(3))
        self.stdscr.addstr(f"  System Monitor  ", curses.color_pair(6))
        self.stdscr.addstr(f"  {now_str}")
        self.stdscr.attroff(curses.A_BOLD)
        self.stdscr.addstr(0, w - len(up_str) - 2, f" ↑{up_str}")
        self.stdscr.clrtoeol()

        # ─── Layout ────────────────────────────────────────────
        if self.view == "main":
            self._render_main(sample, h, w)
        elif self.view == "procs":
            self._render_procs(sample, h, w)
        elif self.view == "net":
            self._render_net(sample, h, w)
        elif self.view == "disk":
            self._render_disk(sample, h, w)

        # ─── Footer ────────────────────────────────────────────
        self.stdscr.attron(curses.A_DIM)
        footer = "  [M]ain  [P]rocs  [N]et  [D]isk  [Space]pause  [Q]uit"
        self.stdscr.addstr(h - 1, 0, footer)
        self.stdscr.attroff(curses.A_DIM)

        if self.pause:
            self.stdscr.attron(curses.A_STANDOUT)
            self.stdscr.addstr(h - 1, w // 2 - 6, "  PAUSED  ")
            self.stdscr.attroff(curses.A_STANDOUT)

    def _render_main(self, sample: Sample, h: int, w: int):
        history = self.history.get()
        n = len(history)

        # ── CPU Block ──────────────────────────────────────────
        cpu_color = resource_color(sample.cpu)
        self.stdscr.attron(curses.color_pair(cpu_color) | curses.A_BOLD)
        self.stdscr.addstr(2, 0, f" CPU  {sample.cpu:5.1f}% ")
        self.stdscr.attroff(curses.color_pair(cpu_color) | curses.A_BOLD)

        if n > 0:
            cpu_vals = [s.cpu for s in history]
            spark = sparkline(cpu_vals, w - 15)
            self.stdscr.addstr(2, 15, spark)

        # Per-core bars
        cores = psutil.cpu_percent(interval=0, percpu=True)
        y = 3
        self.stdscr.addstr(y, 2, "CORES", curses.A_DIM)
        y += 1
        cols = 6
        core_w = max(4, (w - 20) // cols)
        for idx, c in enumerate(cores):
            col = idx % cols
            row = idx // cols
            bx = 2 + col * (core_w + 1)
            by = y + row * 2
            if by >= h - 3:
                break
            self.stdscr.addstr(by, bx, f"C{idx} ")
            col_c = resource_color(c)
            self.stdscr.attron(curses.color_pair(col_c))
            bar = "█" * min(int(c / 10), core_w - 3)
            self.stdscr.addstr(by, bx + 3, bar.ljust(core_w - 3))
            self.stdscr.attroff(curses.color_pair(col_c))
            self.stdscr.addstr(by, bx + core_w, f"{c:4.0f}%", curses.A_DIM)

        y += (len(cores) // cols + 1) * 2 + 1

        # ── Memory Block ───────────────────────────────────────
        mem = psutil.virtual_memory()
        mem_color = resource_color(mem.percent)
        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.addstr(y, 0, f" MEM  {mem.percent:5.1f}%  ", curses.color_pair(mem_color))
        self.stdscr.attroff(curses.A_BOLD)

        total_g = mem.total / (1024**3)
        used_g = mem.used / (1024**3)
        avail_g = mem.available / (1024**3)
        self.stdscr.addstr(f"{used_g:.1f}G / {total_g:.1f}G  ", curses.A_DIM)
        self.stdscr.addstr(f"avail {avail_g:.1f}G")

        y += 1
        # Memory bar
        bar_len = min(40, w - 20)
        filled = int((mem.percent / 100) * bar_len)
        mc = resource_color(mem.percent)
        self.stdscr.addstr(y, 2, "[" + "█" * filled + " " * (bar_len - filled) + "]")
        y += 2

        # Swap
        swap = psutil.swap_memory()
        self.stdscr.addstr(y, 2, f"Swap {swap.percent:4.1f}%  ")
        self.stdscr.addstr(f"{swap.used/1024**3:.1f}G / {swap.total/1024**3:.1f}G")
        y += 2

        # ── Network Block ──────────────────────────────────────
        self.stdscr.attron(curses.A_BOLD | curses.color_pair(4))
        self.stdscr.addstr(y, 0, f" NET  ↓{sample.net_down:6.1f} KB/s  ↑{sample.net_up:6.1f} KB/s ")
        self.stdscr.attroff(curses.A_BOLD | curses.color_pair(4))
        y += 1

        if n > 1:
            down_vals = [s.net_down for s in history if s.net_down is not None]
            up_vals = [s.net_up for s in history if s.net_up is not None]
            spark_w = max(20, w - 30)
            if down_vals:
                self.stdscr.addstr(y, 2, "↓", curses.color_pair(4))
                self.stdscr.addstr(sparkline(down_vals, spark_w))
            y += 1
            if up_vals:
                self.stdscr.addstr(y, 2, "↑", curses.color_pair(6))
                self.stdscr.addstr(sparkline(up_vals, spark_w))
            y += 1
        y += 1

        # ── Disk Block ─────────────────────────────────────────
        disk = psutil.disk_usage('/')
        self.stdscr.attron(curses.A_BOLD)
        self.stdscr.addstr(y, 0, f" DISK {disk.percent:5.1f}%  ")
        self.stdscr.attroff(curses.A_BOLD)
        self.stdscr.addstr(f"{disk.used/1024**3:.0f}G / {disk.total/1024**3:.0f}G")
        y += 1
        bar_len = min(40, w - 20)
        filled = int((disk.percent / 100) * bar_len)
        self.stdscr.addstr(y, 2, "[" + "█" * filled + " " * (bar_len - filled) + "]")
        y += 2

        # ── Temp ───────────────────────────────────────────────
        if sample.temp:
            self.stdscr.attron(curses.A_BOLD | curses.color_pair(1))
            self.stdscr.addstr(y, 0, f" TMP  {sample.temp:.1f}°C")
            self.stdscr.attroff(curses.A_BOLD | curses.color_pair(1))

    def _render_procs(self, sample: Sample, h: int, w: int):
        self.stdscr.attron(curses.A_BOLD | curses.color_pair(3))
        self.stdscr.addstr(2, 0, "  Top Processes by CPU ")
        self.stdscr.attroff(curses.A_BOLD | curses.color_pair(3))
        self.stdscr.addstr(2, w - 20, " PID    NAME   CPU%  MEM%")

        procs = get_processes()
        y = 3
        for p in procs:
            cpu_b = resource_color(p['cpu_percent'])
            self.stdscr.addstr(y, 2, f"{p['pid']:6d}")
            self.stdscr.addstr(f"  {p['name'][:w-35]:20s}")
            self.stdscr.attron(curses.color_pair(cpu_b))
            self.stdscr.addstr(f"  {p['cpu_percent']:5.1f}%")
            self.stdscr.attroff(curses.color_pair(cpu_b))
            mem_bar = int(p['memory_percent'] / 5)
            self.stdscr.addstr(f"  {'█' * mem_bar}{' ' * (20 - mem_bar)}")
            self.stdscr.addstr(f"  {p['memory_percent']:4.1f}%", curses.A_DIM)
            y += 1
            if y >= h - 3:
                break

        self.stdscr.addstr(y + 1, 2, "Press [P] to cycle views", curses.A_DIM)

    def _render_net(self, sample: Sample, h: int, w: int):
        self.stdscr.attron(curses.A_BOLD | curses.color_pair(4))
        self.stdscr.addstr(2, 0, "  Network Interfaces ")
        self.stdscr.attroff(curses.A_BOLD | curses.color_pair(4))

        stats = psutil.net_io_counters(pernic=True)
        y = 4
        for iface, data in stats.items():
            self.stdscr.addstr(y, 2, f"{iface[:15]:15s}")
            self.stdscr.addstr(f"  ↓ {data.bytes_recv/1024**2:.1f}M  ↑ {data.bytes_sent/1024**2:.1f}M")
            y += 1
            if y >= h - 3:
                break

        history = self.history.get()
        if len(history) > 5:
            self.stdscr.attron(curses.A_BOLD)
            self.stdscr.addstr(y + 1, 2, "  Throughput History (KB/s)")
            self.stdscr.attroff(curses.A_BOLD)
            y += 3
            down_vals = [s.net_down for s in history if s.net_down is not None]
            up_vals = [s.net_up for s in history if s.net_up is not None]
            spark_w = w - 15
            self.stdscr.addstr(y, 2, "↓ ", curses.color_pair(4))
            self.stdscr.addstr(sparkline(down_vals, spark_w))
            y += 1
            self.stdscr.addstr(y, 2, "↑ ", curses.color_pair(6))
            self.stdscr.addstr(sparkline(up_vals, spark_w))

    def _render_disk(self, sample: Sample, h: int, w: int):
        self.stdscr.attron(curses.A_BOLD | curses.color_pair(7))
        self.stdscr.addstr(2, 0, "  Disk Usage ")
        self.stdscr.attroff(curses.A_BOLD | curses.color_pair(7))

        partitions = psutil.disk_partitions()
        y = 4
        for part in partitions:
            try:
                usage = psutil.disk_usage(part.mountpoint)
                self.stdscr.addstr(y, 2, f"{part.device[:12]:12s}  {part.mountpoint[:20]:20s}")
                pct_c = resource_color(usage.percent)
                self.stdscr.attron(curses.color_pair(pct_c))
                self.stdscr.addstr(f"  {usage.percent:5.1f}%")
                self.stdscr.attroff(curses.color_pair(pct_c))
                self.stdscr.addstr(f"  {usage.used/1024**3:.0f}G / {usage.total/1024**3:.0f}G")
                y += 1
                bar_len = min(40, w - 40)
                filled = int((usage.percent / 100) * bar_len)
                self.stdscr.addstr(y, 4, "[" + "█" * filled + " " * (bar_len - filled) + "]")
                y += 1
            except PermissionError:
                pass
            y += 1
            if y >= h - 3:
                break

    def handle_key(self, key: int):
        import constants
        if key in (ord('q'), ord('Q')):
            self.running = False
        elif key in (ord(' '),):
            self.pause = not self.pause
        elif key in (ord('m'), ord('M')):
            self.view = "main"
        elif key in (ord('p'), ord('P')):
            self.view = "procs"
        elif key in (ord('n'), ord('N')):
            self.view = "net"
        elif key in (ord('d'), ord('D')):
            self.view = "disk"

    def loop(self):
        while self.running:
            key = self.stdscr.getch()
            if key != -1:
                self.handle_key(key)

            if not self.pause:
                sample = self.collect()
                self.history.push(sample)

            self.render(sample if not self.pause else self.history.buf[self.history.head - 1] if self.history.count > 0 else None)
            self.stdscr.refresh()

            if self.args.flush:
                time.sleep(self.args.flush)
            else:
                time.sleep(1.0)


def curses_main(stdscr, args):
    monitor = PulseMonitor(stdscr, args)
    monitor.loop()


def main():
    parser = argparse.ArgumentParser(description="PULSE — Real-time system monitor")
    parser.add_argument("-f", "--flush", type=float, metavar="SEC",
                        help="Flush rate in seconds (default: 1s)")
    parser.add_argument("-w", "--width", type=int, default=80,
                        help="Force terminal width")
    args = parser.parse_args()

    curses.wrapper(lambda s: curses_main(s, args))


if __name__ == "__main__":
    main()