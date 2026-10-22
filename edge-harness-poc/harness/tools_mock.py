"""L2 工具桩（全部虚构数据，带 [MOCK] 水印）。

与 registry/tools.yaml 的 stub 字段一一对应；
ToolExecutor 强制：白名单校验、单请求最多 2 轮工具调用。
"""

from __future__ import annotations

import json
from datetime import date, timedelta


def mock_get_balance(args: dict) -> dict:
    return {"balance": "5,234.10", "currency": "CNY", "account": args.get("account", "默认账户")}


def mock_get_recent_transactions(args: dict) -> dict:
    days = int(args.get("days", 7))
    return {"window": f"最近{days}天",
            "items": [{"date": str(date.today() - timedelta(days=i)),
                       "desc": "[MOCK]消费", "amount": "-36.00"} for i in range(3)]}


def mock_get_deposit_holding(args: dict) -> dict:
    return {"items": [{"type": "整存整取", "amount": 50000.0, "rate": "1.10%",
                       "maturity": "2027-06-20"}]}


def mock_get_quota(args: dict) -> dict:
    return {"single": 50000, "daily": 200000, "currency": "CNY"}


def mock_find_branch(args: dict) -> dict:
    city = args.get("city", "")
    return {"city": city,
            "branches": [f"[MOCK]{city}中区支行（{city}市中心路1号）",
                         f"[MOCK]{city}高新区支行（{city}高新区科技路8号）"]}


def mock_calc_interest(args: dict) -> dict:
    amount = float(args.get("amount", 0))
    term = str(args.get("term", ""))
    # 占位示例利率，与 kb/rate_consult.md 口径一致（W2 业务复核时统一替换）
    rate = {"一年": 0.011, "三年": 0.015, "半年": 0.010, "三个月": 0.008}.get(term, 0.011)
    years = {"三年": 3}.get(term, 1)
    interest = round(amount * rate * years, 2)
    return {"amount": amount, "term": term, "annual_rate": f"{rate:.2%}",
            "interest": f"{interest:.2f}"}


STUBS = {
    "get_balance": mock_get_balance,
    "get_recent_transactions": mock_get_recent_transactions,
    "get_deposit_holding": mock_get_deposit_holding,
    "get_quota": mock_get_quota,
    "find_branch": mock_find_branch,
    "calc_interest": mock_calc_interest,
}


class ToolExecutor:
    """白名单 + 次数限制的执行器。安全规则在代码层，不依赖模型自觉。"""

    MAX_CALLS_PER_REQUEST = 2

    def __init__(self, registry_tools: list[dict]):
        # 白名单来自注册表（tools.yaml），而非模型输出
        self.whitelist = {t["name"] for t in registry_tools}

    def execute(self, name: str, arguments: dict, call_count: int) -> dict:
        if name not in self.whitelist:
            # 对应测试集 C 类注入 case：拒绝并记录（记录动作由 pipeline 层负责）
            return {"error": "tool_not_in_whitelist", "rejected": name}
        if call_count >= self.MAX_CALLS_PER_REQUEST:
            return {"error": "tool_call_limit_exceeded"}
        result = STUBS[name](arguments or {})
        # 水印强制注入，演示物料不得去除
        return {"[MOCK]": True, "tool": name, "result": result}


def render_tool_args_json(raw: str) -> tuple[str, dict] | None:
    """从模型输出中解析 <tool_call>{...}</tool_call>；失败返回 None。"""
    if "<tool_call>" not in raw:
        return None
    try:
        seg = raw.split("<tool_call>", 1)[1].split("</tool_call>", 1)[0]
        obj = json.loads(seg.strip())
        return obj.get("name"), obj.get("arguments", {})
    except (IndexError, json.JSONDecodeError):
        return None
