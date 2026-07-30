"""
パイプライン。

同じKukaSimを fault_params だけ変えて実行する:
  normal     → {}
  mechanical → grip_force=35, joint_friction=5.0
  electrical → encoder_noise_std=0.08, sensor_missing_prob=0.03
  software   → loop_delay_ms=28, ik_target_noise=0.15
"""

import shutil
from pathlib import Path

from src.simulation.kuka_sim import KukaSim
from src.monitoring.sensor import SensorMonitor
from src.monitoring.trial_logger import TrialLogger
from src.monitoring.label_writer import LabelWriter
from src.visualization.gif_renderer import GifRenderer


FAULT_PARAMS = {
    "normal": {},

    # デバッグ用: 案1（グリッパパッド摩耗）のみ
    "mechanical": {
        "gripper_friction": 0.05,
        "grip_force": 3,            # 極端に低い → 閉じ切れず把持失敗
        "joint_friction": 1.0,
    },

    # 本番用: 4種類のmechanical故障を均等に生成
    "mechanical_variants": [
        {   # 案1: グリッパパッド摩耗（grip_forceも下げてslipを確実に起こす）
            "label": "mechanical_pad_wear",
            "gripper_friction": 0.05,
            "grip_force": 3,
            "joint_friction": 1.0,
        },
        {   # 案2: 関節ベアリング劣化
            "label": "mechanical_bearing",
            "gripper_friction": 2.0,
            "grip_force": 100,
            "joint_friction": 8.0,
        },
        {   # 案3: グリッパアクチュエータ劣化
            "label": "mechanical_actuator",
            "gripper_friction": 2.0,
            "grip_force": 3,
            "joint_friction": 1.0,
        },
        {   # 案4: 複合故障
            "label": "mechanical_combined",
            "gripper_friction": 0.2,
            "grip_force": 3,
            "joint_friction": 3.0,
        },
    ],

    "electrical": {
        "encoder_noise_std": 0.08,
        "sensor_missing_prob": 0.08,
        "sensor_missing_steps": 10,
    },
    "software": {
        "loop_delay_ms": 28.0,
        "ik_target_noise": 0.40,
    },
}


class SimulationPipeline:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.monitor = SensorMonitor(cfg)
        self.trial_logger = TrialLogger()
        self.gif_renderer = GifRenderer(cfg)

        out = cfg["output"]
        Path(out["trials_dir"]).mkdir(parents=True, exist_ok=True)
        Path(out["docs_dir"]).mkdir(parents=True, exist_ok=True)
        Path(out["viz_dir"]).mkdir(parents=True, exist_ok=True)

        self.label_writer = LabelWriter(out["labels_file"])

    def run_episode(self, log_id: str, fault_type: str,
                    save_gif: bool = False,
                    fault_params_override: dict = None) -> dict:
        fault_params = fault_params_override or FAULT_PARAMS.get(fault_type, {})
        # バリアントのlabelをfault_typeのサブカテゴリとして使用
        effective_label = fault_params.get("label", fault_type)
        sim = KukaSim(fault_params=fault_params)

        try:
            sim.setup()
            records, episode_result = sim.run(save_frames=save_gif)
        finally:
            sim.close()

        # GIF保存
        if save_gif:
            rgb_frames = [r.rgb_frame for r in records if r.rgb_frame is not None]
            if rgb_frames:
                self.gif_renderer.save(rgb_frames, f"{log_id}_{fault_type}.gif")

        # センサ解析 → イベント抽出
        events = self.monitor.analyze(records, fault_type)

        # 試行ディレクトリへログ群を保存（2層構成）
        trial_dir = Path(self.cfg["output"]["trials_dir"]) / log_id
        self.trial_logger.write_trial(
            trial_dir, records, events, episode_result, log_id)

        # ラベル保存
        fault_phases = sorted({
            ev.phase for ev in events if ev.level in ("WARN", "ERROR")
        })
        self.label_writer.write(
            log_id=log_id,
            label=effective_label,
            fault_type=fault_type if fault_type != "normal" else "none",
            fault_phase=",".join(fault_phases) or "none",
            episode_result=episode_result,
        )

        return {
            "log_id": log_id,
            "fault_type": fault_type,
            "result": episode_result,
            "n_events": len(events),
            "n_errors": sum(1 for e in events if e.level == "ERROR"),
            "records": records,  # PlotRenderer用
        }

    def export_spec_doc(self):
        src = Path("specs/robot_arm_spec.md")
        dst = Path(self.cfg["output"]["docs_dir"]) / "robot_arm_spec.txt"
        if src.exists():
            shutil.copy(src, dst)
            print(f"  Spec doc exported: {dst}")
