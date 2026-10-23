"""规则判分器：intent 子集（准确率/宏F1/逐类召回/OOS 拒识率/误拒率）。

用法：python eval/judges/rule_judge.py --run reports/<run_id>
输出：同目录 report.json + report.md（阈值对照见实施计划第一节）。
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

THRESHOLDS = {  # 预设判定阈值（先定标准再测）
    "macro_f1": 0.90,
    "min_class_recall": 0.85,
    "oos_reject_rate": 0.85,
}


def prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f1


def judge_intent(run_dir: Path) -> dict:
    rows = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]
    n_all = len(rows)
    gold = [r["meta"].get("gold_intent") for r in rows]
    pred = [r["output"].get("pred_intent") or "out_of_scope"
            if "__error__" not in r["output"] else "__error__" for r in rows]
    confs = [r["output"].get("confidence")
             if "__error__" not in r["output"] else None for r in rows]
    n_err = sum(1 for p in pred if p == "__error__")
    rows = [r for r, p in zip(rows, pred) if p != "__error__"]
    gold = [g for g, p in zip(gold, pred) if p != "__error__"]
    confs = [c for c, p in zip(confs, pred) if p != "__error__"]
    pred = [p for p in pred if p != "__error__"]

    classes = sorted(set(gold) | set(pred))
    stats = {c: defaultdict(int) for c in classes}
    for g, p in zip(gold, pred):
        if g == p:
            stats[g]["tp"] += 1
        else:
            stats[p]["fp"] += 1
            stats[g]["fn"] += 1

    n_correct = sum(1 for g, p in zip(gold, pred) if g == p)
    acc = n_correct / len(pred) if pred else 0.0
    # 双口径（O7）：错误行"剔除"为主口径，"计为错"用于跨轮次硬可比
    acc_err_as_wrong = n_correct / n_all if n_all else 0.0
    per_class = {c: {"precision": prf(s["tp"], s["fp"], s["fn"])[0],
                     "recall": prf(s["tp"], s["fp"], s["fn"])[1],
                     "f1": prf(s["tp"], s["fp"], s["fn"])[2],
                     "support": s["tp"] + s["fn"]} for c, s in stats.items()}
    macro_f1 = sum(v["f1"] for v in per_class.values()) / len(per_class)

    # OOS 专项：gold=out_of_scope 且 pred=out_of_scope → 正确拒识
    oos_gold = [i for i, g in enumerate(gold) if g == "out_of_scope"]
    oos_reject = sum(1 for i in oos_gold if pred[i] == "out_of_scope")
    oos_rate = oos_reject / len(oos_gold) if oos_gold else None
    # 误拒：gold 非 OOS 却被判 OOS
    in_gold = [i for i, g in enumerate(gold) if g != "out_of_scope"]
    false_reject = sum(1 for i in in_gold if pred[i] == "out_of_scope")
    fr_rate = false_reject / len(in_gold) if in_gold else None

    # 置信度阈值扫描（O7）：模拟"conf<t → 保守拒识为 out_of_scope"的工作点曲线
    sweep = []
    for t in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
        pred_t = [p if (c is not None and float(c) >= t) else "out_of_scope"
                  for p, c in zip(pred, confs)]
        acc_t = sum(1 for g, p in zip(gold, pred_t) if g == p) / len(pred_t) if pred_t else 0.0
        oos_r = (sum(1 for i in oos_gold if pred_t[i] == "out_of_scope")
                 / len(oos_gold) if oos_gold else None)
        fr = (sum(1 for i in in_gold if pred_t[i] == "out_of_scope")
              / len(in_gold) if in_gold else None)
        sweep.append({"conf_min": t, "accuracy": round(acc_t, 4),
                      "oos_reject": round(oos_r, 4) if oos_r is not None else None,
                      "false_reject": round(fr, 4) if fr is not None else None})

    worst = min((c for c, v in per_class.items() if v["support"] > 0),
                key=lambda c: per_class[c]["recall"], default=None)
    return {
        "n": len(pred), "n_error_rows": n_err,
        "accuracy": acc, "accuracy_err_as_wrong": round(acc_err_as_wrong, 4),
        "macro_f1": macro_f1,
        "per_class": per_class,
        "oos_reject_rate": oos_rate, "false_reject_rate": fr_rate,
        "worst_recall_class": worst,
        "conf_threshold_sweep": sweep,
        "threshold_check": {
            "macro_f1>=0.90": macro_f1 >= THRESHOLDS["macro_f1"],
            "oos_reject>=0.85": (oos_rate or 0) >= THRESHOLDS["oos_reject_rate"],
            "min_class_recall>=0.85": all(
                v["recall"] >= THRESHOLDS["min_class_recall"]
                for v in per_class.values() if v["support"] >= 5),
        },
    }


def to_markdown(rep: dict) -> str:
    lines = ["# Intent 评测报告", "",
             f"- n={rep['n']}（错误行 {rep['n_error_rows']}）  "
             f"accuracy={rep['accuracy']:.4f}（错误行计为错口径 {rep['accuracy_err_as_wrong']:.4f}）  "
             f"macro_F1={rep['macro_f1']:.4f}",
             f"- OOS 拒识率={rep['oos_reject_rate']}  误拒率={rep['false_reject_rate']}",
             f"- 最差召回类：{rep['worst_recall_class']}", "",
             "| intent | P | R | F1 | support |", "|---|---|---|---|---|"]
    for c, v in sorted(rep["per_class"].items(), key=lambda kv: kv[1]["recall"]):
        lines.append(f"| {c} | {v['precision']:.3f} | {v['recall']:.3f} | {v['f1']:.3f} | {v['support']} |")
    if rep.get("conf_threshold_sweep"):
        lines += ["", "## 置信度阈值扫描（conf<t → 拒识为 out_of_scope）", "",
                  "| conf_min | accuracy | OOS拒识 | 误拒 |", "|---|---|---|---|"]
        for s in rep["conf_threshold_sweep"]:
            lines.append(f"| {s['conf_min']:.2f} | {s['accuracy']:.4f} | "
                         f"{s['oos_reject']} | {s['false_reject']} |")
    lines += ["", f"阈值判定：{json.dumps(rep['threshold_check'], ensure_ascii=False)}"]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="reports/<run_id> 目录")
    a = ap.parse_args()
    run_dir = Path(a.run)
    if not run_dir.is_absolute():
        run_dir = Path(__file__).resolve().parent.parent / "reports" / run_dir
    rep = judge_intent(run_dir)
    (run_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=2),
                                         encoding="utf-8")
    (run_dir / "report.md").write_text(to_markdown(rep), encoding="utf-8")
    print(to_markdown(rep))
