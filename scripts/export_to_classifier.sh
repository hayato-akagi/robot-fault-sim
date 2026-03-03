#!/bin/bash
# 生成物を experiment-classifier のデータディレクトリへコピーする
# Usage: bash scripts/export_to_classifier.sh [path/to/experiment-classifier]

set -e
DEST="${1:-../experiment-classifier}"

if [ ! -d "$DEST" ]; then
  echo "Error: $DEST not found."
  echo "Usage: bash scripts/export_to_classifier.sh [path/to/experiment-classifier]"
  exit 1
fi

echo "Exporting to $DEST ..."
mkdir -p "$DEST/data/logs" "$DEST/data/docs" "$DEST/data/labels"
cp -v output/dataset/logs/*.txt   "$DEST/data/logs/"
cp -v output/dataset/docs/*.txt   "$DEST/data/docs/"
cp -v output/dataset/labels.csv   "$DEST/data/labels/"
echo "Done."
