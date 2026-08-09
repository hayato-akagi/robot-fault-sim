"""正解ラベル CSV を追記出力する。"""

import csv
from pathlib import Path


class LabelWriter:
    HEADER = ["log_id", "label", "fault_type", "fault_phase", "episode_result"]

    def __init__(self, labels_path: str):
        # 常に新規作成（追記しない）。trials/ 側は同じ log_id のディレクトリを
        # 都度上書きするだけなので、labels.csv が追記のままだと、件数を変えて
        # 実行し直したときに前回分の行が残って重複・不整合を起こす
        # （trials/ には無い log_id の行が labels.csv にだけ残る等）。
        # 1回の実行で作られる trials/ と labels.csv が常に1:1対応するようにする。
        self.path = Path(labels_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", newline="") as f:
            csv.writer(f).writerow(self.HEADER)

    def write(self, log_id: str, label: str, fault_type: str,
              fault_phase: str, episode_result: str):
        with open(self.path, "a", newline="") as f:
            csv.writer(f).writerow(
                [log_id, label, fault_type, fault_phase, episode_result]
            )
