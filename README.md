# JSNC 端侧智能体验证工程（技术内参配套）

验证"端侧小模型（Qwen3-1.7B / Qwen3-4B-Instruct-2507，MNN int4）+ 自建 Harness"
在手机银行场景的能力边界：**脱敏 → 意图路由（30 类 + OOS 拒识）→ 离线 FAQ / mock 工具 / 转云**。
架构为"PC 驱动 + 设备推理"：Harness 与评测跑在 PC（Python），模型前向跑在 Android 真机
（MNN 交叉编译的 `llm_demo` CLI，经 adb 驱动，**无需开发 Android App**）。

## 仓库结构

```
├── 方案-端侧大模型与银行智能体内参.md      # 内参主文档（定位/章节框架/四问题结论）
├── 方案-端侧意图路由验证实施计划.md        # ★ 主设计文档 v2（目标阈值/模型矩阵/测试集/开发部署/Harness 设计）
├── 调研-01~06-*.md                        # 背景调研（模型性能/工具调用/WASM/业界/MiniCPM/适老化）
└── edge-harness-poc/                      # ★ 全部工程代码（详见其 README.md）
    ├── registry/    # 单一事实源：30 意图 + 6 mock 工具 + 15 张 FAQ 知识卡（值为占位，待行内替换）
    ├── harness/     # Harness 参考实现：adapter_mnn / adapter_openai / pipeline 状态机 / 4 个 prompt 模板
    ├── build/       # 测试集构建器 + LLM 增广（intent 910 / mask 800 / tool 30 / faq 91 已生成入库）
    ├── eval/        # run_eval.py（三后端 dry|mnn|openai）+ 4 个判分器 + 阈值判定
    ├── bench/       # 真机性能采集：perf_probe / endurance / cold_start
    ├── models/      # 模型下载、MNN 转换、tokenizer 校验脚本（权重产物已 gitignore）
    ├── tests/       # 4 套单测（全部通过：registry lint / 模板 / 解析器 / 状态机分支）
    └── docs/        # device-setup.md（设备清单）、dev-log.md（W1/W2 任务板 + 坑记录）
```

## 当前状态与交接说明（给接手开发的智能体）

**代码已全部完成**（W0+）：注册表、Harness、四子集数据集、评测闭环、判分器、性能探针、
单测全绿。dry 后端全管线已验证（457 行 0 错误）。尚未做任何真机操作。

接入 Android 设备后的工作按 `edge-harness-poc/docs/dev-log.md` 的 W1 任务板执行，
顺序与入口如下：

| 步骤 | 内容 | 入口 |
|---|---|---|
| D1 | 设备初始化（USB 调试、thermal 节点探测、基线信息采集） | `edge-harness-poc/docs/device-setup.md` |
| D2 | MNN 源码 Docker 交叉编译 arm64 `llm_demo`，回填路径常量 | `harness/adapter_mnn.py` 中 `TODO(D2)` |
| D3 | 模型转换 + tokenizer 对齐校验（实现 `gen_baseline`） | `models/verify_tokenizer.py` |
| D4 | CLI 常驻/批量改造（方案 A：`--file` 批处理优先） | 设计文档 4.4.2 决策表；`TODO(D4)` 标记处 |
| D5+ | smoke → 全量评测 → 性能/耐久/冷启动 | `eval/run_eval.py`、`bench/*.py` |

关键设计依据（为何不写 App、性能口径如何排除 adb 开销、安全规则硬编码位置）见
`方案-端侧意图路由验证实施计划.md` 第 4.1、4.4、5 节，**改代码前先读**。

## 快速命令

```bash
cd edge-harness-poc
pip install -r requirements.txt
python -m pytest tests/ -q                      # 全部单测
python -m harness.pipeline --dry-run --input "帮偶查哈子余额"   # 无设备联调
python eval/run_eval.py --backend dry --subset intent          # dry 评测闭环

# 设备到位前可选：本机 llama.cpp 起服务，真模型过全管线
llama-server -m ~/.cache/qwen3-1.7b-q4km.gguf -c 8192 --port 8080 -fa &
python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset intent
```

## 待行内确认的三项输入（阻塞 W2，不阻塞 W1）

1. 30 类意图清单需按行内手机银行 App 功能树修订（`registry/intents.yaml`）；
2. 15 张知识卡中的 `[占位示例]` 数值需业务双审后替换（`registry/kb/`）；
3. 测试集 LLM 增广用的行内大模型 API（`build/augment.py` 的 `LLMRewriter`）。

## 注意

- 本仓库含行内技术研究文档与评测方案，**请保持仓库为 private**。
- 知识卡数值当前全部为占位示例，不包含真实业务数据；测试集 PII（卡号/证件号/手机号）
  均为脚本按校验位算法生成的虚构值。
