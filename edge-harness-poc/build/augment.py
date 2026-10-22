"""增广器：离线规则版（立即可用）+ LLM 改写客户端接口（W2 接行内 API）。

LLM 接入点：实现 LLMRewriter.rewrite() 调用行内任意旗舰模型，对种子做
4 类改写（口语化/错别字拼音/老年口吻/极简指代），prompt 见 REWRITE_PROMPT。
"""

from __future__ import annotations

import json
import random
import urllib.request

REWRITE_PROMPT = """你是手机银行用户语料增广器。对下面这条"用户想说的话"各生成一个变体：
1. 口语化（随意、省略）
2. 带错别字或拼音混写（如 帮偶查哈子）
3. 老年人口吻（啰嗦、礼貌、无主语）
4. 极简指代（假设有上文，如"那笔呢""再查一个"）
保持原意不变。只输出 JSON 数组：["变体1","变体2","变体3","变体4"]
原句：{seed}"""

_PREFIX = ["", "帮我", "麻烦", "请问", "我想", "我要", "帮我看看", "麻烦你"]
_SUFFIX = ["", "吧", "呢", "啊", "呀", "谢谢", "行吗"]
_SUBS = [("什么", "啥"), ("怎么", "咋"), ("查询", "查下"), ("一下", "哈子"),
         ("多少", "好多"), ("办理", "弄"), ("开通", "开个")]
_ELDERLY = ["老人家不太会弄，{s}", "我年纪大了，{s}", "麻烦你慢慢说，{s}", "我想问一下啊，{s}"]


class RuleAugmenter:
    """确定性规则增广（v0 草案用；质量有限，W2 由 LLM 增广替代并冻结 v1.0）。"""

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    def variants(self, s: str) -> list[str]:
        out = set()
        plain = s
        for a, b in _SUBS:                       # 口语替换
            plain = plain.replace(a, b)
        out.add(plain)
        out.add(self.rng.choice(_PREFIX) + s + self.rng.choice(_SUFFIX))
        out.add(self.rng.choice(_PREFIX) + plain)
        out.add(self.rng.choice(_ELDERLY).format(s=s))
        out.add(s + self.rng.choice(_SUFFIX) + "？")
        out.discard(s)
        return sorted(out)


class LLMRewriter:
    """W2 接入：指向行内 OpenAI 兼容端点即可。"""

    def __init__(self, endpoint: str, model: str):
        from harness.adapter_openai import OpenAIAdapter
        self.ad = OpenAIAdapter(endpoint, model)

    def rewrite(self, seed_text: str) -> list[str]:
        prompt = REWRITE_PROMPT.format(seed=seed_text)
        raw, _ = self.ad.generate(prompt, max_new_tokens=256)
        try:
            arr = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
            return [str(x) for x in arr][:4]
        except (ValueError, json.JSONDecodeError):
            return []


if __name__ == "__main__":     # 自检
    aug = RuleAugmenter()
    for v in aug.variants("查一下余额"):
        print(v)
