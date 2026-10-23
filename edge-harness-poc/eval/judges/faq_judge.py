"""faq 子集判分 v0（启发式）：信息点命中 + 意图路由正确性 + 拒答率。

python eval/judges/faq_judge.py --run reports/<run_id>
口径（v0 启发式，W2 升级为 LLM-as-judge + 人工复核 30%）：
- 命中：期望信息点行中的数字/百分比/关键词出现在回复中
- 意图正确：route 的 intent == gold_intent 且 action == faq
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
REG = ROOT / "registry"

THRESHOLDS = {"info_hit": 0.80}


def load_info_points(intent_id: str) -> dict[str, str]:
    """意图 → {信息点编号: 信息点行文本}"""
    import yaml
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))
    reg = {it["id"]: it for it in intents["intents"]}[intent_id]
    card = (REG / reg["knowledge"]).read_text(encoding="utf-8")
    points = {}
    for line in card.splitlines():
        m = re.match(r"- \[(I\d+)\]\s*(.+)$", line.strip())
        if m:
            points[m.group(1)] = m.group(2)
    return points


def key_tokens(info_line: str) -> list[str]:
    toks = re.findall(r"\d+(?:\.\d+)?%?", info_line)          # 数字/百分比
    toks += re.findall(r"[\u4e00-\u9fa5]{2,}", info_line)[:3]  # 前几个中文词组
    return [t for t in toks if len(t) >= 2]


def judge(run_dir: Path) -> dict:
    from collections import Counter
    rows = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]
    n_point_hit = n_point_total = 0
    n_intent_ok = n_refuse = 0
    misses = []
    fallback_dist = Counter()                       # O7：转云/兜底原因分布
    for r in rows:
        meta, out = r["meta"], r["output"]
        if out.get("intent") == meta["gold_intent"] and out.get("action") == "faq":
            n_intent_ok += 1
        if "转人工" in out.get("reply", ""):
            n_refuse += 1
        fallback_dist[out.get("fallback_reason") or ""] += 1
        points = load_info_points(meta["gold_intent"])
        reply = out.get("reply", "")
        for pid in meta["info_points"]:
            n_point_total += 1
            line = points.get(pid, "")
            hit = any(tok in reply for tok in key_tokens(line))
            if hit:
                n_point_hit += 1
            elif len(misses) < 20:
                misses.append({"id": r["id"], "point": pid, "line": line[:50],
                               "reply": reply[:50]})
    rate = n_point_hit / n_point_total if n_point_total else None
    return {"n": len(rows), "intent_route_ok": n_intent_ok / len(rows) if rows else None,
            "info_point_hit": rate, "refuse_rate": n_refuse / len(rows) if rows else None,
            "fallback_reason_dist": dict(fallback_dist),
            "miss_examples": misses,
            "threshold_check": {"info_hit>=0.80": (rate or 0) >= THRESHOLDS["info_hit"]}}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    a = ap.parse_args()
    run_dir = Path(a.run)
    if not run_dir.is_absolute():
        run_dir = Path(__file__).resolve().parent.parent / "reports" / run_dir
    rep = judge(run_dir)
    (run_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    print(json.dumps({k: v for k, v in rep.items() if k != "miss_examples"},
                     ensure_ascii=False, indent=2))
    for m in rep["miss_examples"][:8]:
        print("MISS", m["id"], m["point"], "|", m["line"], "| reply:", m["reply"])
