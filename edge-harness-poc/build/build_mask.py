"""脱敏测试集构建器：全合成 PII（校验位合法），800 条，固定种子可复现。

python build/build_mask.py     # → eval/datasets/mask.jsonl
分布：0 PII 12% / 1-2 PII 55% / 3+ PII 23% / 仅干扰项 10%
"""

from __future__ import annotations

import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
rng = random.Random(2026)

SURNAMES = "张王李赵刘陈杨黄周吴徐孙马朱胡郭何高林罗郑梁谢宋唐许韩冯邓曹彭"
GIVEN = ["伟", "芳", "娜", "敏", "静", "磊", "军", "洋", "勇", "艳", "杰", "涛",
         "明", "超", "秀英", "国华", "建国", "桂兰", "玉梅", "志强"]
ROADS = ["人民路", "建设路", "中山大道", "解放北路", "幸福大街", "科技路", "和平街", "朝阳路"]
DISTRICTS = ["阳光花园", "翡翠湾", "锦绣小区", "康泰家园", "紫金公馆", "东方雅苑"]

ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
ID_CHECK = "10X98765432"
AREA_CODES = ["110101", "310104", "440305", "330106", "510107", "420106"]


def gen_name() -> str:
    return rng.choice(SURNAMES) + rng.choice(GIVEN)


def gen_phone() -> str:
    return "1" + rng.choice("3456789") + "".join(rng.choice("0123456789") for _ in range(9))


def gen_idcard() -> str:
    body = (rng.choice(AREA_CODES)
            + f"{rng.randint(1940, 2005)}{rng.randint(1, 12):02d}{rng.randint(1, 28):02d}"
            + f"{rng.randint(0, 999):03d}")
    s = sum(int(c) * w for c, w in zip(body, ID_WEIGHTS))
    return body + ID_CHECK[s % 11]


def gen_card() -> str:
    body = "6222" + "".join(rng.choice("0123456789") for _ in range(11))   # 15 位，补 1 位 Luhn
    total = sum(int(c) * (2 if (len(body) - i) % 2 == 0 else 1)
                for i, c in enumerate(reversed("0" + body)))
    # 标准 Luhn：使整体校验和为 10 的倍数
    def luhn_ok(digits: str) -> bool:
        t = 0
        for i, c in enumerate(reversed(digits)):
            d = int(c) * (2 if i % 2 == 1 else 1)
            t += d - 9 if d > 9 else d
        return t % 10 == 0
    for x in "0123456789":
        if luhn_ok(body + x):
            return body + x
    return body + "0"


def gen_addr() -> str:
    return (f"{rng.choice(ROADS)}{rng.randint(1, 300)}号"
            f"{rng.choice(DISTRICTS)}{rng.randint(1, 20)}栋{rng.randint(1, 6)}单元"
            f"{rng.randint(101, 2504)}室")


def gen_order() -> str:      # 干扰项：不应被脱敏
    return "订单号" + "".join(rng.choice("0123456789") for _ in range(11))


def gen_amount() -> str:     # 干扰项
    return f"{rng.randint(1, 99999)}元"


PII_TEMPLATES = {            # type → (值生成器, 填入句子的前缀)；span 只标值本身
    "NAME": (gen_name, "客户"),
    "PHONE": (gen_phone, "手机号"),
    "ID_CARD": (gen_idcard, "身份证号"),
    "BANK_CARD": (gen_card, "卡号"),
    "ADDR": (gen_addr, "住在"),
}
SENT_HEAD = ["帮", "麻烦帮", "我要", "我想", "请问，", "老人家想"]
SENT_TAIL = ["办一下转账", "改一下预留信息", "开个户", "问问贷款的事", "打一份流水",
             "查一下定期", "把短信提醒开了", "激活一下卡"]
DISTRACT = ["", "，", "，顺便看下", "，还有，"]


def make_row(mode: str) -> dict:
    """mode: none | light(1-2) | heavy(3-5) | distract_only"""
    head = rng.choice(SENT_HEAD)
    tail = rng.choice(SENT_TAIL)
    entities: list[dict] = []

    def build_sentence(parts: list[tuple[tuple[str, str], str]]) -> str:
        s = head
        for (prefix, value), etype in parts:
            s += prefix
            start = len(s)
            s += value
            entities.append({"type": etype, "span": [start, start + len(value)],
                             "original": value})
        return s + rng.choice(DISTRACT) + tail

    if mode == "none":
        text = head + tail
    elif mode == "distract_only":
        d1, d2 = gen_order(), gen_amount()
        text = f"{head}这笔{d2}的{d1}{rng.choice(DISTRACT)}{tail}"
    else:
        n = rng.randint(1, 2) if mode == "light" else rng.randint(3, 5)
        types = rng.sample(list(PII_TEMPLATES), k=min(n, 5))
        parts = []
        for t in types:
            gen, prefix = PII_TEMPLATES[t]
            parts.append(((prefix, gen()), t))
        text = build_sentence(parts)

    return {"entities": entities, "text": text}


def main() -> None:
    plan = (["none"] * 96 + ["light"] * 440 + ["heavy"] * 184 + ["distract_only"] * 80)
    rng.shuffle(plan)
    rows = []
    for i, mode in enumerate(plan):
        row = make_row(mode)
        rows.append({"id": f"mask_{i:04d}", "subset": "mask",
                     "split": "test" if i % 5 == 0 else "dev",
                     "text": row["text"],
                     "meta": {"entities": row["entities"],
                              "mode": mode,
                              "should_keep": ["订单号", "金额"]}})
    out = ROOT / "eval" / "datasets" / "mask.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
                   encoding="utf-8")
    with_pii = sum(1 for r in rows if r["meta"]["entities"])
    print(f"mask.jsonl: {len(rows)} rows，含 PII {with_pii}，干扰项行 "
          f"{sum(1 for r in rows if r['meta']['mode']=='distract_only')}")


if __name__ == "__main__":
    main()
