#!/usr/bin/env bash
# HF 权重 → MNN int4 单文件（权重+分词器+配置）。
# ⚠️ 命令为步骤示意：具体脚本路径与参数名以 MNN 仓库 README/llmexport 文档为准，
#    D2/D3 交叉编译通过后回填验证过的命令并删除本行警告。
set -euo pipefail
cd "$(dirname "$0")"

MNN_DIR="${MNN_DIR:-$HOME/src/MNN}"     # MNN 源码位置（git clone 后修改）
QUANT_BIT=4

python "$MNN_DIR/transformers/llmexport/export.py" \
  --path weights/Qwen3-1.7B \
  --export mnn --quant_bit "$QUANT_BIT" \
  --output mnn/qwen3-1.7b-int4

python "$MNN_DIR/transformers/llmexport/export.py" \
  --path weights/Qwen3-4B-Instruct-2507 \
  --export mnn --quant_bit "$QUANT_BIT" \
  --output mnn/qwen3-4b-2507-int4

# 推送到设备（路径与 adapter_mnn.py 的 MODEL_MAP 一致）
adb shell "mkdir -p /data/local/tmp/mnn/models"
adb push mnn/qwen3-1.7b-int4 /data/local/tmp/mnn/models/
adb push mnn/qwen3-4b-2507-int4 /data/local/tmp/mnn/models/

echo "完成。验证: python models/verify_tokenizer.py"
