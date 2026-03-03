"""
SensorEvent リストを experiment-classifier 向けテキストログに変換する。
"""

import datetime
from src.monitoring.sensor import SensorEvent


class LogGenerator:
    BASE_TIME = datetime.datetime(2024, 1, 15, 10, 0, 0)

    def generate(self, events: list[SensorEvent], episode_result: str,
                 fault_type: str, log_id: str) -> str:
        lines = []

        lines.append(self._fmt(0, "INFO",
            f"Episode start: log_id={log_id} task=pick_and_place "
            f"fault_type={fault_type} robot=Kuka_IIWA total_steps=750"
        ))

        for ev in events:
            offset_ms = ev.t * 4  # 240Hz → ms換算
            lines.append(self._fmt(offset_ms, ev.level, ev.message))

            # ERROR は診断詳細行を追加（LLMが拾いやすいように）
            if ev.level == "ERROR":
                lines.append(self._fmt(offset_ms, "ERROR",
                    f"FAULT DETECTED: {ev.event_type} "
                    f"category={ev.category} phase={ev.phase} "
                    f"values={ev.values}"
                ))

        n_errors = sum(1 for e in events if e.level == "ERROR")
        n_warns  = sum(1 for e in events if e.level == "WARN")
        end_level = "INFO" if episode_result == "success" else "ERROR"
        lines.append(self._fmt(750 * 4, end_level,
            f"Episode end: result={episode_result} fault_type={fault_type} "
            f"errors={n_errors} warnings={n_warns}"
        ))

        return "\n".join(lines)

    def _fmt(self, offset_ms: int, level: str, message: str) -> str:
        ts = self.BASE_TIME + datetime.timedelta(milliseconds=offset_ms)
        return f"[{ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {level:<5} {message}"
