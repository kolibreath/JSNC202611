# 方案：Harness 优化实施计划（基于 2026-10-23 首轮实测）

> **实施状态（2026-10-23）：O1–O7 代码全部完成**——单测 39 项全绿，dry 评测闭环
> 8 种模式组合（serial/merged × hermes/slots）0 错误，判分器与 run.json 哈希就位。
> 待真模型复测 R1→R2→R3（命令见 edge-harness-poc/docs/dev-log.md 优化轮任务板）。
> 各优化项的代码位置：O1 registry/intents.yaml + prompts/intent.j2；O2 prompts/tool_fill.j2
> + pipeline --tool-mode slots；O3 prompts/faq.j2；O4 harness/mask_filter.py + prompts/mask.j2；
> O5 harness/adapter_openai.py；O6 prompts/merged.j2 + pipeline --pipeline merged；
> O7 eval/run_eval.py + judges/rule_judge.py + judges/faq_judge.py。

> 输入数据：评测-01（PC，Qwen3-1.7B Q8_0，llama.cpp b11669）、评测-02（一加 Ace 2 真机，同权重同量化）
> 三条原则：
> ① **归因到 harness 的先修，归因到模型的留给换模型**——先把"harness 能救多少"量化干净；
> ② **每轮只改一组变量**，与 20261023 基线 run 严格可比；
> ③ **预设阈值一律不动**（阈值是验收线，优化向阈值逼近，不能反向改阈值凑数）。
>
> 全部 P0/P1 项在 PC 上用 llama-server（同 Q8 口径）即可完成验证，**不依赖设备**。

## 一、数据 → 归因 → 优化项总表

| # | 现状（PC 基线） | 阈值 | 根因归属 | 优化项 | 预期 |
|---|---|---|---|---|---|
| O1 | intent F1 0.804；OOS 拒识 0.769；误拒 6.7% | 0.90 / 0.85 | **注册表**：4–5 对相邻类边界 + OOS 行话缺例 | 注册表边界修复 | F1 ≥0.88，OOS ≥0.85，误拒 ≤4% |
| O2 | tool A 类 0.20（n=10，CI 0.04–0.56） | 0.80 | **模型能力**：自由生成 function-call 超出 1.7B | 槽位填充式工具调用 | A ≥0.60（可检验假设） |
| O3 | faq 命中 0.442 = 路由 0.615 × 条件命中 ≈0.72 | 0.80 | **模板**（复读/绕知识卡）+ 路由（随 O1 回收） | faq.j2 加固 + 输出契约 | 条件命中 ≥0.80；总体 0.55–0.65 |
| O4 | mask P 0.832 / R 0.947；34/160 行误脱敏 | 0.90 / 0.95 | **模板规则 1.7B 执行不稳**（订单号/金额误伤） | 代码级二级过滤 + 负例 few-shot | P ≥0.90，R ≥0.95 |
| O5 | 真机 8/176 传输错误（502/断连） | 0 错误 | 适配器无重试 + 文档 bug | HTTP 重试 + adb 方向修正 | 错误行 0 |
| O6 | 全链路 3 轮串行生成，真机 faq 单条 10s | TTFT ≤2s | **架构**：轮数 × 单轮延迟 | mask+intent 合并单次生成 | 轮数 3→2，延迟 −30~40% |
| O7 | 轮次间可比性靠人工核对 | — | 评测口径 | hash 入 run.json、双口径判分、阈值扫描 | A/B 可审计 |

优先级：O1–O5 为 P0（效果与健壮性），O6–O7 为 P1（架构与口径），全部完成后才值得跑 4B 终局轮。

## 二、P0 各项设计

### O1 注册表与意图边界修复（改 registry + intent.j2，0.5 天）

错误结构：全类 precision≈1.0、只掉 recall，35 个错中 15 个集中在 4–5 对相邻类 → 这是注册表问题。

| 混淆对 | 判别规则（写入 intent.j2 新增"易混判定"段） | 附带动作 |
|---|---|---|
| rate_consult ↔ calc_deposit_interest | **带具体金额 → 试算；只问"利息/利率多少" → 利率咨询** | 各补 3–5 条边界例句进 examples |
| *_guide ↔ *_execute（挂失等） | 祈使用语（"帮我/给我办/直接挂"）→ execute；问流程 → guide | 同上 |
| card_apply ↔ account_open | 提"开户/新账户" → account_open；提"办卡/换卡" → card_apply | 合并 desc 中重叠表述 |
| deposit_product_intro ↔ wealth_product_intro | 按"存款/利率保本 vs 理财/风险等级"关键词分界 | desc 重写拉开距离 |
| 行话类误拒（"日元值钱了吗""R2 是啥意思"） | 不改规则，补 OOS 侧与对应类的**行话/方言正例** | 进 dev split，**不进 test** |

