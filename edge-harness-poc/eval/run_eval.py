"""批量评测驱动：四子集 × 三后端（dry / mnn / openai）→ 落盘原始结果。

子集口径：
- intent：直接对原文做意图分类（干净归因；生产链路含脱敏，两者差异另行分析）
- mask  ：只跑脱敏能力，比对实体
- faq   ：全链路 route，考察知识卡应答
- tool  ：全链路 route，考察工具调用行为（含追问/拒调）

用法：
  python eval/run_eval.py --backend dry --subset intent
  python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset intent
  python eval/run_eval.py --backend mnn --model qwen3-1.7b --device <serial> --subset tool
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.pipeline import Harness, extract_json          # noqa: E402

DATASETS = ROOT / "eval" / "datasets"
REPORTS = ROOT / "eval" / "reports"


def make_adapter(backend: str, model: str, device: str, endpoint: str):
    if backend == "dry":
        from harness.adapter_mnn import DryAdapter
        return DryAdapter()
    if backend == "openai":
        from harness.adapter_openai import OpenAIAdapter
        return OpenAIAdapter(endpoint)
    if backend == "mnn":
        from harness.adapter_mnn import MNNAdapter
        serial = None if device in ("mid", "default") else device
        return MNNAdapter(model, serial)
    raise ValueError(backend)


# ---------- 子集驱动 ----------

def drive_intent(h: Harness, rec: dict) -> dict:
    obj, trace = h.classify(rec["text"])
    return {"pred_intent": obj.get("intent"), "confidence": obj.get("confidence"),
            "slots": obj.get("slots"), "ok_json": bool(obj),
            "raw_keys": list(obj.keys()) if obj else []}


def drive_mask(h: Harness, rec: dict) -> dict:
    m = h.mask(rec["text"])
    return {"pred_text": m.masked_text, "action": m.action,
            "pred_entities": m.entities, "fallback": m.fallback_reason}


def drive_faq(h: Harness, rec: dict) -> dict:
    r = h.route(rec["text"])
    return {"action": r.action, "intent": r.intent, "reply": r.reply}


def drive_tool(h: Harness, rec: dict) -> dict:
    r = h.route(rec["text"])
    executed = [c for c in r.tool_calls if not (c.get("result") or {}).get("error")]
    return {"action": r.action, "intent": r.intent, "reply": r.reply,
            "tool_calls": r.tool_calls, "executed_any": bool(executed)}


DRIVERS = {"intent": drive_intent, "mask": drive_mask,
           "faq": drive_faq, "tool": drive_tool}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--subset", required=True, choices=list(DRIVERS))
    ap.add_argument("--backend", default="dry", choices=["dry", "mnn", "openai"])
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--device", default="mid")
    ap.add_argument("--endpoint", default="http://127.0.0.1:8080/v1")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--include-dev", action="store_true")
    a = ap.parse_args()

    ds = DATASETS / f"{a.subset}.jsonl"
    if not ds.exists():
        sys.exit(f"dataset missing: {ds}（先运行 build/build_*.py）")

    adapter = make_adapter(a.backend, a.model, a.device, a.endpoint)
    h = Harness(adapter)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{ts}_{a.model}_{a.subset}_{a.device}_{a.backend}"
    out_dir = REPORTS / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    n, n_err = 0, 0
    with ds.open(encoding="utf-8") as f, (out_dir / "raw.jsonl").open("w", encoding="utf-8") as out:
        for line in f:
            if a.limit and n >= a.limit:
                break
            rec = json.loads(line)
            if rec.get("split") == "dev" and not a.include_dev:
                continue
            try:
                output = DRIVERS[a.subset](h, rec)
            except Exception as e:                    # 单条异常不中断整批
                n_err += 1
                output = {"__error__": f"{type(e).__name__}: {e}"}
            out.write(json.dumps({"id": rec["id"], "text": rec["text"],
                                  "meta": rec.get("meta", {}),
                                  "output": output}, ensure_ascii=False) + "\n")
            n += 1
            if n % 50 == 0:
                print(f"... {n}", file=sys.stderr)

    meta = {"run_id": run_id, "subset": a.subset, "backend": a.backend,
            "model": a.model, "device": a.device,
            "endpoint": a.endpoint if a.backend == "openai" else None,
            "n": n, "n_error": n_err,
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "note": "dry 后端数字仅验证管线，不代表模型能力"}
    (out_dir / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
    print(f"done: {n} rows ({n_err} errors) -> {out_dir}")


if __name__ == "__main__":
    main()
