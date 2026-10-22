"""tokenizer 对齐校验（W1-D3 通过标准）。

目的：MNN 转换后，5 条固定样例在"PC 端 transformers 直推"与"设备端 MNN 推理"
（temperature=0、相同 prompt 模板）的输出应逐 token 一致。不一致说明转换/
模板配置有偏差，后续所有效果数据无效。

用法：
  # 1) 生成 PC 端基线（需 transformers+torch）
  python models/verify_tokenizer.py baseline
  # 2) 设备就绪后对比
  python models/verify_tokenizer.py check --device <serial>
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLES = [
    "你好",
    "帮偶查哈子余额",
    "跨行转账要手续费吗",
    "张三的手机尾号卡6222那笔钱转到建设路88号",
    "10万块钱存一年利息大概多少",
]
BASELINE = HERE / "baseline_pc.json"


def gen_baseline():
    from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401
    # TODO(D3): 加载 weights/Qwen3-1.7B，temperature=0 逐条生成并保存
    raise NotImplementedError("W1-D3 实现")


def check(device: str | None):
    if not BASELINE.exists():
        sys.exit("baseline 缺失，先运行 baseline 子命令")
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    adapter_bin = "/data/local/tmp/mnn/llm_demo"  # TODO(D2)
    ok = True
    for s, expect in zip(SAMPLES, baseline):
        adb = ["adb"] + (["-s", device] if device else []) + \
              ["shell", f"{adapter_bin} --prompt {s!r}"]
        got = subprocess.run(adb, capture_output=True, text=True).stdout.strip()
        same = got == expect
        ok &= same
        print(f"[{'OK' if same else 'DIFF'}] {s}\n  pc={expect!r}\n  dev={got!r}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "baseline":
        gen_baseline()
    elif cmd == "check":
        check(sys.argv[2] if len(sys.argv) > 2 else None)
    else:
        print(__doc__)
