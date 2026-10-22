"""意图测试集构建器 v0（草案）：registry 种子 + 离线规则增广 + 手写 OOS。

python build/build_intent.py            # → eval/datasets/intent.jsonl
口径说明：v0 目标每类 ~20-28 条（LLM 增广接入后 W2 冻结 v1.0，25-40 条/类）。
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build.augment import RuleAugmenter
rng = random.Random(7)

# 每类补充种子（registry examples 之外），偏口语/老年/极简
EXTRA: dict[str, list[str]] = {
    "fee_consult": ["提钱要钱不", "转账收不收钱", "跨行要多少手续费呀"],
    "rate_consult": ["定期利息高不高", "存钱利息咋样", "现在利息多少啊老人问"],
    "exchange_rate_consult": ["美金现在啥价", "换点美元划算不", "日元值钱了吗"],
    "branch_hours": ["礼拜天开门吗", "下班的点儿是几点", "中午有人值班没"],
    "loss_report_guide": ["卡不见了咋整", "卡丢了先干啥", "钱包连卡一起丢了怎么办"],
    "password_reset_guide": ["密码记不住啦", "密码错了好多次", "想换个新密码咋弄"],
    "app_usage_guide": ["这软件咋绑定卡", "手机银行咋开通啊", "回单在哪儿找"],
    "deposit_product_intro": ["存钱都有啥存法", "大额存单是啥", "零钱存哪合适"],
    "wealth_product_intro": ["R2 是啥意思", "稳当的理财有吗", "理财会不会亏"],
    "loan_condition_consult": ["贷款要啥手续", "没房能贷款吗", "借钱要什么证明"],
    "quota_consult": ["一天能转多少出来", "额度不够咋办", "限额能调高不"],
    "statement_consult": ["流水哪儿能打", "要个盖章的账单", "明细能导出吗"],
    "sms_notice_guide": ["花钱了想收到短信", "动账提醒咋开", "短信提醒收费不"],
    "security_tips": ["老有陌生电话让我转账", "验证码给别人行不行", "咋防电信诈骗"],
    "service_channel_consult": ["咋找真人客服", "人工在不在", "投诉往哪儿提"],
    "query_balance": ["看看卡里还剩多少", "余额帮偶查哈子", "我账上还有钱吗"],
    "query_recent_transactions": ["最近花了哪些钱", "看看这周账单", "上月支出多少"],
    "query_deposit_holding": ["我有几笔定期啊", "定期到期没", "存的那些钱在啥状态"],
    "query_quota_value": ["我现在额度多少", "查下我的限额", "单笔能转好多"],
    "find_branch": ["附近营业厅在哪儿", "帮我找个网点", "这附近有你们银行吗"],
    "calc_deposit_interest": ["十万存一年能拿多少", "利息帮我算算", "存三年划算多少钱"],
    "transfer_out": ["给老婆转五百", "汇一千给儿子", "帮我付下这个款"],
    "wealth_purchase": ["买那个稳健理财", "帮我申购", "黄金能买点不"],
    "loan_apply": ["我想办房贷", "测下我能借多少", "信用贷给我办一个"],
    "card_apply": ["办张新卡", "信用卡想办一张", "开个二类户"],
    "account_open": ["我要开个户", "办张储蓄卡", "开个新账户"],
    "loss_report_execute": ["快帮我把卡冻了", "马上挂失", "立刻停了我的卡"],
    "password_change_execute": ["帮我改密码", "重置取款密码", "把登录密码换掉"],
    "complaint_feedback": ["我要投诉你们", "服务太差劲了", "给个建议你们听听"],
    "complex_consult": ["三十万咋配置好", "买理财还是存定期", "提前还房贷划算吗"],
}

# 域外种子（OOS）：闲聊/他业/吐槽/无关
OOS_SEEDS = [
    "今天天气怎么样", "讲个笑话听听", "帮我订个外卖", "附近哪家火锅好吃",
    "明天股票会涨吗", "怎么减肥效果好", "推荐一部电影", "你会唱歌吗",
    "你叫什么名字", "现在几点了", "北京到上海多远", "这道数学题怎么解",
    "帮我写个请假条", "英语四级怎么过", "世界杯谁赢了", "淘宝优惠券在哪领",
    "微信怎么发红包", "这个手机电池耐用吗", "你们行长电话多少", "你是真人吗",
    "给我念首诗", "附近加油站怎么走", "滴滴打车怎么用", "感冒了吃什么药",
    "孩子上学区房问题", "退休金怎么算", "油价又涨了吗", "高铁票退票手续费",
    "这个App太卡了", "你们界面真难用", "字太小看不清啊", "怎么老是闪退",
]


def main() -> None:
    reg = yaml.safe_load((ROOT / "registry" / "intents.yaml").read_text(encoding="utf-8"))
    aug = RuleAugmenter(42)
    rows: list[dict] = []

    for it in reg["intents"]:
        seeds = list(it["examples"]) + EXTRA.get(it["id"], [])
        pool = set(seeds)
        for s in seeds:
            pool.update(aug.variants(s))
        pool = sorted(pool)
        rng.shuffle(pool)
        n = min(len(pool), 26)                      # 每类上限（v0）
        # 80/20 分层：每类按固定比例，保证 test 每类 ≥4 条
        n_test = max(4, round(n * 0.2))
        for i, text in enumerate(pool[:n]):
            rows.append({"id": f"intent_{it['id']}_{i:02d}",
                         "subset": "intent",
                         "split": "test" if i < n_test else "dev",
                         "text": text,
                         "meta": {"gold_intent": it["id"]}})

    # OOS：种子 + 轻度增广 → ~130
    oos_pool = set(OOS_SEEDS)
    for s in OOS_SEEDS:
        oos_pool.update(aug.variants(s))
    oos_pool = sorted(oos_pool)
    rng.shuffle(oos_pool)
    for i, text in enumerate(oos_pool[:130]):
        rows.append({"id": f"intent_oos_{i:03d}", "subset": "intent",
                     "split": "test" if i < 26 else "dev", "text": text,
                     "meta": {"gold_intent": "out_of_scope"}})

    out = ROOT / "eval" / "datasets" / "intent.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    n_all = len(rows)
    n_test = sum(1 for r in rows if r["split"] == "test")
    print(f"intent.jsonl v0: {n_all} rows (test {n_test}), OOS {min(130, len(oos_pool))}")


if __name__ == "__main__":
    main()
