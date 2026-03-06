#!/usr/bin/env python3
"""
labels.csv + logs/*.txt → data/sample_dataset.json 変換スクリプト

ラベル正規化ルール:
  - mechanical_* → ["mechanical"]
  - electrical   → ["electrical"]
  - software     → ["software"]
  - normal       → []  （正常ログ）
"""

import csv
import json
from pathlib import Path

# --- パス設定 -------------------------
ROOT = Path(__file__).resolve().parent.parent
LABELS_CSV = ROOT / "output" / "dataset" / "labels.csv"
LOGS_DIR   = ROOT / "output" / "dataset" / "logs"
OUT_PATH   = ROOT / "data" / "sample_dataset.json"
# -------------------------------------

LABEL_MAP = {
    "normal":             [],
    "mechanical_pad_wear": ["mechanical"],
    "mechanical_bearing":  ["mechanical"],
    "mechanical_actuator": ["mechanical"],
    "mechanical_combined": ["mechanical"],
    "electrical":          ["electrical"],
    "software":            ["software"],
}


def normalize_label(raw_label: str) -> list[str]:
    """CSV の label 値をターゲット形式のリストに変換する。"""
    if raw_label in LABEL_MAP:
        return LABEL_MAP[raw_label]
    # フォールバック: mechanical_ 系はトップレベルに丸める
    if raw_label.startswith("mechanical"):
        return ["mechanical"]
    # それ以外はそのままリストに
    return [raw_label]


def load_log_text(log_id: str) -> str:
    """logs/ 以下の対応テキストを読み込む。"""
    log_file = LOGS_DIR / f"{log_id}.txt"
    if not log_file.exists():
        raise FileNotFoundError(f"Log file not found: {log_file}")
    return log_file.read_text(encoding="utf-8").strip()


def build_dataset() -> list[dict]:
    """labels.csv を読んでデータセットを構築する。重複 log_id は初出のみ採用。"""
    seen: set[str] = set()
    records: list[dict] = []

    with open(LABELS_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            log_id = row["log_id"]
            if log_id in seen:
                continue
            seen.add(log_id)

            records.append(
                {
                    "log_id":       log_id,
                    "log_text":     load_log_text(log_id),
                    "ground_truth": normalize_label(row["label"]),
                }
            )

    return records


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = build_dataset()
    OUT_PATH.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(dataset)} records → {OUT_PATH}")


if __name__ == "__main__":
    main()
