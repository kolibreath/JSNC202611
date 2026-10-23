"""状态机分支覆盖测试（DryAdapter 驱动，覆盖 5.7 的 6 条路径 + O2/O3/O6 新分支）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.adapter_mnn import DryAdapter, Timings  # noqa: E402
from harness.pipeline import Harness, CLOUD_FALLBACK_REPLY  # noqa: E402
from harness.tools_mock import ToolExecutor, STUBS, render_tool_args_json  # noqa: E402
import yaml                                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Override:
    """按 prompt 标记片断替换 DryAdapter 输出（其余走原桩）。"""

    def __init__(self, adapter, marker: str, response: str):
        self.adapter, self.marker, self.response = adapter, marker, response

    def generate(self, prompt: str, max_new_tokens: int = 256):
        if self.marker in prompt:
            now = time.time()
            return self.response, Timings(t_submit=now, t_return=now)
        return self.adapter.generate(prompt, max_new_tokens)


def h(**kw) -> Harness:
    return Harness(DryAdapter(), **kw)


def test_branch_tool():
    r = h().route("帮偶查哈子余额")
    assert r.action == "tool" and r.intent == "query_balance"
    assert r.tool_calls and r.tool_calls[0]["name"] == "get_balance"
    assert "[MOCK]" in r.reply                       # 桩水印强制在场


def test_branch_cloud_highrisk():
    r = h().route("我要给家里转两千块")
    assert r.action == "cloud" and r.intent == "transfer_out"
    assert not r.tool_calls                          # 高风险绝不本地执行


def test_branch_faq():
    r = h().route("跨行转账要手续费吗")
    assert r.action == "faq" and r.intent == "fee_consult"
    assert "手续费" in r.reply                        # O3：answer 来自 JSON 契约


def test_branch_ask_slot():
    r = h().route("附近有什么网点")
    assert r.action == "ask_slot" and r.reply == "请问您在哪个城市？"


def test_branch_oos_fallback():
    r = h().route("今天天气怎么样")
    assert r.action == "cloud_fallback" and r.fallback_reason


def test_mask_before_route():
    r = h().route("张三的手机尾号卡6222那笔钱转到建设路88号")
    assert "张三" not in r.masked_text and "[姓名_1]" in r.masked_text
    # 脱敏失败的安全兜底（mock 一个永远返回非 JSON 的适配器）
    hs = h()
    hs.adapter = Override(hs.adapter, "占位符", "不是JSON")
    r2 = hs.route("查余额")
    assert r2.action == "cloud_fallback" and r2.fallback_reason == "mask_failed"


# ---------- O3：FAQ 输出契约 ----------

def test_faq_hit_false_unified_reply():
    hs = h()
    hs.adapter = Override(hs.adapter, "本地客服助手",
                          '{"hit": false, "answer": "随便"}')
    r = hs.route("跨行转账要手续费吗")
    assert r.action == "faq" and r.fallback_reason == "faq_hit_false"
    assert r.reply == CLOUD_FALLBACK_REPLY           # 转人工话术由代码统一


def test_faq_json_failed_fallback():
    hs = h()
    hs.adapter = Override(hs.adapter, "本地客服助手", "不是JSON")
    r = hs.route("跨行转账要手续费吗")
    assert r.action == "cloud_fallback" and r.fallback_reason == "faq_json_failed"


# ---------- O2：槽位填充式工具调用 ----------

def test_tool_slots_mode_balance():
    r = h(tool_mode="slots").route("帮偶查哈子余额")
    assert r.action == "tool" and r.tool_calls[0]["name"] == "get_balance"
    assert "[MOCK]" in r.reply
    assert any("tool_fill" in s["step"] for s in r.trace)


def test_tool_slots_mode_calc_extracts_amount():
    r = h(tool_mode="slots").route("10万存一年利息多少")
    assert r.action == "tool" and r.tool_calls[0]["name"] == "calc_interest"
    args = r.tool_calls[0]["arguments"]
    assert args["amount"] == 100000.0 and args["term"] == "一年"


def test_tool_slots_mode_missing_required_asks():
    r = h(tool_mode="slots").route("附近有什么网点")
    assert r.action == "ask_slot" and r.reply == "请问您在哪个城市？"


def test_tool_slots_mode_injection_cannot_invent_tool():
    # 工具名由注册表决定：模型输出里塞不进白名单外的工具
    hs = h(tool_mode="slots")
    hs.adapter = Override(hs.adapter, "参数提取模块",
                          '{"amount": 100, "term": "一年", "tool": "transfer_money"}')
    r = hs.route("10万存一年利息多少")
    assert r.tool_calls[0]["name"] == "calc_interest"   # 仍是注册表工具
    assert "tool" not in r.tool_calls[0]["arguments"]   # 多余字段被丢弃


# ---------- O4：mask 二级过滤接入 ----------

def test_mask_filter_restores_false_positive_in_route():
    hs = h()
    hs.adapter = Override(
        hs.adapter, "占位符",
        '{"text":"帮我查下尾号[卡号_1]卡的余额","entities":'
        '[{"type":"BANK_CARD","original":"6688","placeholder":"[卡号_1]"}]}')
    r = hs.route("帮我查下尾号6688卡的余额")
    assert "6688" in r.masked_text and "[卡号_1]" not in r.masked_text
    assert r.entities == []                            # 误标实体被撤回
    assert r.action == "tool"                          # 链路继续正常走


# ---------- O6：merged 合并链路 ----------

def test_merged_pipeline_full_branches():
    hm = h(pipeline_mode="merged")
    r = hm.route("帮偶查哈子余额")
    assert r.action == "tool" and r.intent == "query_balance"
    r2 = hm.route("今天天气怎么样")
    assert r2.action == "cloud_fallback" and r2.fallback_reason == "oos_or_low_confidence"
    r3 = hm.route("我要给家里转两千块")
    assert r3.action == "cloud" and r3.intent == "transfer_out"


def test_merged_pipeline_masks_and_filters():
    r = h(pipeline_mode="merged").route("张三的手机尾号卡6222那笔钱转到建设路88号")
    assert "[姓名_1]" in r.masked_text and "张三" not in r.masked_text
    assert "6222" in r.masked_text                     # 短数字片段被过滤还原


def test_merged_pipeline_mask_failed():
    hs = h(pipeline_mode="merged")
    hs.adapter = Override(hs.adapter, "预处理模块", "不是JSON")
    r = hs.route("查余额")
    assert r.action == "cloud_fallback" and r.fallback_reason == "mask_failed"


def test_merged_pipeline_intent_field_invalid_falls_back_to_classify():
    # merged 输出 intent 字段非法 → 退回单独分类（失败隔离），不整体失败
    hs = h(pipeline_mode="merged")
    orig = hs.adapter.generate

    def gen(prompt, max_new_tokens=256):
        if "预处理模块" in prompt:
            now = time.time()
            return ('{"text":"帮偶查哈子余额","entities":[],"intent":"不存在的意图",'
                    '"confidence":0.9,"slots":{}}'), Timings(
                t_submit=now, t_return=now)
        return orig(prompt, max_new_tokens)

    hs.adapter.generate = gen
    r = hs.route("帮偶查哈子余额")
    assert r.action == "tool" and r.intent == "query_balance"


# ---------- 工具执行器与解析（原路径回归） ----------

def test_tool_executor_whitelist_and_limit():
    reg = yaml.safe_load((ROOT / "registry" / "tools.yaml").read_text(encoding="utf-8"))
    ex = ToolExecutor(reg["tools"])
    assert "error" in ex.execute("transfer_money", {}, 0)          # 白名单外拒绝
    assert "error" in ex.execute("get_balance", {}, call_count=2)  # 超次数
    ok = ex.execute("calc_interest", {"amount": 100000, "term": "一年"}, 0)
    assert ok["[MOCK]"] is True and "1100.00" in ok["result"]["interest"]  # 10万×1.1%


def test_render_tool_args():
    assert render_tool_args_json('x <tool_call>{"name":"get_quota","arguments":{}}</tool_call>')[0] == "get_quota"
    assert render_tool_args_json("没有调用") is None
    assert render_tool_args_json("<tool_call>{坏的 json}</tool_call>") is None


def test_stubs_all_mocked():
    for name, fn in STUBS.items():
        out = fn({})
        assert isinstance(out, dict), name


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        fn()
        print(f"PASS {name}")
    print("pipeline OK")
