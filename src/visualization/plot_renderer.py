"""センサ時系列グラフを PNG で保存する（論文 Figure 用）。"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path
from src.simulation.kuka_sim import StepRecord


FAULT_COLORS = {
    "mechanical": "#e74c3c",
    "electrical": "#f39c12",
    "software":   "#3498db",
    "normal":     "#2ecc71",
}

PHASE_ORDER = ["APPROACH", "GRASP", "LIFT", "MOVE", "HOLD", "RELEASE"]


class PlotRenderer:
    def __init__(self, cfg: dict):
        self.spec = cfg["robot_spec"]
        self.out_dir = Path(cfg["output"]["viz_dir"])
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def save_sensor_overview(
        self,
        histories: dict[str, list[StepRecord]],
        filename: str = "sensor_overview.png",
    ) -> str:
        fig, axes = plt.subplots(2, 2, figsize=(14, 8))
        fig.suptitle("Sensor Time Series by Fault Type", fontsize=12, fontweight="bold")

        for ax, (fault_type, records) in zip(axes.flatten(), histories.items()):
            self._plot_single(ax, records, fault_type)

        plt.tight_layout()
        path = self.out_dir / filename
        plt.savefig(str(path), dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Plot saved: {path}")
        return str(path)

    def save_fault_comparison(
        self,
        histories: dict[str, list[StepRecord]],
        filename: str = "fault_comparison.png",
    ) -> str:
        types = list(histories.keys())
        colors = [FAULT_COLORS.get(t, "#95a5a6") for t in types]
        fig, axes = plt.subplots(1, 3, figsize=(14, 4))
        fig.suptitle("Fault Type Comparison: Key Metrics", fontsize=12, fontweight="bold")

        metrics = [
            ("Peak Torque", lambda rs: max(
                max(r.joint_torques) for r in rs if not r.sensor_missing
            ) if rs else 0),
            ("Peak Loop (ms)", lambda rs: max(r.loop_period_ms for r in rs) if rs else 0),
            ("Peak IK Residual", lambda rs: max(r.ik_residual for r in rs) if rs else 0),
        ]

        for ax, (label, fn) in zip(axes, metrics):
            values = [fn(histories[t]) for t in types]
            bars = ax.bar(types, values, color=colors, alpha=0.8, edgecolor="white")
            ax.set_title(label, fontsize=10)
            for bar, val in zip(bars, values):
                ax.text(bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + 0.01,
                        f"{val:.1f}", ha="center", va="bottom", fontsize=8)

        plt.tight_layout()
        path = self.out_dir / filename
        plt.savefig(str(path), dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Plot saved: {path}")
        return str(path)

    def _plot_single(self, ax, records: list[StepRecord], fault_type: str):
        color = FAULT_COLORS.get(fault_type, "#95a5a6")
        steps = [r.t for r in records]
        torques = [
            max(r.joint_torques) if not r.sensor_missing else 0
            for r in records
        ]
        ax.plot(steps, torques, color=color, linewidth=1.0)

        # フェーズ境界
        prev = None
        for r in records:
            if r.phase != prev:
                ax.axvline(x=r.t, color="#bdc3c7", linewidth=0.8, linestyle=":")
                ax.text(r.t + 1, ax.get_ylim()[1] * 0.9,
                        r.phase[:3], fontsize=6, color="#7f8c8d", rotation=90)
                prev = r.phase

        ax.set_title(f"[{fault_type.upper()}]", fontsize=11,
                     color=color, fontweight="bold")
        ax.set_xlabel("Step", fontsize=8)
        ax.set_ylabel("Peak Torque", fontsize=8)
        ax.tick_params(labelsize=7)
