#!/usr/bin/env bash
# 下载两个模型的原始权重（HF 或国内镜像）。
# 用法：bash models/download_models.sh
set -euo pipefail
cd "$(dirname "$0")"

# 国内网络走镜像；海外直连可去掉
export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

MODELS=(
  "Qwen/Qwen3-1.7B"
  "Qwen/Qwen3-4B-Instruct-2507"
)

command -v huggingface-cli >/dev/null || {
  echo "请先: pip install -U 'huggingface_hub[cli]'"; exit 1; }

for m in "${MODELS[@]}"; do
  name=$(basename "$m")
  echo "==> download $m"
  huggingface-cli download "$m" --local-dir "weights/$name" --exclude "*.pth" "original/*"
done

echo "完成。下一步: bash models/export_mnn.sh"
