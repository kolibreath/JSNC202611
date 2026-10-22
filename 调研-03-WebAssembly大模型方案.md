# 调研-03：基于 WebAssembly（WASM）构建/运行的大模型方案

- 调研日期：2026-10-20（文中标注"访问日期 2026-10-20"的来源均在本日核实）
- 调研范围：浏览器内 WASM/WebGPU 推理方案（WebLLM、wllama、transformers.js、onnxruntime-web、llama.cpp WASM）、服务端/边缘 WASM 运行时（WasmEdge/WASI-NN）、浏览器内置 AI 与 WebNN 的关系辨析、银行业适用性
- 结论先行：**浏览器端跑大模型在 2024-2026 年已从演示走向可用**：WebGPU 方案（WebLLM）在高端桌面可达原生约 70-85% 性能；纯 WASM CPU 方案（wllama、onnxruntime-web）适合 0.5B-3B 小模型与 embedding；Firefox 已用 transformers.js + ONNX WASM 在生产环境 shipped 端侧 AI 功能（PDF 图片替代文本）。但截至 2026-10 **未检索到任何银行/金融机构公开的浏览器内 WASM LLM 生产案例**。

---

## ① WASM 系方案总览

### 总览表

| 方案 | 执行后端 | 模型格式 | API 形态 | 典型模型规模 | 离线能力 | 现状（2026-10） |
|---|---|---|---|---|---|---|
| **WebLLM**（mlc-ai/web-llm） | WebGPU（计算内核 WGSL + WASM 运行时库） | MLC 格式（TVM 编译产物，托管于 HF `mlc-llm` org） | OpenAI 兼容 `chat.completions`（流式、JSON mode、function calling、embeddings） | 0.1B-8B 主力，最大 70B（需 ~31GB 显存） | Service Worker + Cache API/IndexedDB/OPFS，可做 PWA | Apache-2.0，19.3k stars，最新 v0.2.86（2026-10-11）[来源：GitHub Releases](https://github.com/mlc-ai/web-llm/releases) 访问日期 2026-10-20 |
| **wllama**（ngxson/wllama） | WASM CPU（SIMD，可选多线程）+ WebGPU（v3.1+ 接入 llama.cpp WebGPU 后端） | GGUF（llama.cpp 生态任意量化模型） | OpenAI 兼容聊天 API、多模态（图片/音频输入）、工具调用 | 0.5B-3B（CPU），2GB 单文件上限 | 模型分片缓存，Worker 内推理不阻塞 UI | MIT，持续活跃 [来源：GitHub README](https://github.com/ngxson/wllama) 访问日期 2026-10-20 |
| **transformers.js**（Hugging Face，npm `@huggingface/transformers`） | WASM CPU（默认 q8）+ WebGPU（`device:'webgpu'`，默认 fp32） | ONNX（Optimum 转换，HF Hub 1200+ 预转换模型） | Python transformers 同构 pipeline API（非 OpenAI 风格） | 小 LLM/嵌入/视觉/语音全覆盖（BERT、Llama 2-4、Qwen 2/3、Gemma、Phi、Whisper、SAM 等 120+ 架构） | 模型走 HF Hub 或本地 `env` 自定义路径（可内网自托管） | 最新 v4.3.1（v3.0.0 于 2024-10-18 发布引入 WebGPU）[来源：npm registry](https://registry.npmjs.org/@huggingface/transformers)、[GitHub](https://github.com/huggingface/transformers.js) 访问日期 2026-10-20 |
| **onnxruntime-web**（微软，`@onnxruntime/web`） | WASM CPU（Emscripten 编译原生 ORT，"接近原生 CPU 速度"，支持多线程）+ WebGPU（实验）+ WebGL（维护模式，建议弃用）+ WebNN（实验，Chrome/Edge Windows 需 flag） | ONNX | 张量级推理 API（是 transformers.js 的底层引擎） | 任意 ONNX 模型 | 与上层框架配合 | 持续维护 [来源：GitHub js/web](https://github.com/microsoft/onnxruntime/tree/main/js/web) 访问日期 2026-10-20 |

补充（非浏览器但同属 WASM 生态）：

- **llama.cpp 官方 WASM 构建**：官方仓库支持经 Emscripten 工具链编译（`-DCMAKE_TOOLCHAIN_FILE=emscripten`），社区有构建指南与讨论（ggml-org/llama.cpp Discussion #17237，2025）；社区项目 `tangledgroup/llama-cpp-wasm` 提供单线程/多线程（SIMD）构建产物；官方浏览器方向的重心是 2025 年合入的 WebGPU 后端（Reese Levine，已通过 wllama v3.1 暴露给 Web 开发者）。[来源：GitHub Discussion #17237](https://github.com/ggml-org/llama.cpp/discussions/17237)、[llama-cpp-wasm](https://github.com/tangledgroup/llama-cpp-wasm)、[Llamas on the Web](https://reeselevine.github.io/llamas-on-the-web) 访问日期 2026-10-20
- **WasmEdge / WASI-NN（服务端/边缘 WASM，非浏览器）**：WasmEdge 通过 wasi-nn GGML 插件（基于 llama.cpp）跑 Llama-3.1-8B 级模型，LlamaEdge 提供 OpenAI 兼容 API 服务；定位是服务器/边缘的可移植轻量运行时（快冷启动、小 footprint），与浏览器内 WASM 是两条路线。[来源：WasmEdge 文档](https://wasmedge.org/docs/develop/rust/wasinn/llm_inference)、[LlamaEdge](https://github.com/WasmAI/WasmEdge-LlamaEdge) 访问日期 2026-10-20
- Google 官方口径：**"大多数在 Web 上运行 AI 推理的生产应用都使用 WebAssembly"**（既做 CPU 计算、也做与专用计算接口的桥接），WASM 与 WebGPU 是互补关系而非竞争。[来源：Chrome 开发者博客](https://developer.chrome.com/blog/io24-webassembly-webgpu-1) 访问日期 2026-10-20

### 各方案要点

#### 1. WebLLM（浏览器内 LLM 推理的事实标杆）

- 定位：WebGPU 硬件加速的浏览器内 LLM 推理引擎，MLC-LLM/TVM 家族的 Web 端形态；内核为 WGSL compute shader + WASM 运行时库（TVMjs）。[来源：MLC AI 官方博客 2024-06-13](https://blog.mlc.ai/2024/06/13/webllm-a-high-performance-in-browser-llm-inference-engine) 访问日期 2026-10-20
- API：`engine.chat.completions.create()` 完全对齐 OpenAI API，支持流式（AsyncGenerator 逐 token）、JSON mode、种子/logit 控制、function calling、embeddings；模型经 `CreateMLCEngine(modelId)` 加载。[来源：GitHub README](https://github.com/mlc-ai/web-llm) 访问日期 2026-10-20
- 离线/持久化：`ServiceWorkerMLCEngine` 让模型跨页面存活并改善离线体验（心跳保活）；缓存后端支持 Cache API（默认）、IndexedDB、OPFS 及实验性跨源存储；支持 Web Worker 与 Chrome 扩展环境。[来源：GitHub README](https://github.com/mlc-ai/web-llm)、[Releases v0.2.85](https://github.com/mlc-ai/web-llm/releases) 访问日期 2026-10-20
- 支持的模型家族（社区整理自 `src/lib/config.ts`，更新至 2025-05；新版继续增加）：
  - Llama-2/3/3.1/3.2（含 70B，q3f16 约 31GB 显存；Llama-3.2-1B 最低配置约 879MB 显存，q0f32 约 5106MB）[来源：GitHub Issue #683](https://github.com/mlc-ai/web-llm/issues/683) 访问日期 2026-10-20
  - Qwen2/2.5（0.5B-7B，含 Coder、Math）、**Qwen3（2025-05 前后加入，支持可开关的思维链）**，如 `mlc-ai/Qwen3-1.7B-q4f16_0-MLC` [来源：GitHub Issue #683](https://github.com/mlc-ai/web-llm/issues/683)、[HF 模型页](https://huggingface.co/mlc-ai/Qwen3-1.7B-q4f16_0-MLC)、[dev.to 实测](https://dev.to/creeta/qwen3-in-the-browser-zero-keys-webllm-0283-hands-on-3ai2) 访问日期 2026-10-20
  - DeepSeek-R1-Distill-Qwen-7B / Llama-8B（2025-01 随 R1 开源迅速上线，官方 demo Space `webml-community/deepseek-r1-webgpu`）[来源：GitHub Issue #683](https://github.com/mlc-ai/web-llm/issues/683)、[HF Space](https://huggingface.co/spaces/webml-community/deepseek-r1-webgpu) 访问日期 2026-10-20
  - Phi-1.5/2/3.5（含 vision）、Gemma-2（2b/9b/日文版）、SmolLM2（135M/360M/1.7B）、Mistral 7B 系、Hermes 系、TinyLlama-1.1B、StableLM Zephyr 1.6B
  - **嵌入模型**：snowflake-arctic-embed-m/-s（可用于浏览器内 RAG）[来源：GitHub Issue #683](https://github.com/mlc-ai/web-llm/issues/683) 访问日期 2026-10-20
  - 最新版 v0.2.86（2026-10-11）新增 Gemma 4 E2B 指令模型（q4f16_1/q4f32_1，支持文本+音频输入），并重建 224 个 WebGPU 库。【Gemma 4 E2B 具体命名与能力待核实】[来源：GitHub Releases](https://github.com/mlc-ai/web-llm/releases) 访问日期 2026-10-20
- 约束：必须 WebGPU 浏览器（Chrome/Edge 桌面与 Android、Safari 26+；Firefox 默认未开）；企业内网需注意 WebGPU 在旧版 Chromium 不可用（Chrome 113 起才支持）。

#### 2. wllama（llama.cpp 的 WASM 绑定）

- 定位：把 llama.cpp 编译到 WASM，**直接吃 GGUF 模型生态**（这是它与 WebLLM/transformers.js 最大的差异：无需模型转换）；MIT 协议。[来源：GitHub README](https://github.com/ngxson/wllama) 访问日期 2026-10-20
- 能力：OpenAI 兼容 API；多模态（图片/音频输入）；工具调用；**v3.1 起支持 WebGPU**（经 llama.cpp WebGPU 后端，PR #215），同时保留纯 WASM CPU 路线（SIMD，单线程/多线程自动切换；多线程依赖 SharedArrayBuffer，需站点配置 COOP/COEP 跨源隔离响应头）。
- 明确的工程限制（官方 README 原文）：
  - **单文件上限 2GB（ArrayBuffer 限制），建议把 GGUF 切成 512MB 分片**；
  - 推荐 Q4/Q5/Q6 量化（CPU 上表现最好），**不推荐 IQ 系列**；
  - 推理默认在 Worker 线程执行，不冻结 UI；
  - Firefox/Safari 上 WebGPU 需走 `setCompat()` 兼容模式，**性能显著下降**（降级 shader 路径）。[来源：GitHub README](https://github.com/ngxson/wllama) 访问日期 2026-10-20
- 分工结论：**纯 CPU WASM（SIMD+多线程）适合 0.5B-3B 小模型做离线兜底/无 WebGPU 环境；WebGPU 路线负责性能**。wllama v3.1 后两者兼备，但 Firefox/Safari 的 WebGPU 兼容模式意味着在这两个浏览器上实际还是 CPU 档性能。

#### 3. transformers.js（Hugging Face）

- v3.0.0（2024-10-18/22 发布）：引入 **WebGPU 后端（官方口径"部分模型比 WASM 快最多 100 倍"）**、全面量化支持（fp32/fp16/q8/int8/uint8/q4/bnb4/q4f16，可按模块混合 dtype）、支持 120+ 架构/1200+ 预转换模型、Node.js(ESM+CJS)/Deno/Bun 全运行时。[来源：HF 官方博客 Transformers.js v3](https://huggingface.co/blog/transformersjs-v3) 访问日期 2026-10-20
- 当前版本 v4.3.1（npm latest，2026 年）；README 明示默认 CPU WASM（dtype q8）、WebGPU 仍标注"实验性"。[来源：npm registry](https://registry.npmjs.org/@huggingface/transformers)、[GitHub](https://github.com/huggingface/transformers.js) 访问日期 2026-10-20
- 小 LLM 浏览器内 RAG 的公开路径：transformers.js（embedding 模型如 bge/snowflake，或 Qwen2.5-0.5B/SmolLM 级小 LLM）+ 浏览器向量检索，官方教程即以 Qwen2.5-0.5B q4 WebGPU 为示例。[来源：HF 官方博客](https://huggingface.co/blog/transformersjs-v3) 访问日期 2026-10-20
- **生产环境先例——Firefox（最重要的参考案例）**：
  - Firefox 130（2024-09）起，内置 PDF 编辑器（PDF.js）提供**端侧 AI 图片替代文本生成**：ViT + DistilGPT-2 图像描述模型（Mozilla 自训 distilvit，约 1.82 亿参数，量化后磁盘占用 200MB 以内，"笔记本上数秒完成"）；技术栈为 **ONNX Runtime（WASM）+ transformers.js**，独立进程运行防崩溃，模型经 Firefox Remote Settings 下发并缓存于 IndexedDB。[来源：Mozilla Hacks 2024-05](https://hacks.mozilla.org/2024/05/experimenting-with-local-alt-text-generation-in-firefox-nightly) 访问日期 2026-10-20
  - Mozilla 工程师 2025-09 博客复盘训练细节（COCO/Flickr30k 重标注、用户纠错回流微调）；注意：网传"基于 Moondream"说法不确，官方模型为 ViT+DistilGPT2。[来源：Tarek Ziadé 博客 2025-09-01](https://blog.ziade.org/2025/09/01/first-machine-learning) 访问日期 2026-10-20
  - 关键启示：**Firefox 至今未默认开启 WebGPU**（见③），即这个最大规模的浏览器端侧 AI 生产案例是**纯 WASM CPU 路线**跑出来的——证明小模型 + WASM CPU 在生产上成立。

#### 4. onnxruntime-web（微软，WASM 基座）

- WASM 后端由原生 ONNX Runtime 经 Emscripten 编译而来，支持绝大多数原生算子（ai.onnx / ai.onnx.ml），官方口径 CPU"接近原生速度"，支持多线程；WebGPU 后端实验性（Chrome/Edge Win v113+/Android v121+/macOS，不支持 Safari/iOS/Firefox）；WebGL 维护模式；**WebNN 后端实验性（Chrome/Edge on Windows，需启动 flag）**。[来源：GitHub js/web README](https://github.com/microsoft/onnxruntime/tree/main/js/web) 访问日期 2026-10-20
- 生态位：transformers.js、wllama 之外几乎所有"Web + ONNX"方案（含各行业自研推理页）的底层引擎。

---

## ② 性能数据汇总

| 场景 | 数据 | 硬件/环境 | 来源 |
|---|---|---|---|
| WebLLM 解码速度 | Llama-3.1-8B(q4)：**41.1 tok/s**（原生 MLC 57.7，保留 71.2%）；Phi-3.5-mini-3.8B：**71.1 tok/s**（原生 89.3，保留 79.6%） | MacBook Pro M3 Max，Chrome Canary 133，WebLLM v0.2.75 | [WebLLM 论文 arXiv:2412.15803](https://arxiv.org/abs/2412.15803) Table 1，访问日期 2026-10-20 |
| WebLLM 总体结论 | "保留最高约 80% 原生解码吞吐"；论文引言：4-bit 3B 模型在 Apple M3 笔记本上约 **90 tok/s** | M 系列 Mac | 同上 |
| WebGPU vs 原生（早期口径） | WebGPU 保留**最高 85%**原生性能（Llama-3-8B 4-bit，prefill 64/decode 128 tokens 场景） | M3 Max | [MLC AI 官方博客 2024-06-13](https://blog.mlc.ai/2024/06/13/webllm-a-high-performance-in-browser-llm-inference-engine) 访问日期 2026-10-20 |
| 浏览器 LLM vs 云端 LLM | WebGPU 内 Llama-3.1-8B 约 **4.8x** Gemini-1.5 Pro API 吞吐 | M2 Max，Chrome | 同上（MLC 官方博客引 Google 研究） |
| Android/低端设备 | 社区实测浏览器内 LLM 普遍 **1-2 tok/s**（一般硬件）、启动延迟 3-6s；中端手机低个位数 tok/s | Chrome/Edge/Firefox，3B 级模型 | [Medium 社区评测](https://medium.com/@hadiyolworld007/running-llms-in-the-browser-performance-or-fantasy-6c3464a1d197) 访问日期 2026-10-20（社区数据，非官方基准）【待核实：缺分机型官方数据】 |
| wllama vs transformers.js（同一小模型） | Bonsai-1.7B（1-bit）：wllama 解码 **58-60 tok/s**、首 token ~155ms、模型加载 0.73-0.8s；transformers.js(WebGPU) 解码 62-66 tok/s、首 token ~134ms、加载 ~2.5s（wllama 冷启动快约 3 倍） | MacBook Pro M3 Pro，Chrome，模型已缓存 | [mikeesto.com 评测 2026-05-26](https://mikeesto.com/posts/wllama) 访问日期 2026-10-20（作者自注"非正式小样本测试"） |
| transformers.js WebGPU 加速比 | 部分模型/算子 **最多 100x**（vs WASM CPU） | 官方博客口径 | [HF 博客 transformers.js v3](https://huggingface.co/blog/transformersjs-v3) 访问日期 2026-10-20 |
| Firefox 端侧 alt text | ~182M 参数模型（量化后 <200MB），笔记本上"数秒"完成单图 | Firefox 130+，WASM CPU | [Mozilla Hacks](https://hacks.mozilla.org/2024/05/experimenting-with-local-alt-text-generation-in-firefox-nightly) 访问日期 2026-10-20 |
| 原生 NPU 对照（浏览器外） | Qualcomm NPU + LiteRT：prefill 11,000+ tok/s、decode 100+ tok/s——浏览器方案与其差距仍有数量级 | Snapdragon | [Google 开发者博客 2025-11](https://developers.googleblog.com/unlocking-peak-performance-on-qualcomm-npu-with-litert) 访问日期 2026-10-20 |
| 显存需求参考 | Llama-3.2-1B：879MB(q4f16)-5106MB(q0f32)；Llama-3-70B q3f16 约 31GB | WebLLM 官方模型表 | [GitHub Issue #683](https://github.com/mlc-ai/web-llm/issues/683) 访问日期 2026-10-20 |

**性能结论**：
1. 桌面高端硬件（M 系列/A 卡/N 卡 + Chrome/Edge）上 WebGPU 方案跑 1B-8B q4 模型可做到 40-90 tok/s，交互体验流畅；
2. 纯 WASM CPU 路线适合 ≤3B 模型，几十 tok/s 量级（M3 Pro 上 1.7B 1-bit 约 60 tok/s），冷启动反而更快；
3. 手机端（Chrome Android WebGPU 已可用）性能掉到个位数 tok/s，只适合 ≤1.5B 模型或非实时任务【待核实：缺官方 Android 基准】；
4. 未找到 Windows GPU 上 WebLLM 的官方分机型基准，只有论文 M3 Max 一档【待核实】。

---

## ③ 浏览器能力现状（WebGPU / 内置 AI / WebNN）

### WebGPU 可用性（2026-09 数据）

- 全球覆盖率 **87.82%**（完全支持 85.8% + 部分支持 2.02%）。[来源：caniuse.com/webgpu](https://caniuse.com/webgpu)（StatCounter 2026-09）访问日期 2026-10-20
  - Chrome/Edge 桌面：113+ 全面支持；Chrome Android：支持（155）；
  - **Safari：26.0 起**（2025-09-15 发布正式启用 WebGPU；WebKit 官方博客确认 macOS/iOS/iPadOS/visionOS 全平台；26.0 阶段不含 WebXR 用途，26.2 继续扩展）[来源：WebKit 官方博客 Safari 26.0](https://webkit.org/blog/17333/webkit-features-in-safari-26-0)、[Safari 26.2](https://webkit.org/blog/17640/webkit-features-for-safari-26-2)、[Apple 发布说明](https://developer.apple.com/documentation/safari-release-notes/safari-26-release-notes) 访问日期 2026-10-20；caniuse 将桌面版标为"部分支持"、iOS 标为完全支持，两者口径略有出入【待核实：以实际目标机型测试为准】
  - **Firefox：至今默认关闭**（63-161 版本均为 disabled by default）——Firefox 用户只能走 WASM CPU 路线。[来源：caniuse.com/webgpu](https://caniuse.com/webgpu) 访问日期 2026-10-20
- 对银行的实际含义：行内标准化浏览器若为较新 Chromium（113+，2023-04 后版本）即可用 WebGPU；若含 Firefox 或老版本浏览器，需 WASM CPU 降级方案。

### 浏览器内置 AI ≠ 页面 WASM（定位辨析）

- **Chrome 内置 Gemini Nano（Prompt API / AI Language Model APIs / Extensions API）**：
  - Prompt API（`window.ai` / `LanguageModel`）使用**浏览器自带的 Gemini Nano**，模型由 Chrome 经 Optimization Guide 组件统一下发管理，**不是页面里的 WASM 推理**——页面 JS 只调用高层 API。Web 平台 **Chrome 138 起稳定**；Chrome 扩展 **148** 起可用；2025-05 Chrome 138 起支持音频/图像输入与 JSON Schema 结构化输出；采样参数（topK/temperature）经 141-148 的 origin trial 逐步开放；**不支持在 Web Worker 中使用**。[来源：Chrome 官方文档 Prompt API](https://developer.chrome.com/docs/ai/prompt-api) 访问日期 2026-10-20
  - 硬件门槛：仅桌面（Win10/11、macOS 13+、Linux、Chromebook Plus；**不含 Android/iOS Chrome**）；需 22GB 空闲磁盘；GPU 需 >4GB VRAM 或 16GB RAM + 4 核 CPU。[来源：Chrome 官方文档 Prompt API](https://developer.chrome.com/docs/ai/prompt-api) 访问日期 2026-10-20
  - AI Language Model API（原 Session API）：面向长文本生成/摘要的会话式 API，支持 initial prompt、上下文配额查询、tokensPerSecond 读取；截至 2026-10 页面标注实验性。第三方（DataDome 2026-04）称 `LanguageModel` API 计划随 **Chrome 148** ship。[来源：Chrome 官方文档](https://developer.chrome.com/docs/ai/language-model-api)（本日访问不稳定，部分细节转引）、[DataDome 研究 2026-04-22](https://datadome.co/threat-research/how-chromes-new-ai-web-apis-enable-hardware-fingerprinting) 访问日期 2026-10-20【待核实：148 版本节点】
  - 两者定位差异（写报告建议保留这张对比）：

| 维度 | 页面 WASM/WebGPU（WebLLM、transformers.js 等） | 浏览器内置 AI（Chrome Prompt API 等） |
|---|---|---|
| 模型来源 | 应用自选任意开源模型（可自托管于内网） | 浏览器内置（Gemini Nano），不可替换 |
| 更新控制 | 应用侧完全控制版本 | 随浏览器自动更新，企业可用策略管控但模型能力不受应用控制 |
| 隐私 | 数据不出页面/内网 | 端侧运行但模型由 Google 下发，需评估数据外发策略选项 |
| 性能上限 | 取决于设备 GPU/CPU + 模型大小 | 固定 ~3B 级模型，速度由浏览器优化 |
| 兼容性 | 依赖 WebGPU/WASM（跨 Chromium/Safari） | 仅 Chrome/Edge（桌面），Firefox/Safari 无对应 API |
| 内网适配 | 模型文件可放内网静态服务器，完全离线 | 首次需从 Google 下载模型组件，**纯隔离内网基本不可用** |

- **Safari/WebKit 端侧 AI 动向**：截至 WWDC 2026，**WebKit 没有公开的浏览器端侧 AI API**；Apple 的端侧模型能力（Foundation Models 框架、WWDC 2026 的 Core AI/LLM provider API）面向**原生 App**而非 Web 标准。[来源：Apple 开发者资源检索](https://developer.apple.com/apple-intelligence)、[callstack WWDC26 复盘](https://www.callstack.com)（经搜索摘要核实）访问日期 2026-10-20【待核实：Safari 27 未发布 AI API 的确认需持续跟踪 webkit.org】
- 中间态参考：Mozilla Firefox 未提供内置 LLM API，但其翻译、PDF alt text 等端侧功能本质是"浏览器厂商用 WASM 跑开源小模型"——与页面级 WASM 方案同构。

### WebNN（W3C Web Machine Learning）现状

- 规范：W3C Web Machine Learning 工作组持续迭代，规范 2026-10 仍在更新（w3.org/TR/webnn）。[来源：W3C WebNN](https://www.w3.org/TR/webnn)、[GitHub webmachinelearning/webnn](https://github.com/webmachinelearning/webnn) 访问日期 2026-10-20
- Chrome 实现：**Chrome 146 起 WebNN 进入 origin trial**（Edge 同步）；chromestatus 功能页 5176273954144256 跟踪中。[来源：Phoronix Chrome 146 Beta 报道](https://www.phoronix.com/news/Chrome-146-Beta)、[chromestatus](https://chromestatus.com/feature/5176273954144256) 访问日期 2026-10-20；截至 2026-10 **尚未默认开启**（webnn.io 首页横幅仍为"Origin Trial 即将开始/进行"，onnxruntime-web 的 WebNN 后端也仍需 flag）【待核实：最新 OT 截止版本】
- 硬件后端：Windows ML/DirectML、Core ML、LiteRT；官方称 WebNN 是**"唯一能从 Web 访问 NPU 的 API"**。[来源：webnn.io](https://webnn.io/)、[Microsoft Learn WebNN Overview](https://learn.microsoft.com/en-us/windows/ai/directml/webnn-overview) 访问日期 2026-10-20
- 对 LLM 的意义：webnn-samples 已含 LLM 类 demo（Intel AI PC 开发者预览），transformers.js/onnxruntime-web/LiteRT.js 均计划/实验性支持 WebNN 后端；W3C 仓库在推进低精度数据类型（fp16/int8/4bit）、MLTensor、动态 shape 等对 LLM 友好的扩展。**但"WebNN 加速端侧 LLM"在 2026-10 仍处试验阶段，尚无生产可用证据**。[来源：GitHub webmachinelearning/webnn](https://github.com/webmachinelearning/webnn)、[webnn-samples](https://github.com/webmachinelearning/webnn-samples) 访问日期 2026-10-20

---

## ④ 对银行场景的价值与限制

### 价值（与银行内网 Web 应用场景的契合点）

1. **数据不出浏览器**：推理完全发生在页面/WASM 沙箱内，敏感材料（客户信息、授信文档、影像件）不必发往推理服务器，天然契合"数据不出域"的合规要求；WebLLM/wllama/transformers.js 均为纯本地计算。Firefox alt text 案例即以此为主要卖点（"Mozilla 无法接触用户的图片与 PDF"）。[来源：Mozilla Hacks](https://hacks.mozilla.org/2024/05/experimenting-with-local-alt-text-generation-in-firefox-nightly) 访问日期 2026-10-20
2. **免安装、零客户端运维**：以现有 B/S 内网应用为载体，员工浏览器即推理运行时；不需要在办公终端安装本地大模型客户端（ avoids 终端软件分发、杀白名单、版本管理成本）。WASM 二进制跨 Windows/macOS/信创终端一致运行。
3. **模型可完全内网分发**：模型权重是普通静态文件（MLC/GGUF/ONNX），可放行内网文件服务器/制品库；transformers.js 支持自定义模型路径（`env` 配置）；配合 Service Worker/Cache API/OPFS 缓存后可离线运行（WebLLM 官方支持 ServiceWorkerMLCEngine 与 PWA）。[来源：WebLLM README](https://github.com/mlc-ai/web-llm)、[transformers.js README](https://github.com/huggingface/transformers.js) 访问日期 2026-10-20
4. **合理的落地场景定位**（按性能边界倒推）：
   - 文档/影像的**本地预处理**：脱敏分类、版面理解、OCR 后处理、图片 alt text（Firefox 已验证的档位：~200MB、数秒/图）；
   - **浏览器内 RAG 辅助**：embedding（snowflake-arctic-embed 级，WebLLM/transformers.js 均支持）+ 向量检索 + 小 LLM（0.5B-3B）做制度问答草稿、表单预填；
   - **交互式助手的"降级兜底"**：云端/行内推理服务正常时走服务端，断网或涉密场景切浏览器内小模型，保证 Agent Harness 不中断。
5. **架构隔离性**：WASM 沙箱 + Web Worker 执行，模型代码不接触宿主文件系统（无 WASI 文件能力），攻击面比本地安装的推理进程小；wllama 等默认在 Worker 中推理，失败不影响主页面。

### 限制（必须写进内参的硬约束）

1. **内存天花板**：WASM32 线性内存上限 4GB（32-bit 索引），超出需尚未普及的 memory64 提案；浏览器对单 tab 内存另有实际上限（移动端更低）。这把浏览器内模型档位锁死在 ~8B q4 以内，KV cache 长上下文会进一步挤压。[来源：Stack Overflow（浏览器 WebAssembly.Memory 限制）](https://stackoverflow.com/questions/52406217/why-cant-i-construct-webassembly-memory-in-browsers)、[wasmtime memory64 issue](https://github.com/bytecodealliance/wasmtime/issues/11816) 访问日期 2026-10-20
2. **单文件 2GB 限制**（wllama 明示的 ArrayBuffer 约束，需分片绕过）；模型**首次下载体积大**：Llama-3.1-8B q4 权重约 4GB 级、Llama-3.2-1B 约 0.6-0.9GB——内网万兆到桌面问题不大，但首次加载等待（数十秒到分钟级）是产品体验硬伤，需预取/预装策略。[来源：wllama README](https://github.com/ngxson/wllama)、[WebLLM Issue #683](https://github.com/mlc-ai/web-llm/issues/683) 访问日期 2026-10-20
3. **无 NPU 访问**：页面 WASM/WebGPU 只能用 CPU/GPU；NPU（如 Copilot+ PC 的 40+ TOPS 算力）目前只有 WebNN（试验阶段）能触达，而原生运行时在同等硬件上 decode 可达 100+ tok/s——浏览器方案有数量级的算力浪费。[来源：webnn.io](https://webnn.io/)、[Google/LiteRT Qualcomm NPU 基准](https://developers.googleblog.com/unlocking-peak-performance-on-qualcomm-npu-with-litert) 访问日期 2026-10-20
4. **浏览器兼容矩阵复杂**：Firefox 无 WebGPU（2026-09 仍默认关闭）→ Firefox 只能 CPU 路线；Safari 26+ 才有 WebGPU 且 wllama 需兼容模式；多线程 WASM 需要全站配置 COOP/COEP 跨源隔离头——对遗留内网门户是真实的改造工作量。[来源：caniuse](https://caniuse.com/webgpu)、[wllama README](https://github.com/ngxson/wllama) 访问日期 2026-10-20
5. **模型能力上限**：浏览器内现实档位是 0.5B-8B 开源小模型（质量远低于行内旗舰模型），只适合辅助性任务；8B+ 模型在浏览器内的显存/内存占用（4-6GB 起）在办公终端（常配 8-16GB 内存、集显）上不稳。
6. **基准数据不足**：官方系统性基准只有 M3 Max 一档（论文），Windows GPU/信创 ARM 终端/Android 的公开数据为零，选型前需自测。【待核实】
7. **安全模型需要重新评估的点**：WASM 不解决模型本身的风险（prompt 注入、幻觉）；模型文件缓存在浏览器存储（IndexedDB/Cache）需纳入终端数据治理；行内统一浏览器版本策略直接决定 WebGPU 可用性。

### 银行/金融行业公开案例

- **结论：截至 2026-10-20，未检索到任何银行或金融机构公开的"浏览器内 WASM/WebGPU 大模型"生产部署案例**（中英文检索均无；最接近的是把 WebLLM 用于行业边缘 Agent 的学术论文与虚构演示）。
- 佐证材料（说明行业位置）：国内银行大模型规模化落地集中在服务端（工行"领航 AI+"600+ 场景、建行生成式 AI 600+ 场景，均为云端/行内服务器路线）；"金融+端侧 AI"产业论坛（2026-05）显示端侧赛道在金融尚属早期、80-90% 投资在云端。[来源：证券时报](https://www.stcn.com/article/detail/4192494.html)、[观察者网 2026-05-19](https://www.guancha.cn/GongSi/2026_05_19_817531.shtml) 访问日期 2026-10-20
- 可引用的"隔行"标杆只有 Firefox（浏览器厂商自用）与 WebML 社区 demo（DeepSeek-R1-Distill-Qwen-1.5B 全浏览器推理）。若内参需要行业对标，建议如实写"暂无同业公开案例，属前瞻布局项"。

---

## ⑤ 来源清单（全部于 2026-10-20 访问）

**官方一手来源**
1. WebLLM GitHub README/Releases/Issue #683（模型清单）：https://github.com/mlc-ai/web-llm 、https://github.com/mlc-ai/web-llm/releases 、https://github.com/mlc-ai/web-llm/issues/683
2. WebLLM 论文（M3 Max 基准）：Ruan et al., arXiv:2412.15803，https://arxiv.org/abs/2412.15803
3. MLC AI 官方博客（WebGPU 保留 85% 原生性能）：https://blog.mlc.ai/2024/06/13/webllm-a-high-performance-in-browser-llm-inference-engine
4. wllama GitHub README（2GB 限制、量化建议、WebGPU/兼容模式）：https://github.com/ngxson/wllama
5. transformers.js GitHub/npm/HF v3 博客（WebGPU 100x、dtype、模型生态）：https://github.com/huggingface/transformers.js 、https://registry.npmjs.org/@huggingface/transformers 、https://huggingface.co/blog/transformersjs-v3
6. onnxruntime-web（js/web README：四后端定位）：https://github.com/microsoft/onnxruntime/tree/main/js/web
7. llama.cpp WASM 构建讨论：https://github.com/ggml-org/llama.cpp/discussions/17237 ；llama-cpp-wasm：https://github.com/tangledgroup/llama-cpp-wasm ；Llamas on the Web：https://reeselevine.github.io/llamas-on-the-web
8. Chrome 官方文档 Prompt API（Gemini Nano、138 稳定、硬件门槛）：https://developer.chrome.com/docs/ai/prompt-api ；AI Language Model API：https://developer.chrome.com/docs/ai/language-model-api
9. WebKit 官方博客 Safari 26.0/26.2（WebGPU 正式启用）：https://webkit.org/blog/17333/webkit-features-in-safari-26-0 、https://webkit.org/blog/17640/webkit-features-for-safari-26-2 ；Apple 发布说明：https://developer.apple.com/documentation/safari-release-notes/safari-26-release-notes
10. W3C WebNN 规范与仓库：https://www.w3.org/TR/webnn 、https://github.com/webmachinelearning/webnn ；webnn.io：https://webnn.io/ ；webnn-samples：https://github.com/webmachinelearning/webnn-samples ；Microsoft Learn WebNN：https://learn.microsoft.com/en-us/windows/ai/directml/webnn-overview
11. Mozilla Hacks（Firefox 130 端侧 alt text）：https://hacks.mozilla.org/2024/05/experimenting-with-local-alt-text-generation-in-firefox-nightly ；Tarek Ziadé 博客（distilvit 训练复盘）：https://blog.ziade.org/2025/09/01/first-machine-learning
12. caniuse WebGPU（2026-09 覆盖率 87.82%）：https://caniuse.com/webgpu
13. WasmEdge WASI-NN LLM 文档 / LlamaEdge：https://wasmedge.org/docs/develop/rust/wasinn/llm_inference 、https://github.com/WasmAI/WasmEdge-LlamaEdge
14. Chrome 开发者博客（"生产 Web AI 多用 WASM"）：https://developer.chrome.com/blog/io24-webassembly-webgpu-1

**第三方/社区来源（数据需注明性质）**
15. Phoronix（Chrome 146 WebNN OT）：https://www.phoronix.com/news/Chrome-146-Beta ；chromestatus：https://chromestatus.com/feature/5176273954144256
16. mikeesto.com wllama vs transformers.js 实测（2026-05-26，非正式）：https://mikeesto.com/posts/wllama
17. Medium 浏览器 LLM 性能社区评测（1-2 tok/s 档）：https://medium.com/@hadiyolworld007/running-llms-in-the-browser-performance-or-fantasy-6c3464a1d197
18. dev.to WebLLM 0.2.83 Qwen3 实测：https://dev.to/creeta/qwen3-in-the-browser-zero-keys-webllm-0283-hands-on-3ai2 ；HF Space deepseek-r1-webgpu：https://huggingface.co/spaces/webml-community/deepseek-r1-webgpu
19. Google/LiteRT Qualcomm NPU 基准（对照用）：https://developers.googleblog.com/unlocking-peak-performance-on-qualcomm-npu-with-litert
20. DataDome（LanguageModel API Chrome 148 计划，2026-04）：https://datadome.co/threat-research/how-chromes-new-ai-web-apis-enable-hardware-fingerprinting
21. 银行业背景：证券时报 https://www.stcn.com/article/detail/4192494.html ；观察者网"金融+端侧 AI"论坛 https://www.guancha.cn/GongSi/2026_05_19_817531.shtml
22. WASM 内存限制：Stack Overflow https://stackoverflow.com/questions/52406217/why-cant-i-construct-webassembly-memory-in-browsers ；wasmtime memory64 https://github.com/bytecodealliance/wasmtime/issues/11816
