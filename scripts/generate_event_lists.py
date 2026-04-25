#!/usr/bin/env python3
"""センサーイベント定義から WARNING/ERROR 一覧ファイルを生成する。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.monitoring.sensor import EVENT_DEFINITIONS

OUT_PATH = ROOT / "output" / "dataset" / "docs" / "system_warning_error_list.md"


def collect(level: str) -> list[tuple[str, str, str]]:
    rows = []
    for event_type, info in EVENT_DEFINITIONS.items():
        if info.get("level") == level:
            rows.append((info.get("code", ""), event_type, info.get("summary", "")))
    rows.sort(key=lambda x: x[0])
    return rows


def to_table(rows: list[tuple[str, str, str]]) -> str:
    lines = [
        "| Code | Event Type | Summary |",
        "|---|---|---|",
    ]
    for code, event_type, summary in rows:
        lines.append(f"| {code} | {event_type} | {summary} |")
    return "\n".join(lines)


def main() -> None:
    warns = collect("WARN")
    errors = collect("ERROR")

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join([
        "# System Warning/Error List",
        "",
        "このファイルは `src/monitoring/sensor.py` のイベント定義から自動生成されます。",
        "",
        "## WARNING List",
        "",
        to_table(warns),
        "",
        "## ERROR List",
        "",
        to_table(errors),
        "",
    ])
    OUT_PATH.write_text(content, encoding="utf-8")
    print(f"Wrote {OUT_PATH}")
    print(f"WARNING: {len(warns)} events, ERROR: {len(errors)} events")


if __name__ == "__main__":
    main()
