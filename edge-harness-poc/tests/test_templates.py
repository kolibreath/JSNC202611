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
    assert '"hit"' in out                # O3：JSON 输出契约必须在场
    assert "严禁复读" in out              # O3：防复读规则必须在场


def test_mask_template_has_rules():
    out = env().get_template("mask.j2").render()
    for kw in ("NAME", "PHONE", "ID_CARD", "BANK_CARD", "ADDR"):
        assert kw in out
    assert "订单号" in out                 # 干扰项规则必须在场
    assert "entities 为空" in out          # 空 PII 输出契约在场
    assert "A20261103-8856" in out         # O4：负例 few-shot 必须在场


def test_tool_fill_template_renders_slots():
    slots = [{"name": "amount", "desc": "本金（元）", "type": "number", "required": True},
             {"name": "term", "desc": "期限，如 一年/三年", "type": "string", "required": True}]
    out = env().get_template("tool_fill.j2").render(
        tool_name="calc_interest", tool_desc="按本金与期限试算利息",
        slots=slots, out_example='{"amount": null, "term": null}',
        text="10万存一年利息多少")
    assert "参数提取模块" in out and "amount" in out and "term" in out
    assert "10万存一年利息多少" in out and "禁止编造" in out


def test_merged_template_renders_intents_and_mask_rules():
    intents = yaml.safe_load((REG / "intents.yaml").read_text(encoding="utf-8"))
    out = env().get_template("merged.j2").render(intents=intents["intents"])
    for it in intents["intents"]:               # 30 类全部在场
        assert it["id"] in out, f"missing {it['id']}"
    for kw in ('"text"', '"entities"', '"intent"', '"confidence"'):
        assert kw in out                        # 合并输出契约完整
    assert "占位符" in out and "订单号" in out    # 脱敏规则 + 非 PII 白名单在场


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        fn()
        print(f"PASS {name}")
    print("templates OK")
