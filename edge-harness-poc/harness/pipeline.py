"""L3 编排层：脱敏 → 意图分类 → 路由状态机（重试一次 + 确定性兜底）。

优化项开关（方案-Harness优化实施计划.md）：
- tool_mode="slots"   O2：工具分支槽位填充（工具名由代码定，模型只抽参数值）
- pipeline_mode="merged"  O6：脱敏+意图合并单次生成（串行 3 轮 → 2 轮）
- mask 二级过滤        O4：harness/mask_filter.py（环境变量 MASK_FILTER=off 关闭）

无设备联调：
  python -m harness.pipeline --dry-run --input "帮偶查哈子余额"
  python -m harness.pipeline --dry-run --tool-mode slots --pipeline merged --input "10万存一年利息多少"
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

CONF_MIN = 0.5          # 低于此置信度 → 兜底转云（阈值先定标准再测；扫描曲线见 rule_judge）
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
    def __init__(self, adapter, tool_mode: str = "hermes",
                 pipeline_mode: str = "serial"):
        assert tool_mode in ("hermes", "slots"), tool_mode
        assert pipeline_mode in ("serial", "merged"), pipeline_mode
        self.adapter = adapter
        self.tool_mode = tool_mode
        self.pipeline_mode = pipeline_mode
        self.env = Environment(loader=FileSystemLoader(str(PROMPTS)),
                               undefined=StrictUndefined, trim_blocks=True)
        self.intents = yaml.safe_load((REGISTRY / "intents.yaml").read_text(encoding="utf-8"))
        self.tools_reg = yaml.safe_load((REGISTRY / "tools.yaml").read_text(encoding="utf-8"))
        self.intent_map = {it["id"]: it for it in self.intents["intents"]}
        from harness.tools_mock import ToolExecutor          # 延迟导入便于单测替换
        self.executor = ToolExecutor(self.tools_reg["tools"])
        from harness.mask_filter import apply_mask_filter    # O4 二级过滤
        self._mask_filter = apply_mask_filter

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
        ents = [e for e in (obj.get("entities") or [])
                if isinstance(e, dict) and e.get("type") and e.get("original")]
        ents, masked, _restored = self._mask_filter(ents, obj.get("text", ""))   # O4
        return RouteResult(action="masked", masked_text=masked,
                           entities=ents, trace=trace)

    # ---------- ② 意图分类 ----------
    def classify(self, text: str) -> tuple[dict, list]:
        tpl = self.env.get_template("intent.j2")
        prompt = tpl.render(intents=self.intents["intents"]) + "\n\n输入：" + text
        return self._gen_json(prompt, "intent")

    # ---------- ③ 路由状态机 ----------
    def route(self, user_text: str) -> RouteResult:
        if self.pipeline_mode == "merged":                 # O6 合并路径
            return self._route_merged(user_text)
        # Step1 脱敏（PII 不出设备）
        m = self.mask(user_text)
        if m.action == "cloud_fallback":
            m.reply = CLOUD_FALLBACK_REPLY
            return m
        # Step2 意图分类
        cls, tr = self.classify(m.masked_text)
        return self._dispatch(cls, m.masked_text, list(m.trace) + tr)

    def _route_merged(self, user_text: str) -> RouteResult:
        """O6：脱敏+意图一次生成。失败隔离：text 字段非法 → 合规兜底；
        intent 字段非法 → 退回单独分类一次，不整体失败。"""
        obj, trace = self._merged_call(user_text)
        if not obj or "text" not in obj:
            return RouteResult(action="cloud_fallback", masked_text="",
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="mask_failed", trace=trace)
        ents = [e for e in (obj.get("entities") or [])
                if isinstance(e, dict) and e.get("type") and e.get("original")]
        ents, text, _restored = self._mask_filter(ents, str(obj.get("text", "")))
        cls = obj
        if str(cls.get("intent", "")) not in self.intent_map and \
                str(cls.get("intent", "")) != "out_of_scope":
            cls, tr = self.classify(text)                  # 失败隔离：补一次单独分类
            trace += tr
        return self._dispatch(cls, text, trace)

    def _merged_call(self, user_text: str) -> tuple[dict, list]:
        prompt = self.env.get_template("merged.j2").render(
            intents=self.intents["intents"]) + user_text
        return self._gen_json(prompt, "merged")

    # ---------- 子集驱动入口（merged 模式下保证测的是生产路径） ----------
    def mask_only(self, text: str) -> RouteResult:
        """mask 子集：merged 模式走合并模板取脱敏部分，serial 走 mask.j2。"""
        if self.pipeline_mode != "merged":
            return self.mask(text)
        obj, trace = self._merged_call(text)
        if not obj or "text" not in obj:
            return RouteResult(action="cloud_fallback", masked_text="",
                               fallback_reason="mask_failed", trace=trace)
        ents = [e for e in (obj.get("entities") or [])
                if isinstance(e, dict) and e.get("type") and e.get("original")]
        ents, masked, _r = self._mask_filter(ents, str(obj.get("text", "")))
        return RouteResult(action="masked", masked_text=masked,
                           entities=ents, trace=trace)

    def classify_only(self, text: str) -> tuple[dict, list]:
        """intent 子集：merged 模式走合并模板取意图部分（intent 非法时退回单独分类）。"""
        if self.pipeline_mode != "merged":
            return self.classify(text)
        obj, trace = self._merged_call(text)
        if obj and str(obj.get("intent", "")) not in self.intent_map and \
                str(obj.get("intent", "")) != "out_of_scope":
            cls, tr = self.classify(str(obj.get("text", text)))
            return cls, trace + tr
        return obj, trace

    def _dispatch(self, cls: dict, text: str, trace: list) -> RouteResult:
        """分类结果 → 分支执行（serial / merged 共用）。"""
        if not cls:
            return RouteResult(action="cloud_fallback", masked_text=text,
                               reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="intent_json_failed", trace=trace)
        intent_id = str(cls.get("intent", ""))
        conf = float(cls.get("confidence") or 0)
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

        route = reg.get("route")
        if route == "cloud":
            # ★ 高风险动作：注册表硬编码转云，模型意见仅供参考
            return RouteResult(action="cloud",
                               reply=f"好的，{reg['name']}需要为您转接服务，请稍候。",
                               trace=trace, **base)
        if route == "faq":
            return self._route_faq(reg, text, base, trace)
        if route == "tool":
            if self.tool_mode == "slots":
                return self._route_tool_slots(reg, text, base, trace)
            return self._route_tool_hermes(reg, text, base, trace)
        return RouteResult(action="cloud_fallback", fallback_reason="unknown_route",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **base)

    # ---------- FAQ 分支（O3：JSON 输出契约，hit=false 由代码统一转人工话术） ----------
    def _route_faq(self, reg, text, base, trace):
        card = (REGISTRY / reg["knowledge"]).read_text(encoding="utf-8")
        prompt = self.env.get_template("faq.j2").render(
            knowledge_card=card, question=text)
        obj, tr = self._gen_json(prompt, "faq")
        trace += tr
        if not obj or "answer" not in obj:
            return RouteResult(action="cloud_fallback", reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="faq_json_failed", trace=trace, **base)
        hit = bool(obj.get("hit"))
        answer = str(obj.get("answer", "")).strip()
        if not hit:
            return RouteResult(action="faq", reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="faq_hit_false", trace=trace, **base)
        if not answer:
            return RouteResult(action="faq", reply=CLOUD_FALLBACK_REPLY,
                               fallback_reason="faq_empty_answer", trace=trace, **base)
        return RouteResult(action="faq", reply=answer, trace=trace, **base)

    # ---------- 工具分支（hermes 原路径，基线对照臂） ----------
    def _route_tool_hermes(self, reg, text, base, trace):
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
            return self._summarize_tool(result, text, calls, base, trace, slots)
        return RouteResult(action="cloud_fallback", tool_calls=calls,
                           fallback_reason="tool_failed_twice",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **{**base, "slots": slots})

    # ---------- 工具分支（O2：槽位填充，工具名由代码决定，模型只抽参数值） ----------
    def _route_tool_slots(self, reg, text, base, trace):
        tool_def = next((t for t in self.tools_reg["tools"]
                         if t["name"] == reg.get("tool")), None)
        props = ((tool_def or {}).get("parameters") or {}).get("properties") or {}
        slot_defs = [{**s, "desc": props.get(s["name"], {}).get("description", "")}
                     for s in reg.get("slots", [])]

        slots = dict(base["slots"])
        prompt = None
        if slot_defs:      # 无槽位工具（如 get_quota）直接执行，省一次生成
            out_example = "{" + ", ".join(f'"{s["name"]}": null' for s in slot_defs) + "}"
            prompt = self.env.get_template("tool_fill.j2").render(
                tool_name=reg["tool"],
                tool_desc=(tool_def or {}).get("description", ""),
                slots=slot_defs, out_example=out_example, text=text)
            obj, tr = self._gen_json(prompt, "tool_fill")
            trace += tr
            if not obj:
                return RouteResult(action="cloud_fallback", reply=CLOUD_FALLBACK_REPLY,
                                   fallback_reason="tool_fill_json_failed",
                                   trace=trace, **{**base, "slots": slots})
            for s in slot_defs:                 # 合并抽取值；类型不合法的丢弃
                v = obj.get(s["name"])
                if v is None:
                    continue
                if s.get("type") in ("number", "integer"):
                    try:
                        v = float(v) if s["type"] == "number" else int(float(v))
                    except (TypeError, ValueError):
                        continue
                slots[s["name"]] = v

        # 必填槽位仍缺 → 代码追问（含分类阶段就缺、抽取也没拿到的情况）
        missing = [s for s in slot_defs if s.get("required") and s["name"] not in slots]
        if missing:
            return RouteResult(action="ask_slot", trace=trace,
                               reply=missing[0]["ask"], **{**base, "slots": slots})

        allowed = {s["name"] for s in slot_defs}
        arguments = {k: v for k, v in slots.items() if k in allowed and v is not None}
        calls = []
        for attempt in range(2):  # 含一次纠错重抽
            result = self.executor.execute(reg["tool"], arguments, call_count=attempt)
            calls.append({"name": reg["tool"], "arguments": arguments, "result": result})
            if not result.get("error"):
                return self._summarize_tool(result, text, calls, base, trace, slots)
            if attempt == 0 and prompt is not None:
                obj, tr = self._gen_json(
                    prompt + f"\n工具报错：{result['error']}。请修正参数值后重新输出。",
                    "tool_fill#fix")
                trace += tr
                if obj:
                    for s in slot_defs:
                        if obj.get(s["name"]) is not None:
                            slots[s["name"]] = obj[s["name"]]
                    arguments = {k: v for k, v in slots.items()
                                 if k in allowed and v is not None}
                continue
        return RouteResult(action="cloud_fallback", tool_calls=calls,
                           fallback_reason="tool_failed_twice",
                           reply=CLOUD_FALLBACK_REPLY, trace=trace, **{**base, "slots": slots})

    def _summarize_tool(self, result, text, calls, base, trace, slots):
        answer_prompt = (f"用一两句话向用户播报以下查询结果，数字要准确，"
                         f"开头带[MOCK]标记：{json.dumps(result, ensure_ascii=False)}\n用户原话：{text}")
        reply, t2 = self.adapter.generate(answer_prompt)
        trace.append({"step": "tool#summarize", "wall_ms": (t2.t_return - t2.t_submit) * 1000})
        return RouteResult(action="tool", reply=reply.strip(),
                           tool_calls=calls, trace=trace, **{**base, "slots": slots})


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
    ap.add_argument("--tool-mode", default="hermes", choices=["hermes", "slots"],
                    help="工具分支形态（O2）：slots=槽位填充，hermes=自由 function-call")
    ap.add_argument("--pipeline", default="serial", choices=["serial", "merged"],
                    help="链路形态（O6）：merged=脱敏+意图合并单次生成")
    a = ap.parse_args()

    if a.dry_run:
        from harness.adapter_mnn import DryAdapter
        adapter = DryAdapter()
    else:
        from harness.adapter_mnn import MNNAdapter
        adapter = MNNAdapter(a.model, a.device)

    result = Harness(adapter, tool_mode=a.tool_mode,
                     pipeline_mode=a.pipeline).route(a.input)
    print(json.dumps(result.__dict__, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
