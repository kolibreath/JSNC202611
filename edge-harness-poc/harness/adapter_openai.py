"""OpenAI 兼容 HTTP 适配器（免设备真模型链路）。

三个用途：
1. Termux + llama-server（设备侧起服务，adb reverse 后 PC 直连）——备链路/常驻方案 C；
2. 本机 llama.cpp server（Mac 上跑 Qwen3-1.7B 验证整条评测管线，Android 到位前的主要验证手段）；
3. 任何 OpenAI 兼容端点（含行内推理服务，用于 harness 与云端模型的对照实验）。

用法（端点由调用方保证已启动）：
  python -m harness.pipeline --backend openai --endpoint http://127.0.0.1:8080/v1 --input "查余额"

llama-server 启动示例（Qwen3-1.7B Q4_K_M，本机或 Termux）：
  llama-server -m qwen3-1.7b-q4km.gguf -c 8192 --port 8080 -fa
设备侧（Termux）使用时需先: adb reverse tcp:8080 tcp:8080
"""

from __future__ import annotations

import json
import time
import urllib.request

from harness.adapter_mnn import Timings


class OpenAIAdapter:
    """chat/completions 客户端。无第三方依赖（urllib）。"""

    def __init__(self, endpoint: str = "http://127.0.0.1:8080/v1",
                 model: str = "default", temperature: float = 0.0,
                 max_context_keep: int = 16, timeout_s: int = 120):
        self.url = endpoint.rstrip("/") + "/chat/completions"
        self.model = model
        self.temperature = temperature
        self.max_context_keep = max_context_keep
        self.timeout_s = timeout_s

    def chat(self, messages: list[dict], max_tokens: int = 512,
             json_mode: bool = False) -> tuple[str, Timings]:
        payload = {"model": self.model, "messages": messages,
                   "temperature": self.temperature, "max_tokens": max_tokens}
        if json_mode:
            # llama-server 与 OpenAI 均支持 response_format；不支持时服务端会忽略
            payload["response_format"] = {"type": "json_object"}
        t = Timings(t_submit=time.time())
        req = urllib.request.Request(
            self.url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            body = json.loads(r.read().decode("utf-8"))
        t.t_device_start = t.t_device_end = time.time()  # HTTP 场景网络耗时极小，
        t.t_return = time.time()                          # 计时以 wall 口径为准并注明
        return body["choices"][0]["message"]["content"] or "", t

    # ---- 与 MNNAdapter 同形接口：prompt 进、文本出（单轮、无历史）----
    def generate(self, prompt: str, max_new_tokens: int = 512) -> tuple[str, Timings]:
        return self.chat([{"role": "user", "content": prompt}],
                         max_tokens=max_new_tokens)
