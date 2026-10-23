# 开发日志（W1–W2 任务板）

> 按设计文档 4.2.2 推进；每完成一项打勾并把坑记录追加到文末。

## W1

- [ ] D1–D2 设备初始化（见 device-setup.md）；MNN 源码拉取 + Docker 交叉编译
      通过标准：设备 `llm_demo` 跑通 Qwen3-1.7B 单轮对话
- [ ] D3 模型转换（1.7B / 4B-2507 → MNN int4）+ tokenizer 对齐校验（models/verify_tokenizer.py）
      通过标准：5 条样例与 PC 端 transformers 输出逐 token 一致
- [ ] D4 **CLI 常驻改造**（关键工程点，三选一，D2 末决策）：
      - 方案 A：改 MNN llm_demo 支持 `--file prompts.jsonl` 一次加载批量处理（推荐，改动小）
      - 方案 B：stdin 管道逐条喂入
      - 方案 C：放弃改造，切备链路 Termux + llama-server（OpenAI 兼容接口）
      通过标准：一条命令处理 50 条 jsonl 并逐条输出结果
      ※ 备链路 C 已在真机（一加 Ace 2 / Termux）提前跑通，见 docs/评测记录/
- [x] D5 adapter 打通 + 意图注册表 + intent.j2 模板（2026-10-22）
- [x] D6–D7 mask/faq/tool_call 模板 + pipeline 状态机 + 重试兜底（2026-10-22）

## W2

- [x] 意图集构造（910 含 dev/test split）/ FAQ 集 91 / 脱敏集 800 / 工具 sanity 集 30
- [x] 判分器四件套（rule/mask/tool/faq，v0 启发式）
- [x] 首轮真模型四子集评测（PC llama.cpp Q8_0 + 真机 Termux，见 docs/评测记录/）
- [ ] faq_judge 升级 LLM-as-judge + 人工复核 30%
- [ ] LLM 增广接入行内 API（build/augment.py LLMRewriter）
- [ ] 测试集冻结（版本号 v1.0，hash 记录）
- [ ] 性能采集脚本适配 HTTP 服务形态（perf_probe 取 pid 改 `pgrep -f llama-server`）

## Harness 优化轮（方案-Harness优化实施计划.md，O1–O7 已全部实施 2026-10-23）

真模型复测按 R1→R2→R3 顺序在评测机（llama-server Q8_0 同口径）执行，与
20261023 基线四个 run 严格可比（run.json 已含 registry/templates 哈希）：

- [ ] R1（O1+O5）：复测 intent + faq——注册表边界修复的回收量
      `python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset intent`
      `python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset faq`
- [ ] R2（O2+O3+O4）：复测 tool（slots vs hermes 各一轮）+ faq + mask
      `... --subset tool --tool-mode slots`（对照臂：默认 hermes）
- [ ] R3（O6）：全四子集 `--pipeline merged`；记录 per-item 生成轮数（trace 步数）
- [ ] 4B-2507 终局轮（**直接用 Q4_K_M**，勿用 Q8：口径对齐部署形态 + 中端机内存放不下 4B Q8），
      同时补 1.7B Q4 一轮拿量化衰减系数

## 决策记录

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-10-20 | 主链路 MNN，备链路 Termux+llama.cpp | 见设计文档 4.1 |
| 2026-10-23 | 首轮真模型验证走备链路 C（llama-server + OpenAIAdapter） | 设备/Docker 未到位，方案 B 真机已跑通证明等价 |
| 2026-10-23 | 工具分支默认 hermes、`--tool-mode slots` 为优化臂 | 保持与基线可比，A/B 由 run.json tool_mode 字段区分 |
| 2026-10-23 | 4B 测试量化档定 Q4_K_M | 部署口径是 int4；4B Q8 权重约 4.3GB 中端机不可行 |

## 坑记录（追加式）

- **adb 方向**（评测-02 实锤，已修正 adapter_openai.py 文档）："PC 客户端 → 设备服务"
  用 `adb forward`；`adb reverse` 是反方向且会与 Termux 抢端口（couldn't bind）。
- **Qwen3 思考模式**：llama-server 必须 `--reasoning off`（b11669+；旧版
  `--chat-template-kwargs '{"enable_thinking":false}'`），否则输出带 `<think>` 段废掉 JSON 提取。
- **llama.cpp 参数**：b11669 的 `-fa` 必须显式带值（`-fa on`），否则吞掉后一个参数。
- **Windows Git Bash**：adb push `/sdcard/...` 会被 MSYS 改写成本地路径——先 `export MSYS_NO_PATHCONV=1`。
- **模型下载**：ModelScope `qwen/Qwen3-1.7B-GGUF` 仅 Q8_0 一档；HF 官方 GGUF 仓库名不存在。
- **评测机 adb server 不稳定**（每条命令后即死，forward/reverse 活不过命令边界）：长任务走局域网直连。
- **/sdcard 无执行权限**：Termux 需先把二进制拷到 `~/` 再运行。
- **mask 过滤权衡**：生产上用户输错的证件号会被二级过滤还原（漏保护），测试集无此问题——
  已在方案文档 O4 声明，生产可 `MASK_FILTER=off` 关闭。
