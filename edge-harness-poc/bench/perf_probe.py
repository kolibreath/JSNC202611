"""真机性能采集：内存 / 温度 / 电量 轮询（设计文档 4.4.3）。

用法：python bench/perf_probe.py --device <serial> --pid <推理进程pid> --interval 5 --out bench/out/perf.csv
注意：温度节点路径因机型而异，D1 探测后回填 THERMAL_ZONE。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import subprocess
import time
from pathlib import Path

# TODO(D1): 从 docs/device-setup.md 回填本机 CPU 温度节点
THERMAL_ZONE = "/sys/class/thermal/thermal_zone0/temp"


def adb(serial: str | None, *args: str) -> str:
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return r.stdout if r.returncode == 0 else f"<err {r.returncode}>"


def parse_meminfo(out: str) -> str:
    # 取 "TOTAL RSS" 行；不同 Android 版本格式有差异，D2 校准解析
    for line in out.splitlines():
        if "TOTAL RSS" in line or line.startswith("TOTAL "):
            return line.split()[-2]  # TOTAL PSS 总量列位置 D2 校准
    return "-1"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", default=None)
    ap.add_argument("--pid", required=True, help="推理进程 pid（常驻模式下固定）")
    ap.add_argument("--interval", type=float, default=5)
    ap.add_argument("--duration", type=float, default=600, help="采集时长（秒）")
    ap.add_argument("--out", default="bench/out/perf.csv")
    a = ap.parse_args()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t_s", "mem_pss_kb", "cpu_temp", "battery_pct"])
        while time.time() - t0 < a.duration:
            mem = parse_meminfo(adb(a.device, "shell", f"dumpsys meminfo {a.pid}"))
            temp = adb(a.device, "shell", f"cat {THERMAL_ZONE}").strip()
            bat = adb(a.device, "shell", "dumpsys battery | grep level").strip().split()[-1]
            w.writerow([round(time.time() - t0, 1), mem, temp, bat])
            f.flush()
            time.sleep(a.interval)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