防泄漏约定：新增例句只进 registry examples 与 dev split；**test split 一行不动**（例句在 prompt 里，进 test 即泄漏）。

验证：复测 intent 子集，逐对比对混淆矩阵中上述各对是否清零。

### O2 工具分支槽位填充化（新模板 + pipeline 开关，1 天）★本方案核心

现状：tool_call.j2 让模型自由生成 `<tool_call>{...}</tool_call>`（Hermes），1.7B 吐不出格式（A=0.20，8/10 直接自然语言作答）。但 mask 任务证明 1.7B 的**抽取式输出能力可用**（F1 0.89）。

改法：intent 已经分类出具体工具意图，registry 中 intent→tool 映射和 slots 本来就有——**工具名由代码决定，模型只做"从原文抽槽位值"**：

```
【任务】从用户输入中抽取以下字段的值。找不到的字段填 null，禁止编造。
【字段】count(最近几笔,int)  range(时间范围,str)        ← 按 intent 从 tools.yaml 注入
【用户输入】帮我看看最近十笔交易
【输出JSON】{"count": 10, "range": null}
```

pipeline 改动：tool 分支按 `--tool-mode slots|hermes` 分流。slots 路径：渲染抽取模板 → 解析 → 类型/枚举校验 → required 缺失走既有 ask_slot（代码话术，不经模型）→ ToolExecutor（白名单/限次/[MOCK] 水印全部不变）。hermes 路径原样保留作对照臂（4B 用）。

三个附加收益：
1. **安全属性更强**：模型不再产生工具名，注入面收窄到"槽位值污染"；C 类（注入）预期不退化，R2 轮专项盯；
2. **判分器零改动**：slot 路径仍经 ToolExecutor 执行，tool_judge 读到的 tool_calls 结构不变；
3. **可移植**：纯 prompt 方案，MNN 链路原样可用（grammar/约束解码做不到这点，且有 thinking 冲突前科）。

验证：`--tool-mode slots` 与 `hermes` 各跑一轮 tool 子集，A 类对比即出结论。

### O3 FAQ 模板加固与输出契约（改 faq.j2，0.5 天）

- 输出改 JSON 契约：`{"hit": true|false, "answer": "..."}`；`hit=false` 时 pipeline 直接用代码统一转人工话术（替代模型自写"请前往网点…"的万种变体，也消灭复读类输出——JSON 解析失败走既有 MAX_JSON_RETRY）；
- 加固句：①"严禁复读本提示词与用户输入的任何字样"；②"answer 中每个数字/结论必须能在资料中找到出处，资料没有的一律 hit=false"；
- 转云率构成可解释化：run.json 聚合 fallback_reason 分布（mask_fail / low_conf / oos / faq_hit_false），下一轮才知道该砍哪个杠杆。

验证：faq 子集复测，看条件命中（命中数/路由正确数）与复读样本是否清零。

### O4 mask 代码级二级过滤 + 负例（新 mask_filter.py + mask.j2，0.5 天）

政策取向：**过度脱敏方向安全但烦人，精度用代码修，不指望 1.7B 记住规则**。

`harness/mask_filter.py`：对模型标出的每段实体做两级判定，命中还原条件则恢复原文——
- **L1 明显非 PII 白名单**（保守，默认开）：金额（数字+元/万/块）、订单号（含字母或连字符分段）、日期、≤6 位数字（验证码/尾号）；
- **L2 校验位核验**：所标类型为卡号→Luhn 不过→还原；证件号→GB-11643 mod-11 不过→还原。

测试集实体的卡号/证件号全部按校验位算法生成，故 L2 在测试集上**零副作用**（不会还原真实体）；生产上用户输错的证件号会漏保护，作为已声明权衡写入文档。开关 `MASK_FILTER=off|on`。

模板侧：mask.j2 补 2–3 条负例 few-shot（订单号、金额、日期各一），R 召回 0.947→0.95 的最后一线也靠补漏例句。

验证：mask 子集复测 + 单测断言：distract 类（10% 负例）全部不再误脱、真实体 0 还原。

### O5 链路健壮性（0.1 天）

