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
- [ ] D5 adapter_mnn.py 打通 + 意图注册表 v1（先 5 类跑通）+ intent.j2 模板
      通过标准：PC 单条命令完成"输入 → JSON 意图"闭环
- [ ] D6–D7 mask/faq/tool_call 模板 + pipeline 路由状态机 + 重试兜底；50 条 smoke
      通过标准：四个子链路各跑通，格式零报错

## W2

- [ ] 意图集构造（30 类 × 25–40 条 + OOS 130，方法见设计文档 3.2.2）
- [ ] FAQ 集（100 条 + 知识卡双人复核）/ 脱敏集（800 条）/ 工具 sanity 集（30 case）
- [ ] 判分器（rule_judge + FAQ 的 LLM-as-judge）
- [ ] 性能采集脚本联调（perf_probe / endurance）
- [ ] 公开基准校准（BFCL 抽样 20 + FinEval/FinanceIQ 各 200）
- [ ] 测试集冻结（版本号 v1.0，hash 记录）

## 决策记录

| 日期 | 决策 | 理由 |
|---|---|---|
| 2026-10-20 | 主链路 MNN，备链路 Termux+llama.cpp | 见设计文档 4.1 |
| | D4 常驻改造选方案 ___ | |

## 坑记录（追加式）

- （暂无）
