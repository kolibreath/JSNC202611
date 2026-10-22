"""冷启动测试：杀进程 → 启动 → 首 token，冷/热各 10 次取分布（设计文档 4.4.3）。

用法（W1-D4 常驻改造后）：
  python bench/cold_start.py --model qwen3-1.7b --device <serial> --rounds 10
"""

from __future__ import annotations

import argparse
import csv
import statistics
import subprocess
import time
from pathlib import Path

THRESHOLD_MS = 10_000


def adb(serial: str | None, *args: str, timeout: int = 120) -> str:
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--device", default=None)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--out", default="bench/out/cold_start.csv")
    a = ap.parse_args()

    model_path = f"/data/local/tmp/mnn/models/{a.model.replace('2507', '2507')}-int4"
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    samples_cold, samples_warm = [], []

    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["mode", "attempt", "ms_to_first_output"])
        for i in range(a.rounds):
            # 冷：杀掉常驻进程再启动
            adb(a.device, "shell", "pkill -f llm_demo || true")
            time.sleep(2)
            t0 = time.time()
            # TODO(D4)：按常驻二进制的实际交互协议执行"启动+首条生成"，
            # 以第一个输出字节出现时刻为准；以下为占位实现
            adb(a.device, "shell", f"{model_path}/llm_demo --model {model_path} --prompt 你好")
            cold_ms = (time.time() - t0) * 1000
            samples_cold.append(cold_ms)
            w.writerow(["cold", i, round(cold_ms, 0)]); f.flush()
            # 热：复用已启动进程（常驻模式）直接再生成
            t0 = time.time()
            # TODO(D4)：向常驻进程写入第二条请求
            warm_ms = (time.time() - t0) * 1000
            samples_warm.append(warm_ms)
            w.writerow(["warm", i, round(warm_ms, 0)]); f.flush()

    def stat(x): return {"p50_ms": round(statistics.median(x)),
                         "max_ms": round(max(x))} if x else None
    print("cold:", stat(samples_cold), " warm:", stat(samples_warm),
          f" 阈值 {THRESHOLD_MS}ms：",
          "PASS" if stat(samples_cold) and stat(samples_cold)["max_ms"] <= THRESHOLD_MS else "CHECK")
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