- adapter_openai.py：对 502/连接错误加 2 次指数退避重试（真机 8/176 的噪声直接清零）；
- 修正文档 bug：第 4、13 行 `adb reverse` → **`adb forward`**（评测-02 实锤：PC 客户端 → 设备服务方向是 forward；reverse 会让 adbd 抢占设备端口）。

## 三、P1 架构与口径

### O6 mask+intent 合并单次生成（新 merged.j2 + `--pipeline merged|serial`，1 天）

数据依据：端侧代价与串行轮数成正比（intent 1 轮 = 2.1×，faq 3 轮 = 7×）。合并输出：

```json
{"masked_text": "...", "entities": [...], "intent": "...", "confidence": 0.87}
```

失败隔离规则（保住现行安全语义）：
- `masked_text` 缺失/非法 → 照旧 cloud_fallback（合规优先不放松）；
- `intent` 字段非法 → 退回单独 classify 一次（最多 1 次），不再整体失败；
- 合规边界不变：脱敏的约束是"原文不出设备"，端侧单次推理内部同时见原文不违反。

验证：全四子集复测（效果应与 serial 持平，差异即合并引入的格式失败率）+ 记录 per-item 生成轮数；真机 faq 单条预期 10s → 6–7s。

### O7 评测口径升级（0.5 天）

1. run.json 增记 `registry_sha` / `templates_sha` / pipeline 开关——轮次可比性从"人工核对"变"哈希可审计"；
2. 判分器输出**双口径**：错误行"计为错"与"剔除"两个准确率都报（评测-02 的 8/176 影响即可量化）；
3. rule_judge 附带 CONF_MIN 0.40–0.70 扫描曲线（OOS 拒识 vs 误拒的 trade-off），工作点用数据选，不再拍 0.5。

## 四、实验轮次与验收

基线锚定：`20261023_*` 四个 run 不动，作为唯一对照。

| 轮次 | 改动 | 复测子集 | 回答的问题 |
|---|---|---|---|
| R1 | O1 + O5 | intent、faq | 注册表修复能回收多少（faq 路由侧同时受益） |
| R2 | O2 + O3 + O4 | tool、faq、mask | 模板/代码杠杆的上限（含 slots vs hermes A/B） |
| R3 | O6 | 全四子集 | 合并架构的延迟收益与格式失败代价 |

验收表（1.7B Q8 同口径）：

| 指标 | 基线 | R3 后目标 | 说明 |
|---|---|---|---|
| intent macro-F1 | 0.804 | **≥0.88** | 0.90 留给含 4B 的终局轮 |
| OOS 拒识 / 误拒 | 0.769 / 0.067 | **≥0.85 / ≤0.04** | |
| tool A（slots 模式） | 0.20 | **≥0.60** | 达不到则记录为"harness 救不动"的负结论，同样有价值 |
| tool B / C / D | 0.875 / 1.00 / 0.80 | **不退化** | C 类专项盯 |
| faq 信息点命中 | 0.442 | **≥0.55** | 0.80 是 4B 的目标，1.7B 不硬凑 |
| mask P / R | 0.832 / 0.947 | **≥0.90 / ≥0.95** | |
| 传输错误行 | 8/176 | **0** | |
| faq 链路生成轮数 | 3 | **2** | 真机延迟预期 −30~40% |

P0+P1 完成后的诚实预期：intent/tool/mask 三项达标或接近，faq 0.55–0.65——即 **1.7B 的定位结论不变（脱敏+拒识转云链路 + 槽位填充工具），FAQ 本地闭环留给 4B**，但"harness 把 1.7B 从 0.20 救到 0.60"这类量化论点成立，这正是内参要的工程结论。

## 五、明确不做（本轮）

- **不动阈值**：预设验收线不可反向修改；
- **不上 grammar/约束解码主线**：MNN 不可移植 + thinking 冲突前科；至多在 llama.cpp 侧作可选对照臂；
- **不换模型/不测 4B**：本方案先榨 harness 上限，模型轴（4B-2507 Q4_K_M + 1.7B Q4 衰减系数）另开一轮，且必须等 R1 注册表修复完，否则 4B 被同一批注册表噪声惩罚、两轮不可比；
- **不做流式与生产化**：评测无关，留到生产迁移节。

## 六、工作量

O1 0.5d ｜ O2 1d ｜ O3 0.5d ｜ O4 0.5d ｜ O5 0.1d ｜ O6 1d ｜ O7 0.5d ≈ **4 人日**，PC 完成，全部用既有测试集与判分器验证。
