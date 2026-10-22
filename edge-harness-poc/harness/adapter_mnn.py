"""L1 模型适配层：封装"PC Python → adb → 设备 MNN 进程"的调用。

设计要点（对应实施计划 4.1/4.2）：
- generate(prompt) 返回 (text, timings)：timings 含设备侧推理起止时间戳，
  用于把 adb 往返耗时从 TTFT 计时中扣除（性能口径见设计文档 4.4.3）。
- 实际二进制名/路径取决于 MNN 交叉编译产物，集中在下方常量，D2 完成后回填。
- W1-D4 之前：DEVICE_BIN 为单轮模式，仅供 smoke；批量评测必须等常驻改造完成。

用法：
  python harness/adapter_mnn.py --smoke --model qwen3-1.7b
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass, field

# ---- 设备侧常量（W1-D2 编译完成后回填实际路径与用法） ----
DEVICE_ROOT = "/data/local/tmp/mnn"
DEVICE_BIN = f"{DEVICE_ROOT}/llm_demo"          # TODO(D2): 确认产物名
MODELS_DIR = f"{DEVICE_ROOT}/models"            # 模型目录挂载点

MODEL_MAP = {
    "qwen3-1.7b": {
        "device_path": f"{MODELS_DIR}/qwen3-1.7b-int4",
        "max_ctx": 8192,
        # 采样参数：效果测试统一 temperature=0（贪心），top_p 按模型卡
        "temperature": 0.0,
        "top_p": 0.8,
        "top_k": 20,
    },
    "qwen3-4b-2507": {
        "device_path": f"{MODELS_DIR}/qwen3-4b-2507-int4",
        "max_ctx": 8192,
        "temperature": 0.0,
        "top_p": 0.8,
        "top_k": 20,
        # 注意：2507 为非思考版本；若使用带思考的 Qwen3 版本，
        # 需在模板中关闭 thinking（避免与约束输出冲突，见 README 已知坑）。
    },
}


@dataclass
class Timings:
    t_submit: float = 0.0        # PC 发出时刻
    t_device_start: float = 0.0  # 设备侧开始推理（D4 常驻改造后由设备进程打点回传）
    t_device_end: float = 0.0
    t_return: float = 0.0
    raw_fields: dict = field(default_factory=dict)


class MNNAdapter:
    """真机适配器。"""

    def __init__(self, model: str, device_serial: str | None = None,
                 timeout_s: int = 120):
        if model not in MODEL_MAP:
            raise KeyError(f"unknown model {model}; known: {list(MODEL_MAP)}")
        self.cfg = MODEL_MAP[model]
        self.model = model
        self.serial = device_serial
        self.timeout_s = timeout_s

    # ---------- adb 基础 ----------
    def _adb(self, *args: str, input_text: str | None = None) -> str:
        cmd = ["adb"]
        if self.serial:
            cmd += ["-s", self.serial]
        cmd += list(args)
        r = subprocess.run(cmd, capture_output=True, text=True,
                           input=input_text, timeout=self.timeout_s)
        if r.returncode != 0:
            raise RuntimeError(f"adb failed: {' '.join(cmd)}\n{r.stderr}")
        return r.stdout

    # ---------- 推理 ----------
    def generate(self, prompt: str, max_new_tokens: int = 256) -> tuple[str, Timings]:
        """单条推理。

        TODO(D4): 常驻改造前的临时实现——每条一个进程，仅限 smoke；
        常驻改造后改为：批量文件/stdin 模式 + 设备侧打点回传。
        """
        t = Timings(t_submit=time.time())
        out = self._adb("shell", f"{DEVICE_BIN} --model {self.cfg['device_path']}",
                        input_text=prompt)
        t.t_return = time.time()
        # TODO(D2/D4): 按实际输出协议解析正文与设备侧时间戳
        return out.strip(), t


class DryAdapter:
    """无设备联调适配器：按 prompt 类型 + 输入关键词返回确定性桩输出，
    用于在笔记本上联调模板渲染与路由状态机的全部分支（W1-D6）。
    约定：按 prompt 标记片段分类；再从尾部"输入：/用户输入：/用户原话"取用户文本，
    用关键词路由到不同桩输出。不模拟模型误差。"""

    # 输入关键词 → 意图桩（与 registry/intents.yaml 对应，供 intent 分支演示）
    # 规则有序：试算/咨询类在前，动作类在后（"跨行转账要手续费吗"应判咨询而非转账）
    _INTENT_RULES = [
        (("存一年", "存三年", "存半年", "存五年", "利息大概", "利息多少"),
         '{"intent":"calc_deposit_interest","confidence":0.9,"slots":{}}'),
        (("手续费", "利率"), '{"intent":"fee_consult","confidence":0.9,"slots":{}}'),
        (("转账", "汇款", "转给", "转到", "付钱", "块钱给", "转一", "转两", "转三", "转四", "转五",
          "转六", "转七", "转八", "转九", "转千", "转万"),
         '{"intent":"transfer_out","confidence":0.93,"slots":{}}'),
        (("网点", "营业厅"), '{"intent":"find_branch","confidence":0.88,"slots":{}}'),
        (("天气", "股票", "笑话"), '{"intent":"out_of_scope","confidence":0.95,"slots":{}}'),
        (("余额", "剩多少钱"), '{"intent":"query_balance","confidence":0.92,"slots":{}}'),
    ]
    _INTENT_DEFAULT = '{"intent":"query_balance","confidence":0.9,"slots":{}}'

    @staticmethod
    def _user_text(prompt: str) -> str:
        for marker in ("用户输入：", "用户问题：", "\n输入："):
            if marker in prompt:
                return prompt.rsplit(marker, 1)[1].strip()
        return ""

    def generate(self, prompt: str, max_new_tokens: int = 256) -> tuple[str, Timings]:
        now = time.time()
        t = Timings(t_submit=now, t_device_start=now, t_device_end=now + 0.1,
                    t_return=now + 0.1)
        ut = self._user_text(prompt)
        if "占位符" in prompt:                                   # mask.j2
            if any(k in ut for k in ("张三", "6222", "建设路")):
                text = ('{"text":"[姓名_1]的手机尾号卡 [卡号_1] 那笔钱转到[地址_1]",'
                        '"entities":[{"type":"NAME","original":"张三","placeholder":"[姓名_1]"},'
                        '{"type":"BANK_CARD","original":"6222","placeholder":"[卡号_1]"},'
                        '{"type":"ADDR","original":"建设路88号","placeholder":"[地址_1]"}]}')
            else:
                text = '{"text":"' + ut + '","entities":[]}'
        elif "意图清单" in prompt:                               # intent.j2
            text = next((out for keys, out in self._INTENT_RULES
                         if any(k in ut for k in keys)), self._INTENT_DEFAULT)
        elif "<tool>" in prompt:                                 # tool_call.j2
            text = '<tool_call>{"name":"get_balance","arguments":{}}</tool_call>'
        elif "向用户播报" in prompt:                              # 工具结果总结
            text = "[MOCK] 您的默认账户余额为 5,234.10 元。"
        elif "资料" in prompt:                                   # faq.j2
            text = "[MOCK] 手机银行行内转账手续费为 0 元（占位示例，以行内公示为准）。"
        else:                                                    # 其他（smoke 等）
            text = "[MOCK] OK"
        return text, t


def smoke(model: str, device_serial: str | None) -> None:
    print(f"[smoke] model={model} device={device_serial or 'default'}")
    ad = MNNAdapter(model, device_serial)
    print("[smoke] adb devices ->")
    print(ad._adb("devices"))
    print("[smoke] 单轮推理（临时实现，仅验证链路） ->")
    text, t = ad.generate("你好，请回复：OK")
    print(text)
    print(f"[smoke] wall={t.t_return - t.t_submit:.2f}s（含 adb 往返，不计入性能口径）")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--model", default="qwen3-1.7b",
                    choices=list(MODEL_MAP))
    ap.add_argument("--device", default=None, help="adb serial")
    a = ap.parse_args()
    if a.smoke:
        smoke(a.model, a.device)
    else:
        print(__doc__)
