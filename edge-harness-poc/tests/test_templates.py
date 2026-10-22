"""模板快照与渲染测试：注册表 → prompt 的 diff 可审（设计文档 5.7）。"""

from __future__ import annotations

from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "registry"
PROMPTS = ROOT / "harness" / "prompts"


def env() -> Environment:
    return Environment(loader=FileSystemLoader(str(PROMPTS)),
                       undefined=__import__("jinja2").StrictUndefined,
                       trim_blocks=True)


def test_intent_template_renders_all_classes():
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))
    out = env().get_template("intent.j2").render(intents=intents["intents"])
    assert "意图清单" in out and "规则" in out
    for it in intents["intents"]:               # 30 类全部出现在清单里
        assert it["id"] in out, f"missing {it['id']}"
        assert it["examples"][0] in out
    assert "out_of_scope" in out


def test_intent_template_output_format_block():
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))
    out = env().get_template("intent.j2").render(intents=intents["intents"])
    assert '"intent"' in out and '"confidence"' in out and '"slots"' in out


def test_tool_template_contains_all_tools():
    import json
    tools = yaml.safe_load((REG / "tools.yaml").read_text(encoding="utf-8"))
    tj = [{"schema_json": json.dumps({"name": t["name"], "description": t["description"],
                                      "parameters": t["parameters"]}, ensure_ascii=False)}
          for t in tools["tools"]]
    out = env().get_template("tool_call.j2").render(tools=tj, text="查余额")
    for t in tools["tools"]:
        assert t["name"] in out, f"missing tool {t['name']}"
    assert "<tool_call>" in out


def test_faq_template_renders_card():
    card = (REG / "kb" / "fee_consult.md").read_text(encoding="utf-8")
    out = env().get_template("faq.j2").render(knowledge_card=card, question="手续费")
    assert "[I1]" in out and "用户问题：手续费" in out
    assert "资料没有覆盖" in out          # 拒答规则必须在场


def test_mask_template_has_rules():
    out = env().get_template("mask.j2").render()
    for kw in ("NAME", "PHONE", "ID_CARD", "BANK_CARD", "ADDR"):
        assert kw in out
    assert "订单号" in out                 # 干扰项规则必须在场


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        fn()
        print(f"PASS {name}")
    print("templates OK")
