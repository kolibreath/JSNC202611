"""mask 子集判分：实体级 P/R、误伤率、兜底率。

python eval/judges/mask_judge.py --run reports/<run_id>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

THRESHOLDS = {"entity_recall": 0.95, "entity_precision": 0.90}


def judge(run_dir: Path) -> dict:
    rows = [json.loads(l) for l in (run_dir / "raw.jsonl").open(encoding="utf-8")]
    tp = fp = fn = 0
    n_hurt = n_fallback = n_overmask_none = 0
    for r in rows:
        gold = {(e["type"], e["original"]) for e in r["meta"].get("entities", [])}
        out = r["output"]
        if out.get("fallback"):
            n_fallback += 1
            fn += len(gold)
            continue
        pred = {(e.get("type"), e.get("original", ""))
                for e in out.get("pred_entities", []) if e.get("original")}
        if not gold and pred:
            n_overmask_none += 1        # 本无 PII 却脱敏（无 PII 行的误伤）
        if pred - gold:
            n_hurt += 1                 # 存在金标之外的"误伤"脱敏
        tp += len(pred & gold)
        fp += len(pred - gold)
        fn += len(gold - pred)

    p = tp / (tp + fp) if tp + fp else None
    rc = tp / (tp + fn) if tp + fn else None
    f1 = (2 * p * rc / (p + rc)) if (p and rc) else 0.0
    return {"n": len(rows), "entity_tp": tp, "entity_fp": fp, "entity_fn": fn,
            "precision": p, "recall": rc, "f1": f1,
            "rows_with_false_mask": n_hurt, "no_pii_but_masked_rows": n_overmask_none,
            "fallback_rows": n_fallback,
            "threshold_check": {"recall>=0.95": (rc or 0) >= THRESHOLDS["entity_recall"],
                                "precision>=0.90": (p or 0) >= THRESHOLDS["entity_precision"]}}


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
    print(json.dumps(rep, ensure_ascii=False, indent=2))
