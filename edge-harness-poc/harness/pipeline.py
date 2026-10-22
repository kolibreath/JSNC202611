"""L3 编排层：脱敏 → 意图分类 → 路由状态机（重试一次 + 确定性兜底）。

无设备联调：
  python -m harness.pipeline --dry-run --input "帮偶查哈子余额"
真机（W1-D5 之后）：
  python -m harness.pipeline --model qwen3-1.7b --device <serial> --input "查下余额"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry"
PROMPTS = ROOT / "harness" / "prompts"

CONF_MIN = 0.5          # 低于此置信度 → 兜底转云（阈值先定标准再测）
MAX_JSON_RETRY = 1      # JSON 解析失败重试上限（硬性，防端侧死循环）

CLOUD_FALLBACK_REPLY = "这个问题我需要帮您转接在线客服，请稍候。"
RETRY_PROMPT_SUFFIX = "你上次的输出不符合格式：{err}。请重新输出，只输出一个 JSON 对象。"


@dataclass
class RouteResult:
    action: str                    # faq | tool | ask_slot | cloud | cloud_fallback | masked
    intent: str = "out_of_scope"
    confidence: float = 0.0
    slots: dict = field(default_factory=dict)
    masked_text: str = ""
    reply: str = ""
    tool_calls: list = field(default_factory=list)   # [{name, arguments, result}]
    entities: list = field(default_factory=list)     # 脱敏步骤解析出的实体
    fallback_reason: str = ""       # 非空时表示走了兜底路径（审计字段）
    trace: list = field(default_factory=list)        # [{step, ms, detail}]


class Harness:
    def __init__(self, adapter):
        self.adapter = adapter
        self.env = Environment(loader=FileSystemLoader(str(PROMPTS)),
                               undefined=StrictUndefined, trim_blocks=True)
        self.intents = yaml.safe_load((REGISTRY / "intents.yaml").read_text(encoding="utf-8"))
        self.tools_reg = yaml.safe_load((REGISTRY / "tools.yaml").read_text(encoding="utf-8"))
        self.intent_map = {it["id"]: it for it in self.intents["intents"]}
        from harness.tools_mock import ToolExecutor          # 延迟导入便于单测替换
        self.executor = ToolExecutor(self.tools_reg["tools"])

    # ---------- 通用：生成 + JSON 解析 + 重试一次 ----------
    def _gen_json(self, prompt: str, step: str) -> tuple[dict, list]:
        trace, last_err = [], ""
        for attempt in range(MAX_JSON_RETRY + 1):
            raw, t = self.adapter.generate(prompt + (f"\n\n{RETRY_PROMPT_SUFFIX.format(err=last_err)}" if last_err else ""))
            trace.append({"step": f"{step}#gen{attempt}", "wall_ms": (t.t_return - t.t_submit) * 1000})
            obj = extract_json(raw)
            if obj is not None:
                return obj, trace
            last_err = "无法解析为 JSON"
        return {}, trace + [{"step": f"{step}#fail", "detail": "json_parse_failed_after_retry"}]

    # ---------- ① 脱敏 ----------
    def mask(self, text: str) -> RouteResult:
        prompt = self.env.get_template("mask.j2").render()
        obj, trace = self._gen_json(prompt + "\n\n输入：" + text, "mask")
        if not obj or "text" not in obj:
            # 脱敏失败的安全兜底：不脱敏则不放行原文，直接转云（合规优先）
            return RouteResult(action="cloud_fallback", masked_text="",
                               fallback_reason="mask_failed", trace=trace)
        ents = obj.get("entities") or []
        valid = [e for e in ents if isinstance(e, dict) and e.get("type")
                 and e.get("original")]
        return RouteResult(action="masked", masked_text=obj.get("text", ""),
                            entities=valid, trace=trace)

    # ---------- ② 意图分类 ----------
    def classify(self, text: str) -> tuple[dict, list]:
        tpl = self.env.get_template("intent.j2")
        prompt = tpl.render(intents=self.intents["intents"]) + "\n\n输入：" + text
        return self._gen_json(prompt, "intent")

    # ---------- ③ 路由状态机 ----------
    def route(self, user_text: str) -> RouteResult:
        # Step1 脱敏（PII 不出设备）
        m = self.mask(user_text)
        if m.action == "cloud_fallback":
            m.reply = CLOUD_FALLBACK_REPLY
            return m
        text = m.masked_text
        trace = list(m.trace)

        # Step2 意图分类
        cls, tr = self.classify(text)
        trace += tr
        if not cls:
            return RouteResult(action="cloud_fallback", masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="intent_json_failed", trace=trace)
        intent_id = str(cls.get("intent", ""))
        conf = float(cls.get("confidence", 0))
        if intent_id not in self.intent_map and intent_id != "out_of_scope":
            return RouteResult(action="cloud_fallback", masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason=f"intent_not_in_registry:{intent_id}", trace=trace)
        if intent_id == "out_of_scope" or conf < CONF_MIN:
            return RouteResult(action="cloud_fallback", intent=intent_id,
                               confidence=conf, masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="oos_or_low_confidence", trace=trace)

        reg = self.intent_map[intent_id]
        base = dict(intent=intent_id, confidence=conf, masked_text=text,
                    slots=cls.get("slots", {}) or {})

        # Step3 分支
        route = reg.get("route")
        if route == "cloud":
            # ★ 高风险动作：注册表硬编码转云，模型意见仅供参考
            return RouteResult(action="cloud",
                               reply=f"好的，{reg['name']}需要为您转接服务，请稍候。",
                               trace=trace, **base)
        if route == "faq":
            card = (REGISTRY / reg["knowledge"]).read_text(encoding="utf-8")
            prompt = self.env.get_template("faq.j2").render(
                knowledge_card=card, question=text)
            raw, t = self.adapter.generate(prompt)
            trace.append({"step": "faq#gen", "wall_ms": (t.t_return - t.t_submit) * 1000})
            return RouteResult(action="faq", reply=raw.strip(), trace=trace, **base)
        if route == "tool":
            return self._route_tool(reg, text, base, trace)
        return RouteResult(action="cloud_fallback", fallback_reason="unknown_route",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **base)

    def _route_tool(self, reg, text, base, trace):
        from harness.tools_mock import render_tool_args_json
        tools_json = [{"schema_json": json.dumps(
            {"name": t["name"], "description": t["description"],
             "parameters": t["parameters"]}, ensure_ascii=False)}
            for t in self.tools_reg["tools"]]
        prompt = self.env.get_template("tool_call.j2").render(tools=tools_json, text=text)

        slots = dict(base["slots"])
        # 缺槽位：先追问（代码触发，用注册表 ask 话术，不让模型自由发挥）
        missing = [s for s in reg.get("slots", []) if s.get("required") and s["name"] not in slots]
        if missing:
            return RouteResult(action="ask_slot", trace=trace,
                               reply=missing[0]["ask"], **{**base, "slots": slots})

        calls = []
        for attempt in range(2):  # 含一次参数纠错重试
            raw, t = self.adapter.generate(prompt)
            trace.append({"step": f"tool#gen{attempt}", "wall_ms": (t.t_return - t.t_submit) * 1000})
            parsed = render_tool_args_json(raw)
            if parsed is None:
                # 模型没调工具而是直接回答：视为完成（FAQ 化回答）
                return RouteResult(action="tool", reply=raw.strip(),
                                   tool_calls=calls, trace=trace, **{**base, "slots": slots})
            name, arguments = parsed
            result = self.executor.execute(name, arguments, call_count=attempt)
            calls.append({"name": name, "arguments": arguments, "result": result})
            if result.get("error"):
                prompt += f"\n工具 {name} 返回错误：{result['error']}，请修正后重试。"
                continue
            # 工具结果回填 → 生成自然语言回复
            answer_prompt = (f"用一两句话向用户播报以下查询结果，数字要准确，"
                             f"开头带[MOCK]标记：{json.dumps(result, ensure_ascii=False)}\n用户原话：{text}")
            reply, t2 = self.adapter.generate(answer_prompt)
            trace.append({"step": "tool#summarize", "wall_ms": (t2.t_return - t2.t_submit) * 1000})
            return RouteResult(action="tool", reply=reply.strip(),
                               tool_calls=calls, trace=trace, **{**base, "slots": slots})
        return RouteResult(action="cloud_fallback", tool_calls=calls,
                           fallback_reason="tool_failed_twice",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **{**base, "slots": slots})


def extract_json(raw: str) -> dict | None:
    """从模型输出提取首个 JSON 对象；grammar 约束正常时 raw 本身就是 JSON。"""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--model", default="qwen3-1.7b")
    ap.add_argument("--device", default=None)
    a = ap.parse_args()

    if a.dry_run:
        from harness.adapter_mnn import DryAdapter
        adapter = DryAdapter()
    else:
        from harness.adapter_mnn import MNNAdapter
        adapter = MNNAdapter(a.model, a.device)

    result = Harness(adapter).route(a.input)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
