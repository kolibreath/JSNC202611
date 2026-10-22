"""状态机分支覆盖测试（DryAdapter 驱动，覆盖 5.7 的 6 条路径）。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.adapter_mnn import DryAdapter  # noqa: E402
from harness.pipeline import Harness        # noqa: E402
from harness.tools_mock import ToolExecutor, STUBS, render_tool_args_json  # noqa: E402
import yaml                                  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def h() -> Harness:
    return Harness(DryAdapter())


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
    import time as _t
    from harness.adapter_mnn import Timings as _T
    hs = h()
    hs.adapter.generate = lambda prompt, max_new_tokens=256: (
        "不是JSON", _T(t_submit=_t.time(), t_return=_t.time()))  # type: ignore
    r2 = hs.route("查余额")
    assert r2.action == "cloud_fallback" and r2.fallback_reason == "mask_failed"


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
