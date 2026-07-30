#!/usr/bin/env python3
"""
labels.csv + trials/<log_id>/ → data/sample_dataset.json 変換スクリプト

各試行ディレクトリのログ群（中央コントローラログ・コンポーネント別ログ）を
`=== path ===` 区切りで1テキストにバンドルする。CSV 時系列はサイズ抑制のため
CSV_SAMPLE_STEP 行ごとに間引く。

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
TRIALS_DIR = ROOT / "output" / "dataset" / "trials"
OUT_PATH   = ROOT / "data" / "sample_dataset.json"

CSV_SAMPLE_STEP = 20  # CSV 時系列の間引き間隔（行）
BUNDLE_ORDER = [
    "metadata.json",
    "controller/main.log",
    "controller/motion.csv",
    "components/servo/trace.csv",
    "components/servo/alarms.log",
    "components/gripper/events.log",
    "components/fieldbus/comm.log",
]
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


def _sample_csv(text: str) -> str:
    """ヘッダは残し、データ行を CSV_SAMPLE_STEP 行ごとに間引く。"""
    lines = text.strip().splitlines()
    if len(lines) <= 1:
        return text.strip()
    return "\n".join([lines[0]] + lines[1::CSV_SAMPLE_STEP])


def load_log_text(log_id: str) -> str:
    """trials/<log_id>/ のログ群を1テキストにバンドルする。"""
    trial_dir = TRIALS_DIR / log_id
    if not trial_dir.is_dir():
        raise FileNotFoundError(f"Trial dir not found: {trial_dir}")

    parts = []
    for rel in BUNDLE_ORDER:
        f = trial_dir / rel
        if not f.exists():
            continue
        text = f.read_text(encoding="utf-8").strip()
        if rel.endswith(".csv"):
            text = _sample_csv(text)
        parts.append(f"=== {rel} ===\n{text}")
    return "\n\n".join(parts)


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
