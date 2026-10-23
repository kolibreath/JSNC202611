# edge-harness-poc

手机银行端侧"意图路由 + 离线 FAQ"验证项目（技术内参配套工程）。

> 设计文档：`../方案-端侧意图路由验证实施计划.md`（v2）
> 背景调研：`../调研-01~06*.md`

## 目标

验证 Qwen3-1.7B / Qwen3-4B-Instruct-2507（MNN int4）在中端 Android 机本地完成
"脱敏 → 意图分类（30 类 + OOS）→ 路由（本地 FAQ / mock 工具 / 转云）"全链路的
效果与工程指标。**PC 驱动 + 设备推理**架构（等价性论证见设计文档 4.1）。

## 目录结构

```
edge-harness-poc/
├── models/          # 模型下载、MNN 转换、tokenizer 对齐校验
├── registry/        # ★ 单一事实源：意图注册表 / 工具注册表 / FAQ 知识卡
├── harness/         # ★ Harness 参考实现（L1 适配 / L3 编排 / L2 模板）
├── eval/            # 测试集、批量评测、判分器
├── bench/           # 真机性能采集（内存/温度/耐久/冷启动）
└── docs/            # 设备初始化、开发日志（坑记录）
```

## 快速开始（W1 阶段完成后可用）

```bash
# 1) 下载并转换模型（首次，约 20-40 分钟）
bash models/download_models.sh
bash models/export_mnn.sh

# 2) 设备链路 smoke test（需 adb 连接真机）
python harness/adapter_mnn.py --smoke --model qwen3-1.7b

# 3) 无设备开发模式（模板渲染与路由状态机联调）
python -m harness.pipeline --dry-run --input "帮偶查哈子余额"
#   优化开关：--tool-mode slots（O2 槽位填充）--pipeline merged（O6 合并生成）

# 4) 批量评测（效果集）
python eval/run_eval.py --model qwen3-1.7b --subset intent --device mid
#   新开关：--tool-mode slots  --pipeline merged（run_id 自动加后缀，run.json 记录哈希）

# 5) 判分
python eval/judges/rule_judge.py --run reports/<run_id>
```

## 当前状态（W0+：代码完成，待设备）

- [x] 目录骨架与注册表 v1（30 类意图 + 15 张知识卡，**需按行内 App 功能树修订**）
- [x] 4 个 prompt 模板 + harness 参考实现（路由状态机 5 分支全通过单测）
- [x] 测试套件：registry lint / 模板快照 / 解析器对抗 / 状态机分支（tests/）
- [x] 数据集 v0 已生成：intent 910 / mask 800（校验位+span 全验证）/ tool 30 / faq 91
- [x] 评测闭环：四子集 × 三后端（dry/mnn/openai）+ 四判分器 + 阈值判定
- [x] OpenAI 兼容后端：设备到位前可用本机 llama.cpp server 跑真模型验证全管线
- [x] **首轮真模型实测完成**（PC Q8_0 + 真机 Termux，基线报告见 docs/评测记录/）：
      intent F1 0.804 / faq 0.442 / tool A 0.20 / mask F1 0.886，端云等价性已证实
- [x] **Harness 优化 O1–O7 全部实施**（方案-Harness优化实施计划.md）：
      注册表边界修复、槽位填充工具（--tool-mode slots）、FAQ JSON 契约、
      mask 二级过滤（harness/mask_filter.py）、HTTP 重试、合并链路（--pipeline merged）、
      run.json 哈希 + 判分器双口径 + 置信度阈值扫描
- [ ] R1→R2→R3 真模型复测（命令见 docs/dev-log.md，与 20261023 基线可比）
- [ ] W1-D1/2 设备初始化 + MNN 交叉编译（阻塞点：设备到位）
- [ ] W1-D3 模型转换与 tokenizer 校验（models/verify_tokenizer.py baseline 待实现）
- [ ] W1-D4 CLI 常驻改造 + adapter_mnn 实际命令回填（TODO 标记处）
- [ ] W2 LLM 增广接入行内 API、测试集冻结 v1.0、faq_judge 升级 LLM-as-judge
- [ ] 4B-2507 终局轮（**Q4_K_M 口径**，勿用 Q8）+ 1.7B Q4 量化衰减系数
- [ ] W3 全量实测

### 设备到位前的真模型验证（可选，推荐）

```bash
# 本机/评测机起 llama.cpp server（b11669+ 用 --reasoning off 关思考）
llama-server -m models/Qwen3-1.7B-Q8_0.gguf -c 8192 --port 8080 --host 127.0.0.1 -fa on --reasoning off &
# 全管线真模型评测（Q4_K_M 口径待 4B 轮启用）
python eval/run_eval.py --backend openai --endpoint http://127.0.0.1:8080/v1 --subset intent
```

## 已知坑（开工前必读）

完整坑记录见 docs/dev-log.md（adb forward 方向、--reasoning off、MSYS 路径改写、
ModelScope 仅 Q8_0、/sdcard 无执行权限等），摘要：
- Qwen3 思考模式与 grammar 约束同开可能失效（llama.cpp #20345）——评测统一 `--reasoning off`。
- MNN CLI 默认单轮退出，批量评测前必须做常驻改造（否则每条重载模型）。
- 热节点路径 `/sys/class/thermal/thermal_zone*` 因机型而异，D1 探测后写入 device-setup.md。
- 8GB 中端机跑 4B-Q4 贴内存红线，OOM/杀后台本身是结论素材，如实记录。
- mask 二级过滤会还原"输错的证件号"（生产权衡，测试集无此问题），可 MASK_FILTER=off 关闭。
