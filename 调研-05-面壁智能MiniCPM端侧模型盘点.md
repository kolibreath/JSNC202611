# 调研-05：面壁智能（OpenBMB）端侧模型盘点（补充调研）

> 内参系列：端侧大模型 + Agent Harness 在银行业的应用 · 问题 1 的厂商补充
> 调研日期：2026-10-20。除注明"官方口径/转述"外，数据来自 GitHub/HuggingFace/论文等原始来源；所有链接访问日期均为 2026-10-20。无法确认的信息标注【待核实】。

---

## ① 厂商概况

- 面壁智能（ModelBest / OpenBMB，清华系）是国内"端侧优先"路线最彻底的厂商之一，MiniCPM 系列全线**代码与权重均 Apache 2.0**。[来源：MiniCPM-V GitHub README（中文）](https://github.com/OpenBMB/MiniCPM-V/blob/main/README_zh.md)、[面壁智能官网](https://modelbest.cn)，访问日期 2026-10-20
- 效率技术栈：InfLLM v2 可训练稀疏注意力（长文本推理提速）、CPM.cu 自研推理框架（官方称端侧推理常规提速 5 倍）、LES 前瞻专家调度（MoE 端侧真实加速 ×5，专家权重可放 SSD）、DSpark 投机采样头（2026-10-15 发布）。[来源：MiniCPM4 论文](https://arxiv.org/html/2506.07900v1)、[MiniCPM-V README](https://github.com/OpenBMB/MiniCPM-V/blob/main/README_zh.md)、[知乎发布解读](https://zhuanlan.zhihu.com/p/1915340618105856653)，访问日期 2026-10-20
- 生态位：与高通 AI Hub 有官方合作（[面壁智能 AI Hub 模型页](https://aihub.qualcomm.cn/model-makers/open-bmb)）；GGUF/Ollama/MNN 生态齐全；MiniCPM-V 4.7 明确支持 iOS、安卓、**鸿蒙**，并适配 Intel/AMD/Arm/瑞芯微/后摩等芯片平台。

---

## ② 纯文本模型（MiniCPM 系列）

| 模型 | 发布时间 | 参数量 | 体积/内存 | 端侧速度 | 备注 |
|---|---|---|---|---|---|
| MiniCPM 2B（初代"小钢炮"） | 2024-02 | 2.4B（非词嵌入参数） | INT4 约 **2 GB** | 早期 MLC-LLM 部署实测可用 | 国内最早规模化上手机的 LLM 之一，历史参照。[来源：MiniCPM 部署教程](https://docs.feishu.cn/v/wiki/D2tFw8Pcsi5CIzkaHNacLK64npg/ak)、[项目页](https://openbmb.vercel.app/minicpm)，访问日期 2026-10-20 |
| **MiniCPM3-4B** | 2024-09 | 4B | 内存优化至约 **2 GB** | 同档参照：CPU 10–20 tok/s（4B 档通用量级） | 32K 上下文（S2-Attention/LLMxMapReduce），**原生支持工具调用与代码解释器**，官方称对齐 GPT-3.5；手机适配最成熟的一代。[来源：腾讯云社区解读](https://cloud.tencent.com/developer/article/2474901)，访问日期 2026-10-20 |
| **MiniCPM4-0.5B** | 2025-06 | 0.5B | 约 0.3–0.4 GB（int4 估算） | 未单独实测（应显著快于同档） | 与 8B 同批发布的低端机/手表/车机档。[来源：新浪报道](https://cj.sina.cn/articles/view/5901272611/15fbe462301902vsyg)，访问日期 2026-10-20 |
| **MiniCPM4-8B / MiniCPM4.1-8B** | 2025-06 / 更新 | 8B | Q4 约 4.5–5 GB（估算，【待核实】）；8GB+ 内存旗舰可跑 | 第三方端侧设备实测**约 30 tok/s**、首 token 约 2.1s；128K 长文本解码约 **10 tok/s**（对照 Qwen3-8B 同场景约 1.5 tok/s，约 7 倍加速，Jetson AGX Orin 数据） | 核心卖点 InfLLM v2 稀疏注意力（原生 32K 上下文）；另有**面向端侧设备的 MiniCPM4-MCP 变体**（公开细节少，需向面壁商务确认【待核实】）。[来源：MiniCPM4 论文](https://arxiv.org/html/2506.07900v1)、[Model Card](https://huggingface.co/openbmb/MiniCPM4-8B)、[实测博客](https://www.xugj520.cn/archives/mobile-edge-ai-minicpm.html)、[知乎全方位解读](https://zhuanlan.zhihu.com/p/1917959492081001377)、[Ollama 页](https://ollama.com/openbmb/minicpm4.1)，访问日期 2026-10-20 |

---

## ③ 多模态视觉模型（MiniCPM-V 系列，OCR/票据/图像场景相关）

| 模型 | 发布时间 | 参数量 | 体积/内存 | 手机端表现 | 备注 |
|---|---|---|---|---|---|
| MiniCPM-V 4.0 | 2025-08 | 4B | — | 官方称手机端稳定流畅运行 | 上一代主力。[来源：智源社区](https://hub.baai.ac.cn/view/48014)，访问日期 2026-10-20 |
| MiniCPM-V 4.5 | 2025-10 | 约 8B | Q4 约 4.5 GB（估算，【待核实】） | 旗舰机可跑 | 强 OCR/视频理解；配套论文《Cooking Efficient MLLMs via Architecture, Data, and Training Recipe》（[arXiv 2509.18154](https://arxiv.org/abs/2509.18154)） |
| **MiniCPM-V 4.6** | 2026-05 | 1.3B | **6GB 内存手机可本地流畅运行（官方口径）** | 流畅（官方口径） | 2026-06 进 Ollama 官方模型库，部署门槛最低；混合视觉 token 压缩。[来源：MiniCPM-V README](https://github.com/OpenBMB/MiniCPM-V/blob/main/README_zh.md)，访问日期 2026-10-20 |
| **MiniCPM-V 4.7（1B 轻量档）** | 2026-10 | 1B | 约 0.6–1 GB（int4/GGUF 估算） | 6GB 内存手机可流畅跑（官方口径） | 最新轻量档，官方称领先 Qwen3.5-0.8B。[来源：同上 README]，访问日期 2026-10-20 |
| **MiniCPM-V 4.7（35B-A3B MoE 旗舰档）** | 2026-10-12 | 总参 35B / **激活仅 3B** | **内存仅 3 GB**（LES 调度 + 专家权重放 SSD） | **13+ tok/s（iPhone 17 Pro Max，官方实测）**；配 DSpark 投机解码更快 | 系列首个 MoE；单图/多图/文档/视频理解，4x/16x 混合视觉 token 压缩；官方称得分超 Qwen3.6 35B-A3B；量化格式齐全（BF16/FP8/int4/AWQ/GPTQ/GGUF），支持 iOS/安卓/鸿蒙。[来源：MiniCPM-V README（中文）](https://github.com/OpenBMB/MiniCPM-V/blob/main/README_zh.md)、[东方财富报道](https://wap.eastmoney.com/a/202610133894181015.html)，访问日期 2026-10-20 |

---

## ④ 全模态模型（MiniCPM-o 系列）

| 模型 | 参数量 | 说明 |
|---|---|---|
| MiniCPM-o 4.5 | 9B | 端到端全双工全模态：视频/音频流输入 + 文本/语音输出，可打断、可主动交互，支持声音克隆；官方称视觉理解超 GPT-4o、整体接近 Gemini 2.5 Flash（厂商口径）。**9B 对多数手机偏重**，更适合柜台终端/平板场景。[来源：MiniCPM-V README](https://github.com/OpenBMB/MiniCPM-V/blob/main/README_zh.md)，访问日期 2026-10-20 |

---

## ⑤ 银行场景选型建议

1. **手机 App 文本助手（意图识别、表单填充、离线 FAQ）**：MiniCPM3-4B（约 2GB 内存、原生工具调用、适配成熟）为稳妥起点；关注 MiniCPM4 系小尺寸（0.5B 已有，中间档待补）。
2. **票据/凭证图像理解**：MiniCPM-V 4.6（1.3B，6GB 内存机型覆盖面大）起步；旗舰体验档用 MiniCPM-V 4.7——"3GB 内存 13 tok/s"是目前端侧多模态最好的公开数据（官方口径）。
3. **差异化优势**：全线 Apache 2.0（采购干净）；高通 AI Hub 官方合作可走骁龙 NPU 路线；明确适配鸿蒙（行内 App 若有鸿蒙版，这是少数有官方背书的选项）；GGUF/Ollama/MNN 分发格式不受限。
4. **风险提醒**：面壁公开速度数据多为官方口径或非手机设备（Jetson 等），且量化体积多为估算——写入内参或立项前，建议按行内测试机型（骁龙 8 系/天玑 9400/iPhone）实测基线；MiniCPM4-MCP 变体能力需商务/官方渠道二次确认。

---

## ⑥ 来源清单（全部访问日期 2026-10-20）

**官方原始来源**
1. MiniCPM-V GitHub README（中文，含 4.7/4.6/4.5/o 4.5 数据与 Apache 2.0 声明）— https://github.com/OpenBMB/MiniCPM-V/blob/main/README_zh.md
2. MiniCPM4 论文《MiniCPM4: Ultra-Efficient LLMs on End Devices》— https://arxiv.org/html/2506.07900v1
3. MiniCPM4-8B / MiniCPM4.1-8B Model Card — https://huggingface.co/openbmb/MiniCPM4-8B ；https://huggingface.co/openbmb/MiniCPM4.1-8B
4. openbmb/minicpm GitHub — https://github.com/openbmb/minicpm
5. MiniCPM-V 4.7 Ollama — https://ollama.com/openbmb/minicpm-v4.7 ；MiniCPM4.1 Ollama — https://ollama.com/openbmb/minicpm4.1
6. 面壁智能官网 — https://modelbest.cn
7. 高通 AI Hub × 面壁智能 — https://aihub.qualcomm.cn/model-makers/open-bmb
8. MiniCPM-V 4.5 论文 — https://arxiv.org/abs/2509.18154

**媒体/社区（转述，已标注）**
9. MiniCPM4 发布报道（8B 与 0.5B 规格）— https://cj.sina.cn/articles/view/5901272611/15fbe462301902vsyg
10. 面壁小钢炮 MiniCPM 4.0 开源解读（CPM.cu 220x/5x 提速）— https://zhuanlan.zhihu.com/p/1915340618105856653
11. MiniCPM4 全方位解读（Jetson 128K 解码 10 tok/s vs Qwen3-8B 1.5）— https://zhuanlan.zhihu.com/p/1917959492081001377
12. 8B 大模型如何塞进手机（端侧约 30 tok/s、首 token 2.1s 实测）— https://www.xugj520.cn/archives/mobile-edge-ai-minicpm.html
13. MiniCPM 3.0 解读（4B、2GB 内存、工具调用、GPT-3.5 对齐）— https://cloud.tencent.com/developer/article/2474901
14. MiniCPM 初代部署教程（INT4 约 2GB）— https://docs.feishu.cn/v/wiki/D2tFw8Pcsi5CIzkaHNacLK64npg/ak ；项目页 — https://openbmb.vercel.app/minicpm
15. MiniCPM-V 4.0 手机端运行（智源社区）— https://hub.baai.ac.cn/view/48014
16. MiniCPM-V 4.7 发布报道 — https://wap.eastmoney.com/a/202610133894181015.html

**遗留【待核实】清单**
- MiniCPM4-8B Q4 精确体积与真机（骁龙/天玑/iPhone）tokens/s 实测
- MiniCPM4-MCP 变体的能力范围与获取方式（仅调研-01 中一句话提及，官方页面未检索到）
- MiniCPM3-4B 在 2026 年当前框架（llama.cpp/MNN/LiteRT）下的适配状态
- MiniCPM-V 4.6/4.7-1B 的独立第三方实测速度
