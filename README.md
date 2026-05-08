# PULSE — Real-time System Monitor

> Built by Leo. Go ship.

A sleek, terminal-native system monitor with ASCII sparklines, color-coded resource bars, multi-view layout, and live per-core CPU breakdown. Runs on any Unix terminal.

![Pulse Demo](https://img.shields.io/badge/python-3.10+-blue) ![License](https://img.shields.io/badge/license-MIT-green)

---

## Quick Start

```bash
pip install psutil
python -m pulse
```

Or install as a package:

```bash
pip install -e .
pulse
```

---

## Project Logo

```
PULSE
─────
   ╭──────────────────╮
   │  ░▒▓█ MONITOR █▓▒░ │
   ╰──────────────────╯
```

---

## Features

- **Multi-view dashboard:** Main overview, Top Processes, Network stats, Disk usage — switch with one key
- **Live ASCII sparklines:** 120-point rolling history per metric
- **Per-core CPU bars:** See exactly which cores are hot
- **Color-coded alerts:** Green → Yellow → Orange → Red as load increases
- **Process table:** Top 8 CPU consumers with memory bars
- **Network throughput:** Per-interface stats + live throughput sparklines
- **Pause mode:** Freeze the display (space bar)
- **No dependencies beyond psutil:** Zero non-stdlib imports

---

## Controls

| Key | Action |
|-----|--------|
| `M` | Main view (CPU, Mem, Net, Disk, Temp) |
| `P` | Top Processes by CPU |
| `N` | Network interfaces + throughput |
| `D` | Disk partitions |
| `Space` | Pause/Resume |
| `Q` | Quit |

---

## Screenshot

```
┌─────────────────────────────────────────────────────────────┐
│  PULSE   System Monitor   Thu May 08 09:24:00 2026           │
├─────────────────────────────────────────────────────────────┤
│ CPU   47.3%  ●····●····●····●●●●●···●············            │
│ CORES  C0 ████████ 70%  C1 ████ 35%  C2 ██████████ 98%     │
│ MEM   62.1%  10.2G / 16.0G  avail 5.8G                       │
│ [████████████████████░░░░░░░░░░░░░░░░░]                      │
│ Swap  12.4%  2.4G / 20.0G                                    │
│ NET   ↓  1,234.5 KB/s   ↑   567.8 KB/s                      │
│ DISK  45.0%  420G / 938G                                     │
│ TMP   67.3°C                                          [M/P/N]│
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture

```
src/pulse/
  __main__.py   — Entry point, curses UI, data collection, views
```

- **RingBuffer:** O(1) rolling history (120 samples = 2 min at 1s)
- **4 view modes:** main | procs | net | disk — toggle with keyboard
- **psutil:** cross-platform CPU, mem, disk, net, temp sensors
- **curses:** terminal-safe rendering, color pairs, nodelay mode

Built fresh at 5AM on a Friday because that's when the best tools get made.
