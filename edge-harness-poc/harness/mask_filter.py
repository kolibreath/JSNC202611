"""mask 二级过滤（优化项 O4）：对模型标注的实体做类型校验，还原明显误标。

背景：首轮实测 mask 精确率 0.832，34/160 行误脱敏（订单号/金额/日期被当 PII），
mask.j2 的文字规则 1.7B 执行不稳 → 精度改由代码保证，模型只负责"多标"。

两级判定，命中任一还原条件则该实体从脱敏结果中撤回（占位符换回原文）：
- L1 明显非 PII 白名单（保守，不依赖所标类型）：
  ≤6 位短数字（验证码/尾号）、金额（数字+元/万/块）、日期、订单号（含字母或连字符分段）；
- L2 校验位核验（按所标类型）：BANK_CARD → Luhn 不过；ID_CARD → GB-11643 mod-11 不过；
  PHONE → 数字位数不在 7–12 区间（既非手机号也非座机）。

测试集的卡号/证件号均按校验位算法生成，L2 在测试集上零副作用；生产上用户
输错的证件号会漏保护，属已声明权衡（方案-Harness优化实施计划.md O4）。
NAME/ADDR 无可靠校验规则，保留模型判断。

开关：环境变量 MASK_FILTER=off 关闭（默认开启）。
"""

from __future__ import annotations

import os
import re

_MOBILE_RE = re.compile(r"^1[3-9]\d{9}$")
_SHORT_DIGITS_RE = re.compile(r"^\d{1,6}$")
_HAS_ALPHA = re.compile(r"[A-Za-z]")
_ORDER_RE = re.compile(r"^[A-Za-z0-9]+(?:-[A-Za-z0-9]+)+$")       # 连字符分段（如 A2026-8856）
_AMOUNT_RE = re.compile(r"^\d+(?:\.\d+)?\s*[万亿]?(?:元|块|块钱|圆)$")
_DATE_RE = re.compile(
    r"^\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?$|^\d{1,2}月\d{1,2}[日号]$")

_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_MAP = "10X98765432"


def luhn_ok(num: str) -> bool:
    digits = re.sub(r"\D", "", str(num))
    if not (12 <= len(digits) <= 19):
        return False
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def idcard_ok(idc: str) -> bool:
    s = str(idc).strip().upper()
    if not re.match(r"^\d{17}[\dX]$", s):
        return False
    total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
    return _ID_MAP[total % 11] == s[17]


def _looks_non_pii(value: str) -> bool:
    """L1：无论标成什么类型，长得就像非 PII 的一律还原。"""
    v = value.strip()
    if not v:
        return True
    if _SHORT_DIGITS_RE.match(v):
        return True
    if _AMOUNT_RE.match(v):
        return True
    if _DATE_RE.match(v):
        return True
    if _ORDER_RE.match(v) and _HAS_ALPHA.search(v):
        return True
    return False


def should_restore(entity: dict) -> bool:
    """True = 该实体判定为误标，应撤回脱敏（还原原文）。"""
    v = str(entity.get("original", ""))
    t = str(entity.get("type", "")).upper()
    if _looks_non_pii(v):
        return True
    if t == "BANK_CARD" and not luhn_ok(v):
        return True
    if t == "ID_CARD" and not idcard_ok(v):
        return True
    if t == "PHONE":
        digits = re.sub(r"\D", "", v)
        if not digits or not (7 <= len(digits) <= 12):
            return True
    return False


def apply_mask_filter(entities: list, masked_text: str
                      ) -> tuple[list, str, list]:
    """过滤实体并在文本中还原被撤回实体的占位符。

    返回 (保留实体, 新文本, 被还原的原文列表)。MASK_FILTER=off 时原样透传。
    """
    if os.environ.get("MASK_FILTER", "on").strip().lower() in ("off", "0", "false"):
        return entities, masked_text, []
    kept, restored = [], []
    for e in entities:
        (restored if should_restore(e) else kept).append(e)
    text = masked_text
    for e in restored:
        ph = str(e.get("placeholder", ""))
        if ph and ph in text:
            text = text.replace(ph, str(e.get("original", "")))
    return kept, text, [str(e.get("original", "")) for e in restored]
