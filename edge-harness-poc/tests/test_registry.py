"""registry lint：结构完整性与交叉引用（设计文档 5.7）。

python -m tests.test_registry   或   python tests/test_registry.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registry"


def load():
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))
    tools = yaml.safe_load((REG / "tools.yaml").read_text(encoding="utf-8"))
    return intents, tools


def lint() -> list[str]:
    errs: list[str] = []
    intents, tools = load()
    tool_names = {t["name"] for t in tools["tools"]}
    ids = [it["id"] for it in intents["intents"]]

    if len(ids) != len(set(ids)):
        errs.append("意图 id 重复")
    n_by_route = {}
    for it in intents["intents"]:
        rid, route = it["id"], it.get("route")
        n_by_route[route] = n_by_route.get(route, 0) + 1
        if route not in ("faq", "tool", "cloud"):
            errs.append(f"{rid}: route 非法 {route}")
            continue
        if route == "faq":
            kb = REG / it.get("knowledge", "")
            if not it.get("knowledge"):
                errs.append(f"{rid}: faq 缺 knowledge")
            elif not kb.exists():
                errs.append(f"{rid}: knowledge 文件缺失 {it['knowledge']}")
        if route == "tool":
            if it.get("tool") not in tool_names:
                errs.append(f"{rid}: tool '{it.get('tool')}' 不在 tools.yaml 白名单")
            for s in it.get("slots", []):
                if s.get("required") and not s.get("ask"):
                    errs.append(f"{rid}: 必填槽位 {s['name']} 缺 ask 追问语")
        if route == "cloud" and not it.get("reason"):
            errs.append(f"{rid}: cloud 类缺 reason")
        for field in ("name", "desc", "examples"):
            if not it.get(field):
                errs.append(f"{rid}: 缺 {field}")
    # tools.yaml 每个工具都应被至少一个意图引用
    used = {it.get("tool") for it in intents["intents"] if it.get("route") == "tool"}
    for t in tool_names - used:
        errs.append(f"tools.yaml: {t} 未被任何意图引用")
    return errs


if __name__ == "__main__":
    problems = lint()
    intents, _ = load()
    stats: dict[str, int] = {}
    for it in intents["intents"]:
        stats[it["route"]] = stats.get(it["route"], 0) + 1
    print(f"意图总数 {len(intents['intents'])}，分布 {stats}")
    if problems:
        print("LINT FAIL:")
        [print(" -", p) for p in problems]
        sys.exit(1)
    print("registry lint OK")
