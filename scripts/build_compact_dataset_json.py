#!/usr/bin/env python3
"""sample_dataset.json の log_text から重要行をルールベース抽出して短縮版を作る。"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = ROOT / "data" / "sample_dataset.json"
DEFAULT_OUTPUT = ROOT / "data" / "sample_dataset_compact.json"

PHASE_RE = re.compile(r"phase=([A-Z_]+)")
LOOP_RE = re.compile(r"loop=([0-9]+(?:\.[0-9]+)?)ms")
IK_RE = re.compile(r"ik_residual=([0-9]+(?:\.[0-9]+)?)m?")
GRIP_RE = re.compile(r"grip_force=([0-9]+(?:\.[0-9]+)?)N")

# エラー・異常を示す語を網羅（大文字小文字は無視）
IMPORTANT_TERMS = [
    "error", "warn", "warning", "fault", "failed", "failure", "timeout",
    "overrun", "divergence", "deviation", "drop", "signal_loss",
    "packet", "blackout", "trip", "overload", "collision", "exceeded",
]


def is_important_text(line: str) -> bool:
    lower = line.lower()
    return any(term in lower for term in IMPORTANT_TERMS)


def extract_important_lines(
    log_text: str,
    ik_threshold: float,
    loop_threshold_ms: float,
    grip_threshold_n: float,
    keep_context: int,
    max_lines: int,
) -> str:
    lines = [ln for ln in log_text.splitlines() if ln.strip()]
    if not lines:
        return ""

    selected_idx: set[int] = set()
    seen_phases: set[str] = set()

    for i, line in enumerate(lines):
        lower = line.lower()

        # 1) エピソード境界は必ず保持
        if "episode start" in lower or "episode end" in lower:
            selected_idx.add(i)

        # 2) WARN/ERROR/FAULT などキーワードを含む行
        if is_important_text(line):
            selected_idx.add(i)

        # 3) 各フェーズの最初の1行を保持（流れの要約）
        phase_match = PHASE_RE.search(line)
        if phase_match:
            phase = phase_match.group(1)
            if phase not in seen_phases:
                selected_idx.add(i)
                seen_phases.add(phase)

        # 4) 閾値ベース抽出
        loop_match = LOOP_RE.search(line)
        if loop_match and float(loop_match.group(1)) > loop_threshold_ms:
            selected_idx.add(i)

        ik_match = IK_RE.search(line)
        if ik_match and float(ik_match.group(1)) > ik_threshold:
            selected_idx.add(i)

        grip_match = GRIP_RE.search(line)
        if grip_match and float(grip_match.group(1)) < grip_threshold_n:
            selected_idx.add(i)

    # 5) 文脈を残すため、前後行を追加
    if keep_context > 0:
        expanded: set[int] = set()
        for idx in selected_idx:
            start = max(0, idx - keep_context)
            end = min(len(lines) - 1, idx + keep_context)
            expanded.update(range(start, end + 1))
        selected_idx = expanded

    ordered = [lines[i] for i in sorted(selected_idx)]

    # 6) 長すぎる場合は頭・中・末尾をバランス保持
    if max_lines > 0 and len(ordered) > max_lines:
        head = max_lines // 2
        tail = max_lines - head
        omitted = len(ordered) - max_lines
        ordered = (
            ordered[:head]
            + [f"... ({omitted} important lines omitted) ..."]
            + ordered[-tail:]
        )

    return "\n".join(ordered)


def build_compact_dataset(
    input_path: Path,
    output_path: Path,
    ik_threshold: float,
    loop_threshold_ms: float,
    grip_threshold_n: float,
    keep_context: int,
    max_lines: int,
) -> tuple[int, int, int]:
    data = json.loads(input_path.read_text(encoding="utf-8"))

    compact_data = []
    before_total_lines = 0
    after_total_lines = 0

    for row in data:
        original = row.get("log_text", "")
        compact = extract_important_lines(
            log_text=original,
            ik_threshold=ik_threshold,
            loop_threshold_ms=loop_threshold_ms,
            grip_threshold_n=grip_threshold_n,
            keep_context=keep_context,
            max_lines=max_lines,
        )

        before_total_lines += len([ln for ln in original.splitlines() if ln.strip()])
        after_total_lines += len([ln for ln in compact.splitlines() if ln.strip()])

        compact_row = {
            "log_id": row.get("log_id"),
            "log_text": compact,
            "ground_truth": row.get("ground_truth", []),
        }
        compact_data.append(compact_row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(compact_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return len(compact_data), before_total_lines, after_total_lines


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="sample_dataset.json から重要行のみ抽出した短縮版を作る"
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--ik-threshold", type=float, default=0.10)
    parser.add_argument("--loop-threshold-ms", type=float, default=25.0)
    parser.add_argument("--grip-threshold-n", type=float, default=3.5)
    parser.add_argument("--keep-context", type=int, default=0)
    parser.add_argument("--max-lines", type=int, default=40)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    count, before_lines, after_lines = build_compact_dataset(
        input_path=args.input,
        output_path=args.output,
        ik_threshold=args.ik_threshold,
        loop_threshold_ms=args.loop_threshold_ms,
        grip_threshold_n=args.grip_threshold_n,
        keep_context=args.keep_context,
        max_lines=args.max_lines,
    )

    ratio = 0.0
    if before_lines > 0:
        ratio = (after_lines / before_lines) * 100

    print(f"Wrote {count} records -> {args.output}")
    print(f"Lines: {before_lines} -> {after_lines} ({ratio:.1f}% retained)")


if __name__ == "__main__":
    main()
