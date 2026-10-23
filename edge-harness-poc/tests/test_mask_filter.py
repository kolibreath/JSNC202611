"""mask 二级过滤（O4）单测：校验位算法 + 非 PII 白名单 + 应用逻辑。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.mask_filter import (apply_mask_filter, idcard_ok,     # noqa: E402
                                 luhn_ok, should_restore)

_ID_W = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_MAP = "10X98765432"


def make_card(base15: str = "622202020012345") -> str:
    return next(base15 + d for d in "0123456789" if luhn_ok(base15 + d))


def make_id(body17: str = "11010519491231002") -> str:
    s = sum(int(body17[i]) * _ID_W[i] for i in range(17))
    return body17 + _ID_MAP[s % 11]


def wrong_id(body17: str) -> str:
    right = make_id(body17)
    return body17 + ("X" if right[-1] != "X" else "0")


def test_luhn():
    card = make_card()
    assert luhn_ok(card)
    assert not luhn_ok(card[:-1] + str((int(card[-1]) + 1) % 10))
    assert not luhn_ok("6222")                 # 过短片段不是合法卡号


def test_idcard():
    assert idcard_ok(make_id())
    assert not idcard_ok(wrong_id("11010519491231002"))
    assert not idcard_ok("11010519491231")     # 位数不足


def test_should_restore_non_pii():
    # L1 白名单：无论标成什么类型
    assert should_restore({"type": "BANK_CARD", "original": "A20261103-8856"})
    assert should_restore({"type": "BANK_CARD", "original": "5000元"})
    assert should_restore({"type": "ID_CARD", "original": "839421"})
    assert should_restore({"type": "PHONE", "original": "6688"})
    assert should_restore({"type": "BANK_CARD", "original": "2026年11月3日"})


def test_should_restore_checksum():
    # L2 校验位：真实体保留，校验不过的还原
    assert not should_restore({"type": "BANK_CARD", "original": make_card()})
    assert not should_restore({"type": "ID_CARD", "original": make_id()})
    assert should_restore({"type": "BANK_CARD",
                           "original": make_card()[:-1] +
                           str((int(make_card()[-1]) + 1) % 10)})
    assert should_restore({"type": "PHONE", "original": "12345"})   # 位数不够


def test_apply_restores_placeholder():
    card = make_card()
    ents = [
        {"type": "BANK_CARD", "original": "A20261103-8856", "placeholder": "[卡号_1]"},
        {"type": "BANK_CARD", "original": card, "placeholder": "[卡号_2]"},
    ]
    kept, text, restored = apply_mask_filter(
        ents, "订单 [卡号_1] 用卡 [卡号_2] 支付")
    assert len(kept) == 1 and kept[0]["original"] == card
    assert text == f"订单 A20261103-8856 用卡 [卡号_2] 支付"
    assert restored == ["A20261103-8856"]


def test_apply_env_off(monkeypatch=None):
    import os
    old = os.environ.get("MASK_FILTER")
    os.environ["MASK_FILTER"] = "off"
    try:
        ents = [{"type": "BANK_CARD", "original": "5000元", "placeholder": "[卡号_1]"}]
        kept, text, restored = apply_mask_filter(ents, "转了 [卡号_1]")
        assert kept == ents and text == "转了 [卡号_1]" and restored == []
    finally:
        if old is None:
            os.environ.pop("MASK_FILTER", None)
        else:
            os.environ["MASK_FILTER"] = old


if __name__ == "__main__":
    for name, fn in sorted({k: v for k, v in globals().items()
                            if k.startswith("test_")}.items()):
        fn()
        print(f"PASS {name}")
    print("mask_filter OK")
