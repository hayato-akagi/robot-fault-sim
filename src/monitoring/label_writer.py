"""正解ラベル CSV を追記出力する。"""

import csv
from pathlib import Path


class LabelWriter:
    HEADER = ["log_id", "label", "fault_type", "fault_phase", "episode_result"]

    def __init__(self, labels_path: str):
        self.path = Path(labels_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with open(self.path, "w", newline="") as f:
                csv.writer(f).writerow(self.HEADER)

    def write(self, log_id: str, label: str, fault_type: str,
              fault_phase: str, episode_result: str):
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(
                [log_id, label, fault_type, fault_phase, episode_result]
            )
