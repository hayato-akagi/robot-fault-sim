#!/usr/bin/env python3
"""sample_dataset.json の log_text から ERROR / WARN 行と前後3行の INFO を抽出する."""

import argparse
import json
import re
from pathlib import Path

LOG_LEVEL_RE = re.compile(r"\]\s+(ERROR|WARN|INFO)\b")
CONTEXT_LINES = 3  # ERROR/WARN の前後に付ける INFO 行数


def extract_error_warn_with_context(log_text: str, context: int = CONTEXT_LINES) -> str:
    """最初の ERROR 行・最初の WARN 行と前後 context 行分の INFO を抽出し、連結したテキストを返す.

    重複する INFO 行は除去し、時系列順を維持する。
    """
    lines = log_text.split("\n")
    # 各行のレベルを事前分類
    levels = []
    for line in lines:
        m = LOG_LEVEL_RE.search(line)
        levels.append(m.group(1) if m else None)

    # 最初の ERROR と最初の WARN のインデックスのみ収集
    first_error = next((i for i, lv in enumerate(levels) if lv == "ERROR"), None)
    first_warn = next((i for i, lv in enumerate(levels) if lv == "WARN"), None)
    target_indices = [i for i in [first_error, first_warn] if i is not None]

    # 出力に含める行インデックスを集める (set で重複排除)
    include = set(target_indices)
    for idx in target_indices:
        # context_before: idx より前の INFO 行を最大 context 件
        count = 0
        for j in range(idx - 1, -1, -1):
            if levels[j] == "INFO":
                include.add(j)
                count += 1
                if count >= context:
                    break

        # context_after: idx より後の INFO 行を最大 context 件
        count = 0
        for j in range(idx + 1, len(lines)):
            if levels[j] == "INFO":
                include.add(j)
                count += 1
                if count >= context:
                    break

    # 時系列順にソートして連結
    return "\n".join(lines[i] for i in sorted(include))


def process_dataset(input_path: Path, output_path: Path, context: int):
    with open(input_path, encoding="utf-8") as f:
        dataset = json.load(f)

    output_records = []
    total_errors = 0
    total_warns = 0

    for record in dataset:
        log_id = record["log_id"]
        ground_truth = record.get("ground_truth", [])
        filtered_text = extract_error_warn_with_context(record["log_text"], context)

        error_count = min(1, len(re.findall(r"\]\s+ERROR\b", filtered_text)))
        warn_count = min(1, len(re.findall(r"\]\s+WARN\b", filtered_text)))
        total_errors += error_count
        total_warns += warn_count

        output_records.append(
            {
                "log_id": log_id,
                "log_text": filtered_text,
                "ground_truth": ground_truth,
            }
        )

    # 書き出し
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_records, f, ensure_ascii=False, indent=2)

    # サマリ表示
    print(f"Processed {len(dataset)} logs")
    print(f"  Total ERROR lines: {total_errors}")
    print(f"  Total WARN  lines: {total_warns}")
    print(f"  Context window   : ±{context} INFO lines")
    print(f"  Output           : {output_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=Path("data/sample_dataset.json"),
        help="入力 JSON パス (default: data/sample_dataset.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("data/extracted_errors.json"),
        help="出力 JSON パス (default: data/extracted_errors.json)",
    )
    parser.add_argument(
        "-c",
        "--context",
        type=int,
        default=CONTEXT_LINES,
        help=f"前後の INFO コンテキスト行数 (default: {CONTEXT_LINES})",
    )
    args = parser.parse_args()
    process_dataset(args.input, args.output, args.context)


if __name__ == "__main__":
    main()
