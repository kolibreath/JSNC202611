# 调研-02：端侧大模型的工具调用（Function Calling / Tool Use）与 Skill 配置支持现状

> 调研日期：2026-10-20 ｜ 调研人：研究员（ZCode）
> 范围：手机端（iOS / Android / 鸿蒙等）与浏览器端本地大模型的工具调用、结构化输出、Skill/MCP 配置能力；重点为 2025–2026 年官方原始信息。
> 方法：官方开发者文档、官方博客、GitHub 仓库为主，社区资料仅作辅助并标注。所有关键结论附来源与访问日期 2026-10-20；未能确认处标【待核实】。

---

## 一、各端侧模型 / 框架工具调用能力对照表

| 端侧方案 | 工具调用支持 | 结构化输出 | 备注 | 来源 |
|---|---|---|---|---|
| Apple Foundation Models（iOS 26 系统级 ~3B 端侧模型） | **原生支持**：`Tool` 协议（非 @Tool 宏）+ `LanguageModelSession`，三种 ToolCallingMode（allowed/required/disallowed） | **原生支持**：`@Generable` + `@Guide` 引导生成（token 级约束，保证合法 Swift 类型/JSON） | 官方支持 LoRA 适配器微调（Adapter Training Toolkit）；工具参数用 @Generable 约束生成 | [来源1.1](#11-apple) 访问日期 2026-10-20 |
| Google ML Kit GenAI APIs（Gemini Nano） | **不支持通用 function calling**：仅提供摘要、校对、改写、图像描述等预置 API | 部分预置 API 返回结构化结果 | 端侧通用 FC 需走 AI Edge 方案 | [来源1.2](#12-googleandroid) 访问日期 2026-10-20 |
| Google AI Edge / LiteRT-LM（Gemma 3n、FunctionGemma 等） | **支持**：官方 Function Calling 库（2025-05 上线 Android），LiteRT-LM 原生 tool use + 约束解码 | 支持（约束解码） | FunctionGemma（270M，2025-12）专做端侧函数调用；支持 iOS/Android/Web | [来源1.2](#12-googleandroid) 访问日期 2026-10-20 |
| Android 16 AppFunctions API | 系统级"App 即工具"接口（MCP 风格），非模型层 FC | 生成/返回结构化 schema | `@AppFunction` 注解 + schema 索引；Agent 侧当时为 Gemini 私人预览 | [来源1.2](#12-googleandroid) 访问日期 2026-10-20 |
| Chrome 内置 AI（Prompt API / AI Language Model APIs） | **无原生工具调用**；社区用"结构化输出 + 意图循环"自行实现 tool loop | **支持 JSON Schema 结构化输出**（Chrome 138+） | W3C Web Machine Learning 提案仍无 tools 参数 | [来源1.3](#13-chrome-浏览器端) 访问日期 2026-10-20 |
| Qwen3 全系（0.6B–235B） | **原生训练支持**：Hermes 风格模板（`<tool_call>` XML+JSON），官方推荐 | 模板层支持 | Qwen 官方文档明确 Qwen-Agent 为"canonical implementation" | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| Gemma 3 / 3n | **无原生工具调用模板**（模型卡与 chat template 均无工具标记，Ollama/GitHub 有大量讨论） | 需自行 prompt 工程 | 端侧官方路径：LiteRT-LM 的函数调用库 + FunctionGemma 路由 | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| Gemma 4（E2B/E4B 等，2026） | **原生支持**：chat template 内置专用 token（`<\|tool_call\|>call:`、`<\|tool_response\|>response:` 等），`apply_chat_template(tools=...)` | 支持 | 官方文档 2026-06-04 更新；LiteRT-LM 已支持 Gemma 4 | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| Llama 3.2 1B/3B | **官方支持**：系统提示内函数定义 + 自定义 tool call 格式两种方式 | 模板层支持 | 量化方案按 ExecuTorch Arm CPU 后端设计 | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| SmolLM3-3B | **支持**：chat template 支持工具消息（SmolTalk2 训练集含 function calling 数据，Qwen3-32B 蒸馏） | 支持 | 社区反馈过模板渲染 bug（2025-07 已修复，另有流式解析 issue） | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| MiniCPM5 1B/2B（OpenBMB） | **支持**：XML 风格工具调用，官方推荐 SGLang/vLLM 后端解析 | 模板层支持 | 另有历史版本 MiniCPM3-4B-FC 专用函数调用变体 | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| Hammer 2.1（0.5B/1.5B/3B/7B） | **专门做小模型函数调用**的模型族（MadeAgents），已上 BFCL 官方榜 | 模板层支持 | 面向端侧 agent；BFCL V4 有官方成绩 | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| xLAM-2（1B/3B fc-r，Salesforce） | 专用函数调用模型（Large Action Models） | 模板层支持 | xLAM-2-1b/3b 均在 BFCL V4 榜上 | [来源1.4](#14-开源模型层) 访问日期 2026-10-20 |
| llama.cpp（含 iOS/Android 移植） | **支持**：`--jinja` + 模型工具模板，OpenAI 兼容 `/v1/chat/completions` tools；多/并行调用可开启 | **支持**：GBNF 语法 + JSON Schema（`response_format`）约束解码 | 已知坑：thinking 与 grammar 同开时约束可能失效（issue #20345）；KV 量化损伤 FC 质量 | [来源1.5](#15-推理框架层) 访问日期 2026-10-20 |
| MNN / MNN-Chat（阿里） | 引擎具备模板渲染；官方 App README 现版仅明示 Qwen3.5/Qwen3 思考模式切换，未明示工具调用（早期版本曾标注支持 Qwen3 工具调用）【待核实：当前 App 是否内置 tool call】 | 引擎层支持 JSON 输出 | 社区有 Operit + MNN Tool Call 端侧实践 | [来源1.5](#15-推理框架层) 访问日期 2026-10-20 |
| MLC-LLM / WebLLM（浏览器） | OpenAI 兼容接口含 function calling（质量依赖具体模型，早期有兼容性 issue） | **强支持**：XGrammar 约束生成（JSON Schema / EBNF，WebAssembly 内实现），有官方 Playground | 浏览器端结构化输出最成熟方案之一 | [来源1.5](#15-推理框架层) 访问日期 2026-10-20 |
| ExecuTorch（PyTorch 官方端侧运行时） | Llama 3.2 1B/3B 官方移动端示例；Swift LLM 运行时支持 tool calling；上层 react-native-executorch v0.4.0（2025-05）内置 useLLM 工具调用（示例模型即 Hammer2.1-1.5B） | 模板层 | 依赖模型 chat template："只在模型 chat template 支持时生效" | [来源1.5](#15-推理框架层) 访问日期 2026-10-20 |

### 1.1 Apple

- **模型与能力**：Foundation Models 框架（iOS/iPadOS/macOS/visionOS 26+，watchOS 27+）暴露驱动 Apple Intelligence 的系统级端侧模型，官方技术报告称为"~3 billion parameter on-device language model"，iPhone 15 Pro 上首 token 延迟约 0.6ms/prompt token、生成约 30 tokens/s。[来源：Apple ML Research《Introducing Apple foundation models》](https://machinelearning.apple.com/research/introducing-apple-foundation-models)（访问日期 2026-10-20）
- **工具调用 API（纠错：官方是 `Tool` 协议，不存在官方 `@Tool` 宏）**：官方文档《Expanding generation with tool calling》：工具以遵循 `Tool` 协议的结构体定义（name、description、`@Generable` 参数结构，参数上用 `@Guide(description:, .range(...))` 描述与约束），`LanguageModelSession(tools: [...])` 注入；模型自主决定调用，支持并行多工具；`GenerationOptions.ToolCallingMode` 提供 `.allowed`（默认）/.required/.disallowed 三态，`.required` 必须设置退出条件（工具抛错或 DynamicProfile 动态切换），否则模型会持续调用；工具报错时框架可将 transcript 回滚到上一有效状态（`transcriptErrorHandlingPolicy`）。官方建议工具描述尽量短（描述占上下文且引入延迟）。[来源：Apple Developer Documentation](https://developer.apple.com/documentation/foundationmodels/expanding-generation-with-tool-calling)、[Tool 协议](https://developer.apple.com/documentation/foundationmodels/tool)（访问日期 2026-10-20）
- **引导生成/结构化输出**：`@Generable` 宏 + `@Guide`（描述、范围约束）+ 正则，token 级约束保证输出为合法 Swift 类型实例，工具参数解析同样走引导生成（同上来源；另见 WWDC25 Session 286/301）。
- **LoRA 微调（官方支持，条件严格）**：官方 Adapter Training 页面：适配器即 LoRA，导出 `.fmadapter` 包；每个适配器约 160MB，基础任务需 100–1000 条、复杂任务 5000+ 条数据；需申请 Foundation Models Framework Adapter Entitlement；适配器需经 Background Assets 从服务器下发，且"每个适配器只兼容单一系统模型版本"；Toolkit 26.0.0 为最后一版，仅支持 OS 26 系（不支持 OS 27+）。官方同时提示："在考虑适配器之前，先通过提示工程或工具调用榨干系统模型能力。"[来源：Apple Developer《Foundation Models adapter training》](https://developer.apple.com/apple-intelligence/foundation-models-adapter)（访问日期 2026-10-20）
- **与 App Intents/Siri 的编排**：App Intents（含 Assistant Schemas）是把 App 能力接入 Siri/Apple Intelligence/Spotlight 的官方通道；Foundation Models 的 `Tool` 协议用于 App 内会话级工具，两者是并行体系。[来源：Apple Developer《What's new — Apple Intelligence》](https://developer.apple.com/apple-intelligence/whats-new)、[第三方综述](https://blakecrosley.com/blog/app-intents-are-apples-new-api-to-your-app)（访问日期 2026-10-20）

### 1.2 Google / Android

- **ML Kit GenAI APIs（Gemini Nano）**：2025-05 上线，提供端侧摘要、校对、改写、图像描述/实时描述等**预置 API，未开放通用 function calling**；云上函数调用在 Gemini API 侧。[来源：ML Kit GenAI 概览](https://developers.google.com/ml-kit/genai)、[Android Developers Blog 2025-05](https://android-developers.googleblog.com/2025/05/on-device-gen-ai-apis-ml-kit-gemini-nano.html)、[InfoQ 报道](https://www.infoq.com/news/2025/06/google-mlkit-genai-gemini-nano)（访问日期 2026-10-20）
- **AI Edge SDK / LiteRT-LM / Galaxi**：2025-05-20 Google 开发者博客发布"端侧 SLM：多模态 + RAG + Function Calling"，**AI Edge Function Calling 库**当日上线 Android（后续跨 iOS/Web），配合 Gemma 3n 等端侧模型做多模态 RAG 与工具调用。[来源：Google Developers Blog](https://developers.googleblog.com/google-ai-edge-small-language-models-multimodality-rag-function-calling)（访问日期 2026-10-20）LiteRT-LM 官方文档（2026-10-06 更新）明确列出能力："**Tool Use: Function calling support for agentic workflows with constrained decoding for improved accuracy**"，支持模型含 Gemma 4（E2B/E4B）、Gemma 3n、Gemma 3 1B、FunctionGemma、phi-4-mini、Qwen2.5、Qwen3-0.6B 等，覆盖 Android/iOS/macOS/Windows/CLI。[来源：LiteRT-LM Overview](https://developers.google.com/edge/litert-lm/overview)（访问日期 2026-10-20）
- **FunctionGemma**：2025-12 发布，基于 Gemma 3 270M 专门调优的函数调用小模型（作为路由/微调底座），int8 仅约 288MB，官方 GDE 文章称 Hammer2.1-1.5B 约 73% vs FunctionGemma 更小但开箱分数更低（面向微调）。[来源：FunctionGemma 文档](https://ai.google.dev/gemma/docs/functiongemma)、[GDE 文章](https://medium.com/google-developer-experts/on-device-function-calling-with-functiongemma-39f7407e5d83)（访问日期 2026-10-20）
- **Android 16 App Functions API**：官方文档（2026-09-08 更新）："AppFunctions 让 App 向 AI Agent 暴露工具，**类似 MCP**"；以 `@AppFunction` 注解 Kotlin 函数、生成结构化 schema，安装时由系统 schema 索引；执行需持有 `android.permission.EXECUTE_APP_FUNCTIONS`；官方称该 API 将"随 Android 版本与设备扩展"，且当时的调用方（如 Gemini）尚处**私人预览**。[来源：AppFunctions 概览](https://developer.android.com/ai/appfunctions)、[官方示例库](https://github.com/android/appfunctions)、[Android Developers Blog 2026-07](https://android-developers.googleblog.com/2026/07/build-intelligent-android-apps-appfunctions.html)（访问日期 2026-10-20）

### 1.3 Chrome（浏览器端）

- Prompt API 支持 **JSON Schema 结构化输出**（`response_format`，Chrome 138+ 稳定可用），但**没有原生工具调用**；社区通行做法是"结构化输出解析意图 + 自行分发到 JS 函数"的意图循环。[来源：Chrome for Developers《Structured output support for the Prompt API》](https://developer.chrome.com/docs/ai/structured-output-for-prompt-api)、[Prompt API](https://developer.chrome.com/docs/ai/prompt-api)、[W3C webmachinelearning/prompt-api](https://github.com/webmachinelearning/prompt-api)、[社区教程](https://danduh.me/courses/chrome-built-in-ai/structured-output-and-tools)（访问日期 2026-10-20）
- 浏览器端若需完整工具调用，成熟路径是 **WebLLM**（见 1.5）而非 Chrome 内置 AI。【待核实：Chrome AI 后续版本是否新增 tools 参数——截至本调研日未见官方文档】

### 1.4 开源模型层

- **Qwen3（阿里）**：官方文档："**We recommend using Hermes-style tool use for Qwen3 to maximize function calling performance**"，模板输出 `<tool_call>` XML+JSON；Qwen-Agent 是"canonical implementation"，vLLM（≥0.8.5）用 `--enable-auto-tool-choice --tool-call-parser hermes`；官方同时警告函数调用本质是提示工程，"不保证模型生成永远遵循协议"，生产需处理畸形输出。全系列（含 0.6B/1.7B/4B）均按此训练。[来源：Qwen 官方 Function Calling 文档](https://qwen.readthedocs.io/en/latest/framework/function_call.html)、[QwenLM/Qwen-Agent](https://github.com/QwenLM/qwen-agent)（访问日期 2026-10-20）。注：检索未见名为"Qwen Orchestrator"的开源模型；2025–2026 阿里侧新的 agent 编排相关开源仍以 Qwen-Agent / Qwen Code（CLI，MCP 集成）为主【待核实：是否有新命名的 orchestrator 模型】。[来源：Qwen Code](https://qwen.ai/qwencode)（访问日期 2026-10-20）
- **Gemma 3 / 3n**：模型卡与 chat 模板**无工具调用标记**，社区（Ollama issue、HF discussion）与 Gemma 团队成员均确认 Gemma 3 系无原生 FC 格式，需提示工程或走 LiteRT-LM 的函数调用库（约束解码）。[来源：Ollama issue #9680](https://github.com/ollama/ollama/issues/9680)、[HF discussion](https://huggingface.co/google/gemma-3-27b-it/discussions/24)（访问日期 2026-10-20）
- **Gemma 4（2026）**：官方文档（2026-06-04 更新）给出**原生函数调用模板**：`<|tool>declaration:`（注入工具定义）、`<|tool_call>call:`（发起调用）、`<|tool_response>response:`（返回结果）等专用 token，经 `apply_chat_template(tools=...)` 使用，并与 thinking 模式联动；LiteRT-LM 已支持 Gemma 4 E2B/E4B。[来源：Function calling with Gemma 4](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)、[LiteRT-LM](https://developers.google.com/edge/litert-lm/overview)（访问日期 2026-10-20）
- **Llama 3.2 1B/3B**：Meta 官方模型卡与提示格式文档确认支持工具调用（两种方式：系统提示内函数定义、自定义 tool call 格式）；HF 模型卡注明量化方案"以 PyTorch ExecuTorch（Arm CPU 后端）为目标设计"。[来源：Meta Llama 3.2 prompt formats](https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats/llama3_2)、[HF meta-llama/Llama-3.2-1B](https://huggingface.co/meta-llama/Llama-3.2-1B)（访问日期 2026-10-20）
- **SmolLM3-3B（HF）**：官方博客明确"SmolLM3 supports tool calling"，训练后数据 SmolTalk2 含函数调用数据（Qwen3-32B 合成）；社区先后报告 chat template 工具渲染 bug（2025-07 修复）与流式工具参数截断 issue。[来源：HF 博客](https://huggingface.co/blog/smollm3)、[模型卡](https://huggingface.co/HuggingFaceTB/SmolLM3-3B)、[讨论 #44](https://huggingface.co/HuggingFaceTB/SmolLM3-3B/discussions/44)（访问日期 2026-10-20）
- **MiniCPM（OpenBMB）**：官方仓库：MiniCPM5（1B/2B）"emits XML-style tool calls"，端侧助手/编码 agent 定位，FC 推荐 SGLang（或 vLLM）后端；早期另有 MiniCPM3-4B-FC 专用函数调用变体（在 BFCL 榜）。[来源：OpenBMB/MiniCPM](https://github.com/openbmb/minicpm)、[HF 讨论](https://huggingface.co/openbmb/MiniCPM5-1B/discussions/7)（访问日期 2026-10-20）
- **Hammer（MadeAgents）**：定位"robust function-calling for on-device LMs"，0.5B/1.5B/3B/7B 全家桶，已进入 BFCL 官方榜（CHANGELOG 记录 Hammer2.1 各尺寸）。[来源：MadeAgents/Hammer](https://github.com/MadeAgents/Hammer)、[BFCL CHANGELOG](https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/CHANGELOG.md)（访问日期 2026-10-20）
- **xLAM（Salesforce）**：Large Action Models，专做函数调用/规划；xLAM-1b-fc-r 曾号称超 GPT-3.5-Turbo 函数调用精度；新一代 xLAM-2（1b/3b fc-r）在 BFCL V4 榜上。[来源：Salesforce 博客](https://www.salesforce.com/blog/large-action-model-ai-agent)、[SalesforceAIResearch/xLAM](https://github.com/SalesforceAIResearch/xLAM)（访问日期 2026-10-20）

### 1.5 推理框架层

- **llama.cpp**：官方文档《function-calling.md》：`llama-server --jinja` 启用 Jinja 模板引擎后即可用 OpenAI 兼容 `/v1/chat/completions` 的 `tools`/`tool_choice`；模板需含工具块（可用 `/props` 查 `chat_template_tool_use`）；原生支持 Llama 3.1/3.2/3.3、Functionary、Hermes 2/3、Qwen 2.5/Qwen（含 Qwen3 系 Hermes 格式）、Mistral Nemo、Command R7B、GPT-OSS 等格式，未识别模板时走"Generic tool call"（更耗 token）；并行工具调用默认关闭（`parallel_tool_calls: true` 开启）；文档警告极端 KV 量化会明显劣化工具调用质量。结构化输出另有 GBNF 语法与 JSON Schema（`response_format`）约束解码（structured outputs 文档）；已知缺陷：`enable_thinking: true` 与 JSON schema 约束同开时 grammar 可能完全不生效（issue #20345，2026-03）。[来源：llama.cpp function-calling.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)、[grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)、[issue #20345](https://github.com/ggml-org/llama.cpp/issues/20345)（访问日期 2026-10-20）
- **MNN / MNN-Chat（阿里）**：官方 App（Android/iOS）README（现版）列明支持 Qwen3.5/Qwen3 思考模式切换等，**未再明示 tool call**（2025 年中版本 README 曾有"支持 Qwen3 工具调用"表述）【待核实】；社区有 Operit 接入 MNN Tool Call、Qwen3-0.6B 骁龙 cDSP + MNN 工具调用等实践；MNN 引擎层具备 chat template 渲染与 JSON 输出能力。[来源：alibaba/MNN MnnLlmChat](https://github.com/alibaba/MNN/tree/master/apps/Android/MnnLlmChat)、[社区实践](https://blog.csdn.net/gitblog_00579/article/details/162692082)（访问日期 2026-10-20）
- **MLC-LLM / WebLLM**：WebLLM README："supports state-of-the-art JSON mode structured generation, implemented in the WebAssembly portion of the model library"；底层为 XGrammar（JSON/SQL/EBNF 跨平台约束生成）；提供 OpenAI 兼容接口（含 function calling，早期有流式工具调用兼容性问题，质量依赖具体模型）；官方有 Structured Generation Playground。[来源：mlc-ai/web-llm](https://github.com/mlc-ai/web-llm)、[XGrammar 博客](https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar)、[issue #462](https://github.com/mlc-ai/web-llm/issues/462)（访问日期 2026-10-20）
- **ExecuTorch（PyTorch）**：官方示例支持 Llama 3.2 1B/3B 移动端运行（XNNPACK + 4bit 量化；另有 Vulkan/QNN 后端教程）；Swift LLM 运行时支持 tool calling（Swift Package Index 功能页注明）；上层封装 react-native-executorch 自 v0.4.0（2025-05）在 useLLM 提供 `toolsConfig`（tools / executeToolCallback / displayToolCalls），文档明确"**仅在模型 chat template 支持时生效**"，示例模型即 Hammer2.1-1.5B，支持模型表含 Hammer 2.1、Qwen 2.5/3、Phi-4-mini、SmolLM 2、Llama 3.2。[来源：ExecuTorch Llama 示例](https://github.com/pytorch/executorch/blob/main/examples/models/llama/README.md)、[useLLM 文档](https://docs.swmansion.com/react-native-executorch/docs/0.5.x/hooks/natural-language-processing/useLLM)、[v0.4.0 发布公告](https://x.com/swmansion/status/1924840799767781394)（访问日期 2026-10-20）

---

## 二、端侧 Agent Harness / MCP / Skill 生态现状

1. **MCP 官方 SDK 的移动可用性**：MCP 官方提供 Kotlin Multiplatform SDK（与 JetBrains 合作，JVM/Native/JS/Wasm，可上 Android）与 Swift SDK（Apple 平台），均列入官方 SDK 分层目录。即"手机上跑 MCP 客户端/服务端"在协议层已无障碍。[来源：MCP SDKs](https://modelcontextprotocol.io/docs/2026-07-28/sdk)、[kotlin-sdk](https://github.com/modelcontextprotocol/kotlin-sdk)（访问日期 2026-10-20）
2. **极简 agent 循环（可平移到端侧）**：HuggingFace Tiny Agents（2025-04）：Node/Python 各约 50/70 行实现 MCP 驱动的 agent 循环（llama-cpp-agent + mcp adapter + OpenAI 兼容模板），本身是桌面/本地示例而非手机框架，但架构（本地推理 + MCP 工具循环）可直接平移到端侧。[来源：HF 博客](https://huggingface.co/blog/tiny-agents)（访问日期 2026-10-20）
3. **llama.cpp 系端侧 agent 编排**：IonClaw（2026-06-01 发布，独立开发者 paulocoutinhox，非 llama.cpp 官方团队）：纯 C++ Agent 编排器，基于 llama.cpp 本地 GGUF 模型，宣称运行于 iOS/Android/watchOS/macOS/Windows/Linux/树莓派，含工具/技能系统、Skills Marketplace、多 agent 沙箱编排、MCP client+server 双角色；早期测试者阶段，成熟度低。[来源：llama.cpp Discussions #23985](https://github.com/ggml-org/llama.cpp/discussions/23985)（访问日期 2026-10-20）
4. **"Skill 文件"范式的端侧进展**：
   - Anthropic Agent Skills（2025-10-16 发布，SKILL.md 文件夹 = 元数据+指令+脚本，按需加载）于 2025-12-18 发布为**跨平台开放标准**（agentskills.io），任何 agent 框架可采纳；检索未见官方 iOS/Android 运行时，但"文件夹即技能、渐进披露"的格式与端侧无绑定，IonClaw 等端侧项目已实现类似 Skills 机制。[来源：Anthropic 工程博客](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)、[agentskills.io](https://agentskills.io)（访问日期 2026-10-20）
   - OpenAI AgentKit（2025-10-06 DevDay）：可视化 Agent Builder/Evals/RFT，云端产品，**无端侧移植**；官方平台公告显示部分组件 2026-11-30 后下线调整。[来源：OpenAI](https://openai.com/index/introducing-agentkit)（访问日期 2026-10-20）
5. **手机厂商官方"智能体编排"平台（给端侧/端云模型配工具的方式）**：
   - **Apple**：App Intents + Assistant Schemas（Siri/Spotlight/Apple Intelligence 的 App 能力暴露层）；App 内会话用 Foundation Models `Tool` 协议。[来源：Apple Developer](https://developer.apple.com/apple-intelligence/whats-new)（访问日期 2026-10-20）
   - **Google**：Android 16 AppFunctions（`@AppFunction` 注解、schema 索引、执行权限，MCP 风格，Agent 侧 Gemini 私人预览）。[来源：developer.android.com/ai/appfunctions](https://developer.android.com/ai/appfunctions)（访问日期 2026-10-20）
   - **华为（鸿蒙）**：小艺开放平台 = 意图框架 + AI 大模型能力开放；HarmonyOS 7 向 Agent 架构演进，鸿蒙智能体框架 HMAF 2.0，端云协同（隐私敏感/高响应走端侧）；开放端侧 A2A 接入与端侧操控、A2UI 协议。[来源：小艺开放平台](https://developer.huawei.com/consumer/cn/celia)、[Harmony Intelligence 开放能力](https://developer.huawei.com/consumer/cn/harmonyos-ai)（访问日期 2026-10-20）
   - **vivo（蓝心）**：2026-09-16 官宣蓝心智能开放平台升级，"支持智能体（Agent）、Skill、MCP 及原子技能快速接入，并全面开放**端侧推理与训练引擎**"；蓝心智能体平台提供插件、知识库、工作流、"手机端侧技能"等工具；端侧模型矩阵 1B/3B（专为端侧 Agent 构建的 3B）至预研 30B MoE。注：vivo 的智能体品牌是"蓝心小V"，YOYO 是荣耀的智能体。[来源：vivo 官网新闻](https://www.vivo.com.cn/brand/news/detail?id=1389&type=0)、[蓝心智能体文档](https://developers.vivo.com/doc/d/Qy9PZS9mbXNJWTc5VGw1WTBXckZTZz09)、[新华网](http://www.xinhuanet.com/tech/20251011/6851b4c02058429880686885d9b0b2d7/c.html)（访问日期 2026-10-20）
   - **荣耀（YOYO）**：YOYO 智能体 = MagicOS 核心 AI 助手，引导式对话 + 意图识别 + 跨 App 自动操作；HGDC 2025（2025-10-23）上线一站式智能体开放平台，开放 **MCP 协议接入**；阿尔法计划目标 2025 年接入 300+ MCP 服务、2026 年 2000+ MCP 服务，打造"通用端侧智能体"。[来源：荣耀开发者平台](https://developer.honor.com/cn/doc/guides/101692)、[中国日报](http://ex.chinadaily.com.cn/exchange/partners/82/rss/channel/cn/columns/sz8srm/stories/WS68fe033ba310c4deea5ee414.html)、[荣耀官网](https://www.honor.com/cn/news/honor-ai-device-expo)（访问日期 2026-10-20）

---

## 三、小模型工具调用效果证据

### 3.1 Berkeley Function Calling Leaderboard（BFCL）V4

BFCL 已升级至 **V4**（页面标注 Last updated 2026-04-12，评测代码 bfcl-eval==2025.12.17），在 V3 多轮基础上加入 agentic（网页搜索、KV/向量/递归摘要记忆）、幻觉测量、格式敏感性等维度；页面图例明确："FC = native support for function/tool calling；Prompt = walk-around using text generation"（Gemma 3 系在榜上仅有 Prompt 模式，佐证其无原生 FC 模板）。**Overall Accuracy 为全部子类非加权平均，绝对值显著低于 V3 时代榜单，与 2025 年旧闻中"70%+"不可直接比较。**[来源：BFCL V4 榜单](https://gorilla.cs.berkeley.edu/leaderboard.html)（访问日期 2026-10-20）

≤4B 端侧量级模型 Overall Accuracy（FC = 原生函数调用模式）：

| 模型（模式） | Overall Acc | 备注 |
|---|---|---|
| **Nanbeige4-3B-Thinking-2511（FC）** | **51.40** | ≤4B 最佳，总榜第 25 |
| xLAM-2-3b-fc-r（FC，Salesforce） | 41.22 | 专用 FC 模型 |
| Qwen3-4B-Instruct-2507（FC） | 35.68 | Prompt 模式 35.52 |
| Arch-Agent-3B（FC） | 35.36 | katanemo |
| Qwen3-4B（FC） | 34.54 | |
| Hammer2.1-7b（FC） | 31.67 | 超过 4B 仅作参照 |
| xLAM-2-1b-fc-r（FC） | 30.44 | |
| Hammer2.1-3b（FC） | 29.71 | |
| Qwen3-1.7B（FC） | 28.41 | |
| Hammer2.1-1.5b（FC） | 27.88 | GDE 文章称其旧口径约 73% |
| MiniCPM3-4B-FC（FC） | 25.55 | OpenBMB 专用 FC 变体 |
| Qwen3-0.6B（FC） | 23.93 | |
| Hammer2.1-0.5b（FC） | 21.22 | |
| Llama-3.2-3B-Instruct（FC） | 21.95 | |
| Gemma-3-4b-it（Prompt） | 19.62 | 无 FC 模式 |
| Granite-4.0-350m（FC） | 18.98 | |
| Llama-3.2-1B-Instruct（FC） | 10.82 | |
| Gemma-3-1b-it（Prompt） | 7.17 | 无 FC 模式 |

参照系（总榜头部）：Claude-Opus-4.5（FC）77.47、GLM-4.6（FC）72.38、Gemini-3.1-Pro（FC）64.92、GPT-5.2（FC）55.87；云端小模型 Gemini-2.5-Flash-Lite（FC）36.87、Qwen3-8B（FC）42.57、Qwen3-30B-A3B（FC）41.39。同榜可见：**最好的端侧 3B（51.40）已接近 GPT-5.2（55.87）的八成水平，但距头部云端模型（77+）仍差 26 分。**[来源：BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard.html)（访问日期 2026-10-20）

子项观察（列映射以官网表格为准）：小模型的 **agentic（网页搜索/记忆）子项普遍接近 0 分**（如 Qwen3-4B-Instruct-2507、Llama-3.2-3B 搜索/记忆子项 0–10 分量级），**多轮子项显著低于单轮子项**（如 Qwen3-4B-Instruct-2507 多轮约 23 分 vs 单轮 53–65 分量级；Llama-3.2-3B 多轮约 12 分量级）——即端侧小模型"单轮结构化调用可用、多轮编排与真实环境 agentic 任务仍很弱"。[来源：BFCL V4 明细](https://gorilla.cs.berkeley.edu/leaderboard.html)（访问日期 2026-10-20）

### 3.2 多轮 / Agent 评测中的小模型数据

- BFCL V3（2024-09 引入多轮）有 Hammer、Qwen3-4B 等小模型成绩，但 V4 已重构口径，旧分数参考价值下降。[来源：BFCL V3 博客](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html)（访问日期 2026-10-20）
- **τ-bench / τ²-bench：未检索到 ≤4B 端侧模型的公开可比数据**（Artificial Analysis 的 τ²-Bench Telecom 榜与 Sierra 官方榜均以云端大模型为主）。结论：截至本调研日，端侧 3B–4B 模型在 τ-bench 类真实多轮客服/工具任务上的公开证据缺失，属于明显的数据空白。[来源：τ²-bench](https://github.com/sierra-research/tau2-bench)、[Artificial Analysis](https://artificialanalysis.ai/evaluations/tau2-bench)（访问日期 2026-10-20）

---

## 四、技术路线图与成熟度评估

**路线 A：厂商原生框架 API（系统集成度最高，银行 App 受限于平台准入）**
- Apple Foundation Models + Tool 协议/@Generable 引导生成：工具调用与结构化输出由系统保证（token 级约束），支持 LoRA 特化；限制：仅 Apple Intelligence 机型、模型固定 ~3B、无法换模型、适配器需逐系统版本重训。**成熟度：单轮/受控多轮工具调用——生产可用（iOS 26 生态内）；复杂编排仍需 App 自建循环。**
- Google AI Edge / LiteRT-LM + Function Calling 库（Gemma 3n / Gemma 4 / FunctionGemma）：Android/iOS/Web 跨平台，约束解码保证参数合法；ML Kit GenAI 不含通用 FC 属于能力分层而非缺失。**成熟度：可用，生态较新（2025-05 起步）。**
- Chrome 内置 AI：仅结构化输出，无原生 FC。**成熟度：工具调用需自行实现意图循环（demo 级）。**

**路线 B：开源模型 + 模板 + 约束解码（自主可控，银行业最可能采用）**
- 组合：Qwen3 / Qwen3-4B-Instruct-2507 / Hammer2.1 / xLAM-2 / MiniCPM5（模型层，Hermes/XML 模板原生训练） + llama.cpp --jinja 或 LiteRT-LM 或 MLC/WebLLM（推理层，模板解析 + GBNF/JSON Schema/XGrammar 约束解码）。**成熟度：单轮函数调用工程上成熟（多框架互认 Hermes 格式）；坑：模板不一致、thinking 与 grammar 冲突、KV 量化劣化、流式解析 bug，均需工程兜底。**
- 专用小 FC 模型（Hammer/xLAM-2/FunctionGemma/MiniCPM-FC）适合做"端侧路由器/调度器"：小模型出调用决策，重活交云端或本地大模型。

**路线 C：端侧 harness 自行解析（提示工程 + 结构化输出 + 手写循环）**
- 适用：Chrome Prompt API、Gemma 3n 等无原生模板的场景；以及把 MCP（Kotlin/Swift SDK）、Agent Skills 开放标准（SKILL.md）、A2A 等生态接入端侧时。**成熟度：原型/演示级，工程量大、鲁棒性差，仅建议窄域（如行内固定 5–10 个工具）使用。**

**平台工具层（给"系统智能体"供工具，与模型层正交）**：App Intents（Apple）、AppFunctions（Android 16，MCP 风格、Agent 侧预览）、小艺意图框架/A2A/A2UI（华为）、蓝心 Agent/Skill/MCP（vivo，开放端侧推理与训练引擎）、YOYO 智能体平台（荣耀，开放 MCP 接入）。银行 App 的正确姿势是"把自己的服务注册为平台级工具/skill"，无论端侧模型归属厂商还是自研。

**总体判断**：2025–2026 年，端侧工具调用已从"提示工程技巧"收敛为三类标准化接口（系统框架 API、模型模板、约束解码）；单轮结构化工具调用在 3–4B 级已可用（专用 FC 模型更稳），多轮编排与 agentic 任务在端侧仍明显不可靠（BFCL V4 子项与 τ-bench 数据空白双重印证）。端侧 skill 配置方面，MCP 协议层已具备移动 SDK，SKILL.md 已开放标准化，但"跑在手机上的成熟 agent harness"仍处早期（IonClaw 等为社区项目，厂商平台为私人预览/灰度）。

---

## 五、来源清单（均为 2026-10-20 访问）

**Apple**
1. Expanding generation with tool calling — https://developer.apple.com/documentation/foundationmodels/expanding-generation-with-tool-calling
2. Tool 协议 — https://developer.apple.com/documentation/foundationmodels/tool（及 .md 版）
3. Foundation Models adapter training — https://developer.apple.com/apple-intelligence/foundation-models-adapter
4. Introducing Apple foundation models — https://machinelearning.apple.com/research/introducing-apple-foundation-models
5. WWDC25 Session 286 / 301 — https://developer.apple.com/videos/play/wwdc2025/286 、/301
6. What's new — Apple Intelligence — https://developer.apple.com/apple-intelligence/whats-new

**Google / Android / Chrome**
7. ML Kit GenAI 概览 — https://developers.google.com/ml-kit/genai
8. On-device GenAI APIs（Android 官方博客 2025-05）— https://android-developers.googleblog.com/2025/05/on-device-gen-ai-apis-ml-kit-gemini-nano.html
9. On-device SLMs with multimodality, RAG, and Function Calling（2025-05-20）— https://developers.googleblog.com/google-ai-edge-small-language-models-multimodality-rag-function-calling
10. LiteRT-LM Overview — https://developers.google.com/edge/litert-lm/overview
11. FunctionGemma — https://ai.google.dev/gemma/docs/functiongemma
12. Function calling with Gemma 4 — https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4
13. AppFunctions 概览 — https://developer.android.com/ai/appfunctions ；示例 https://github.com/android/appfunctions ；博客 https://android-developers.googleblog.com/2026/07/build-intelligent-android-apps-appfunctions.html
14. Chrome Structured output for the Prompt API — https://developer.chrome.com/docs/ai/structured-output-for-prompt-api
15. W3C webmachinelearning/prompt-api — https://github.com/webmachinelearning/prompt-api

**开源模型**
16. Qwen Function Calling 官方文档 — https://qwen.readthedocs.io/en/latest/framework/function_call.html
17. QwenLM/Qwen-Agent — https://github.com/QwenLM/qwen-agent
18. Meta Llama 3.2 模型卡/提示格式 — https://dev.meta.ai/llama/docs/model-cards-and-prompt-formats/llama3_2 ；HF https://huggingface.co/meta-llama/Llama-3.2-1B
19. Gemma 3 无原生 FC 的讨论 — https://github.com/ollama/ollama/issues/9680
20. SmolLM3 博客/模型卡 — https://huggingface.co/blog/smollm3 ；https://huggingface.co/HuggingFaceTB/SmolLM3-3B
21. OpenBMB/MiniCPM — https://github.com/openbmb/minicpm
22. MadeAgents/Hammer — https://github.com/MadeAgents/Hammer
23. Salesforce xLAM — https://github.com/SalesforceAIResearch/xLAM ；https://www.salesforce.com/blog/large-action-model-ai-agent

**推理框架**
24. llama.cpp function-calling.md — https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md
25. llama.cpp grammars/README.md（GBNF）— https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md
26. llama.cpp issue #20345（thinking+grammar）— https://github.com/ggml-org/llama.cpp/issues/20345
27. alibaba/MNN MnnLlmChat — https://github.com/alibaba/MNN/tree/master/apps/Android/MnnLlmChat
28. mlc-ai/web-llm — https://github.com/mlc-ai/web-llm ；XGrammar https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar
29. ExecuTorch Llama 示例 — https://github.com/pytorch/executorch/blob/main/examples/models/llama/README.md
30. react-native-executorch useLLM（0.5.x 文档）— https://docs.swmansion.com/react-native-executorch/docs/0.5.x/hooks/natural-language-processing/useLLM ；v0.4.0 公告 https://x.com/swmansion/status/1924840799767781394

**Harness / MCP / Skill / 厂商平台**
31. MCP SDKs — https://modelcontextprotocol.io/docs/2026-07-28/sdk ；kotlin-sdk https://github.com/modelcontextprotocol/kotlin-sdk
32. HF Tiny Agents — https://huggingface.co/blog/tiny-agents
33. IonClaw（llama.cpp Discussions #23985）— https://github.com/ggml-org/llama.cpp/discussions/23985
34. Anthropic Agent Skills — https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills ；开放标准 https://agentskills.io
35. OpenAI AgentKit — https://openai.com/index/introducing-agentkit
36. 华为小艺开放平台 — https://developer.huawei.com/consumer/cn/celia ；Harmony Intelligence — https://developer.huawei.com/consumer/cn/harmonyos-ai
37. vivo 蓝心智能开放平台（2026-09-16）— https://www.vivo.com.cn/brand/news/detail?id=1389&type=0 ；蓝心智能体文档 https://developers.vivo.com/doc/d/Qy9PZS9mbXNJWTc5VGw1WTBXckZTZz09
38. 荣耀 YOYO 智能体 — https://developer.honor.com/cn/doc/guides/101692 ；HGDC2025 报道 http://ex.chinadaily.com.cn/exchange/partners/82/rss/channel/cn/columns/sz8srm/stories/WS68fe033ba310c4deea5ee414.html ；荣耀 AI 终端 https://www.honor.com/cn/news/honor-ai-device-expo

**评测**
39. BFCL V4 榜单（2026-04-12 更新）— https://gorilla.cs.berkeley.edu/leaderboard.html
40. BFCL V3 多轮博客 — https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html
41. τ²-bench — https://github.com/sierra-research/tau2-bench ；Artificial Analysis τ²-Bench https://artificialanalysis.ai/evaluations/tau2-bench

**待核实清单**
- MNN-Chat 当前版本 App 是否内置工具调用 UI/解析（早期 README 曾标注，现行 README 未提）。
- Chrome 内置 AI 是否在 138 之后版本新增原生 tools 参数（截至调研日未见）。
- "Qwen Orchestrator" 是否为真实存在的开源模型/框架名（检索未见，疑为口径误差）。
- AppFunctions 的第三方 Agent 调用（Gemini 之外）开放时间表。
- Apple Foundation Models 是否在 OS 27 周期开放适配器工具包新版本（26.0.0 为最后一版）。
