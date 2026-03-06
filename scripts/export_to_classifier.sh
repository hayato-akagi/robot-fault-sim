#!/bin/bash
# 生成物をターゲット形式 (Dataset Format Guide) に変換して
# experiment-classifier のデータディレクトリへコピーする
#
# Usage: bash scripts/export_to_classifier.sh [path/to/experiment-classifier]
#
# 処理内容:
#   1. labels.csv + logs/*.txt → data/sample_dataset.json (JSON 配列)
#   2. data/knowledge/*.md     → $DEST/data/knowledge/
#   3. data/sample_dataset.json → $DEST/data/

set -e
DEST="${1:-../experiment-classifier}"

if [ ! -d "$DEST" ]; then
  echo "Error: $DEST not found."
  echo "Usage: bash scripts/export_to_classifier.sh [path/to/experiment-classifier]"
  exit 1
fi

# Step 1: JSON データセットを生成
echo "[1/3] Building JSON dataset ..."
python scripts/build_dataset_json.py

# Step 2: ナレッジベースをコピー
echo "[2/3] Copying knowledge base ..."
mkdir -p "$DEST/data/knowledge"
cp -v data/knowledge/*.md "$DEST/data/knowledge/"

# Step 3: JSON データセットをコピー
echo "[3/3] Copying dataset JSON ..."
mkdir -p "$DEST/data"
cp -v data/sample_dataset.json "$DEST/data/"

echo "Done."
