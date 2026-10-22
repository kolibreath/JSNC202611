"""20 轮耐久测试：逐轮计时（TTFT / tok/s），输出衰减曲线数据（降频证据）。

用法：
  python bench/endurance.py --model qwen3-1.7b --device <serial> --rounds 20 \
      --prompt-file bench/prompts_endurance.txt --out bench/out/endurance.csv
前置：W1-D4 常驻改造完成（否则每轮含模型加载，数据无效）。
口径：TTFT 用设备侧打点（adapter Timings），扣除 adb 往返；
      tok/s = 生成 token 数 / (device_end - device_start)。
"""

from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.adapter_mnn import MNNAdapter  # noqa: E402

DEFAULT_PROMPTS = [  # 覆盖长/短 prompt 与四种能力，各轮轮换
    "帮我查一下余额",
    "跨行转账要手续费吗",
    "张三的手机尾号卡6222那笔钱转到建设路88号",
    "10万块钱存一年利息大概多少",
    "你们网点周六上不上班",
] * 4


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--device", default=None)
    ap.add_argument("--rounds", type=int, default=20)
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--out", default="bench/out/endurance.csv")
    a = ap.parse_args()

    prompts = (Path(a.prompt_file).read_text(encoding="utf-8").splitlines()
               if a.prompt_file else DEFAULT_PROMPTS)[: a.rounds]
    ad = MNNAdapter(a.model, a.device)

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["round", "prompt_len", "gen_ms", "out_chars",
                    "approx_tok_s", "wall_s", "note"])
        for i, p in enumerate(prompts, 1):
            t_start = time.time()
            text, t = ad.generate(p, max_new_tokens=128)
            gen_ms = (t.t_device_end - t.t_device_start) * 1000
            approx = len(text) / (gen_ms / 1000) if gen_ms > 0 else 0  # TODO(D4): 换精确 token 数
            w.writerow([i, len(p), round(gen_ms, 1), len(text),
                        round(approx, 2), round(time.time() - t_start, 2), ""])
            f.flush()
            print(f"round {i:02d}: gen={gen_ms:.0f}ms chars={len(text)}", flush=True)
    print(f"saved -> {out}")


if __name__ == "__main__":
    main()
