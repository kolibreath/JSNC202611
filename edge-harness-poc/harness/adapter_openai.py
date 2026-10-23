"""OpenAI 兼容 HTTP 适配器（免设备真模型链路）。

三个用途：
1. Termux + llama-server（设备侧起服务，PC 直连）——备链路/常驻方案 C；
2. 本机 llama.cpp server（Mac/PC 上跑 Qwen3-1.7B 验证整条评测管线，Android 到位前的主要验证手段）；
3. 任何 OpenAI 兼容端点（含行内推理服务，用于 harness 与云端模型的对照实验）。

用法（端点由调用方保证已启动）：
  python -m harness.pipeline --backend openai --endpoint http://127.0.0.1:8080/v1 --input "查余额"

llama-server 启动示例（本机或 Termux）：
  llama-server -m Qwen3-1.7B-Q8_0.gguf -c 8192 --port 8080 --host 127.0.0.1 -fa on --reasoning off
  （b11669+ 用 --reasoning off 关思考；旧版用 --chat-template-kwargs '{"enable_thinking":false}'）

设备侧（Termux）连接方式，二选一：
  - USB：adb forward tcp:8080 tcp:8080 后访问 http://127.0.0.1:8080/v1
    （注意方向是 forward：PC 客户端 → 设备服务。adb reverse 是"设备客户端 → PC 服务"方向，
      会与 Termux 抢占同一设备端口导致 couldn't bind——评测-02 实测坑，勿再写反）
  - 局域网：设备端 --host 0.0.0.0，PC 访问 http://<设备IP>:8080/v1（无鉴权，评测完务必关闭）
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

from harness.adapter_mnn import Timings

HTTP_RETRIES = 2          # 5xx/连接错误重试次数（评测-02 真机 8/176 传输错误的对策）
RETRY_BACKOFF_S = (0.5, 1.5)


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
        body = self._open_with_retry(req)
        t.t_device_start = t.t_device_end = time.time()  # HTTP 场景网络耗时极小，
        t.t_return = time.time()                          # 计时以 wall 口径为准并注明
        return body["choices"][0]["message"]["content"] or "", t

    def _open_with_retry(self, req: urllib.request.Request) -> dict:
        """仅对 5xx 与连接类错误重试（4xx 属请求本身问题，重试无意义）。"""
        last_err: Exception | None = None
        for attempt in range(HTTP_RETRIES + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
                    return json.loads(r.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code < 500:
                    raise
                last_err = e
            except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
                last_err = e
            if attempt < HTTP_RETRIES:
                time.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)])
        raise last_err  # type: ignore[misc]

    # ---- 与 MNNAdapter 同形接口：prompt 进、文本出（单轮、无历史）----
    def generate(self, prompt: str, max_new_tokens: int = 512) -> tuple[str, Timings]:
        return self.chat([{"role": "user", "content": prompt}],
                         max_tokens=max_new_tokens)
