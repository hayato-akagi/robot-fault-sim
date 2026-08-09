"""
1試行分のログ群を2層構成で出力する。

構成（1試行 = 1ディレクトリ）:
  trial_dir/
  ├── controller/
  │   ├── main.log        中央コントローラログ（全コンポーネント横断・要約のみ）
  │   └── motion.csv      モーション時系列（手先位置・IK残差・制御周期）
  ├── components/
  │   ├── servo/
  │   │   ├── trace.csv   関節トルク・速度の時系列
  │   │   └── alarms.log  サーボ側アラーム詳細
  │   ├── gripper/
  │   │   └── events.log  グリッパイベント・把持力
  │   └── fieldbus/
  │       └── comm.log    センサ通信ステータス
  └── metadata.json       試行メタ情報（正解ラベルは含めない）

中央ログの各行は [コンポーネントID] タグを持ち、同一アラームは
初回のみ記録して以降はラッチ（詳細は各コンポーネントログ側に全件残る）。
"""

import csv
import datetime
import json
import zipfile
from pathlib import Path

from src.simulation.kuka_sim import StepRecord
from src.monitoring.sensor import SensorEvent


# event_type → 発生元コンポーネント
EVENT_SOURCE = {
    "joint_torque_overload":   "servo",
    "axis_stiction_suspected": "servo",
    "encoder_deviation":       "servo",
    "grip_force_degraded":     "gripper",
    "grip_force_insufficient": "gripper",
    "grip_lost_during_transport": "gripper",
    "sensor_packet_timeout":   "fieldbus",
    "control_loop_overrun":    "controller",
    "ik_divergence":           "controller",
    "ik_position_error":       "controller",
}

UNIT_TAG = {
    "servo":      "SRV-01",
    "gripper":    "GRP-01",
    "fieldbus":   "BUS-01",
    "controller": "CTRL",
}

COMPONENT_DESCRIPTIONS = {
    "CTRL":   "Central motion controller (sequence, IK, real-time loop)",
    "SRV-01": "Servo amplifier unit, axes J1-J7 (tags SRV-J1..SRV-J7 per axis)",
    "GRP-01": "2-finger gripper actuator",
    "BUS-01": "Sensor fieldbus interface (joint state packets)",
}

HEARTBEAT_STEPS = 100   # 中央ログの生存確認間隔
SAMPLE_STEPS    = 20    # コンポーネントログの定期記録間隔


class TrialLogger:
    BASE_TIME = datetime.datetime(2024, 1, 15, 10, 0, 0)
    STEP_MS = 4  # 240Hz

    def write_trial(self, trial_dir: Path, records: list[StepRecord],
                    events: list[SensorEvent], episode_result: str,
                    trial_id: str) -> None:
        trial_dir = Path(trial_dir)
        (trial_dir / "controller").mkdir(parents=True, exist_ok=True)
        for comp in ("servo", "gripper", "fieldbus"):
            (trial_dir / "components" / comp).mkdir(parents=True, exist_ok=True)

        self._write_main_log(trial_dir, records, events, episode_result, trial_id)
        self._write_motion_csv(trial_dir, records)
        self._write_servo_trace(trial_dir, records)
        self._write_servo_alarms(trial_dir, events)
        self._write_gripper_events(trial_dir, records, events)
        self._write_fieldbus_comm(trial_dir, records, events)
        self._write_metadata(trial_dir, records, trial_id)
        self._write_zip_archive(trial_dir, trial_id)

    # ------------------------------------------------------------------
    # trials/<trial_id>.zip（trial_dir と同じ階層に、中身一式をまとめる）
    # ------------------------------------------------------------------
    def _write_zip_archive(self, trial_dir: Path, trial_id: str) -> None:
        zip_path = trial_dir.parent / f"{trial_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(trial_dir.rglob("*")):
                if path.is_file():
                    zf.write(path, arcname=f"{trial_id}/{path.relative_to(trial_dir)}")

    # ------------------------------------------------------------------
    # 中央コントローラログ
    # ------------------------------------------------------------------
    def _write_main_log(self, trial_dir: Path, records: list[StepRecord],
                        events: list[SensorEvent], episode_result: str,
                        trial_id: str) -> None:
        lines = []
        lines.append(self._fmt(0, "CTRL", "INFO",
            f"Sequence start: trial_id={trial_id} task=pick_and_place "
            f"robot=Kuka_IIWA units={','.join(UNIT_TAG.values())}"
        ))

        # 時系列マージ用に (t, 順序, 行) を集めてからソートする
        timeline: list[tuple[int, int, str]] = []

        prev_phase = None
        for r in records:
            if r.phase != prev_phase:
                timeline.append((r.t, 0, self._fmt(r.t * self.STEP_MS, "CTRL", "INFO",
                    f"SEQ-PHASE phase={r.phase} t={r.t}")))
                prev_phase = r.phase
            if r.t % HEARTBEAT_STEPS == 0:
                ee = ("N/A" if r.sensor_missing else
                      f"[{r.ee_pos[0]:.3f},{r.ee_pos[1]:.3f},{r.ee_pos[2]:.3f}]")
                timeline.append((r.t, 1, self._fmt(r.t * self.STEP_MS, "CTRL", "INFO",
                    f"SYS-HB t={r.t} phase={r.phase} ee={ee} "
                    f"loop={r.loop_period_ms:.1f}ms")))

        # アラームは (タグ, コード) 単位でラッチ: 初回のみ記録、以降はカウント
        latched: dict[tuple[str, str], int] = {}
        for ev in events:
            if ev.level not in ("WARN", "ERROR"):
                continue
            tag = self._event_tag(ev)
            key = (tag, ev.code)
            if key in latched:
                latched[key] += 1
                continue
            latched[key] = 1
            timeline.append((ev.t, 2, self._fmt(ev.t * self.STEP_MS, tag, ev.level,
                f"{ev.code} {ev.message} (latched; see component log for repeats)")))

        timeline.sort(key=lambda x: (x[0], x[1]))
        lines += [line for _, _, line in timeline]

        end_t = (records[-1].t if records else 0) * self.STEP_MS
        for (tag, code), count in sorted(latched.items()):
            lines.append(self._fmt(end_t, "CTRL", "INFO",
                f"ALM-SUMMARY src={tag} code={code} count={count}"))

        n_alarms = sum(latched.values())
        end_level = "INFO" if episode_result == "success" else "ERROR"
        lines.append(self._fmt(end_t, "CTRL", end_level,
            f"Sequence end: result={episode_result} alarm_events={n_alarms}"))

        (trial_dir / "controller" / "main.log").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def _event_tag(self, ev: SensorEvent) -> str:
        source = EVENT_SOURCE.get(ev.event_type, "controller")
        if source == "servo":
            axis = ev.values.get("axis")
            if axis:
                return f"SRV-{axis}"
        return UNIT_TAG[source]

    # ------------------------------------------------------------------
    # controller/motion.csv
    # ------------------------------------------------------------------
    def _write_motion_csv(self, trial_dir: Path, records: list[StepRecord]) -> None:
        path = trial_dir / "controller" / "motion.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "timestamp", "phase",
                        "ee_x", "ee_y", "ee_z",
                        "target_x", "target_y", "target_z",
                        "ik_residual_m", "loop_period_ms"])
            for r in records:
                w.writerow([r.t, self._ts(r.t), r.phase,
                            *(f"{v:.4f}" for v in r.ee_pos),
                            *(f"{v:.4f}" for v in r.target_pos),
                            f"{r.ik_residual:.4f}", f"{r.loop_period_ms:.2f}"])

    # ------------------------------------------------------------------
    # components/servo/
    # ------------------------------------------------------------------
    def _write_servo_trace(self, trial_dir: Path, records: list[StepRecord]) -> None:
        path = trial_dir / "components" / "servo" / "trace.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["t", "timestamp", "phase",
                        *(f"torque_J{i}" for i in range(1, 8)),
                        *(f"vel_J{i}" for i in range(1, 8)),
                        "encoder_noise_rms"])
            for r in records:
                if r.sensor_missing:
                    # センサ欠損中は値なし（フィールドバス断のため）
                    w.writerow([r.t, self._ts(r.t), r.phase] + [""] * 15)
                    continue
                w.writerow([r.t, self._ts(r.t), r.phase,
                            *(f"{v:.3f}" for v in r.joint_torques),
                            *(f"{v:.4f}" for v in r.joint_velocities),
                            f"{r.encoder_noise_rms:.4f}"])

    def _write_servo_alarms(self, trial_dir: Path, events: list[SensorEvent]) -> None:
        lines = []
        for ev in events:
            if EVENT_SOURCE.get(ev.event_type) != "servo":
                continue
            lines.append(self._fmt(ev.t * self.STEP_MS, self._event_tag(ev),
                                   ev.level, f"{ev.code} {ev.message}"))
            lines.append(self._fmt(ev.t * self.STEP_MS, self._event_tag(ev),
                                   ev.level,
                                   f"DIAG code={ev.code} type={ev.event_type} "
                                   f"phase={ev.phase} values={ev.values}"))
        (trial_dir / "components" / "servo" / "alarms.log").write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    # ------------------------------------------------------------------
    # components/gripper/events.log
    # ------------------------------------------------------------------
    def _write_gripper_events(self, trial_dir: Path, records: list[StepRecord],
                              events: list[SensorEvent]) -> None:
        timeline: list[tuple[int, int, str]] = []

        prev_cmd = None
        for r in records:
            cmd = "open" if r.gripper_val == 1 else "close"
            if cmd != prev_cmd:
                timeline.append((r.t, 0, self._fmt(r.t * self.STEP_MS, "GRP-01", "INFO",
                    f"CMD-{cmd.upper()} t={r.t} phase={r.phase}")))
                prev_cmd = cmd
            if r.t % SAMPLE_STEPS == 0:
                timeline.append((r.t, 1, self._fmt(r.t * self.STEP_MS, "GRP-01", "INFO",
                    f"STAT t={r.t} state={cmd} force={r.grip_force_actual:.1f}N")))

        for ev in events:
            if EVENT_SOURCE.get(ev.event_type) != "gripper":
                continue
            timeline.append((ev.t, 2, self._fmt(ev.t * self.STEP_MS, "GRP-01",
                ev.level, f"{ev.code} {ev.message} values={ev.values}")))

        timeline.sort(key=lambda x: (x[0], x[1]))
        (trial_dir / "components" / "gripper" / "events.log").write_text(
            "\n".join(line for _, _, line in timeline) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # components/fieldbus/comm.log
    # ------------------------------------------------------------------
    def _write_fieldbus_comm(self, trial_dir: Path, records: list[StepRecord],
                             events: list[SensorEvent]) -> None:
        timeline: list[tuple[int, int, str]] = []

        for r in records:
            if r.t % SAMPLE_STEPS == 0:
                status = "TIMEOUT" if r.sensor_missing else "OK"
                level = "WARN" if r.sensor_missing else "INFO"
                timeline.append((r.t, 0, self._fmt(r.t * self.STEP_MS, "BUS-01", level,
                    f"PKT-STAT t={r.t} link={status}")))

        for ev in events:
            if EVENT_SOURCE.get(ev.event_type) != "fieldbus":
                continue
            timeline.append((ev.t, 1, self._fmt(ev.t * self.STEP_MS, "BUS-01",
                ev.level, f"{ev.code} {ev.message} values={ev.values}")))

        timeline.sort(key=lambda x: (x[0], x[1]))
        (trial_dir / "components" / "fieldbus" / "comm.log").write_text(
            "\n".join(line for _, _, line in timeline) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    # metadata.json
    # ------------------------------------------------------------------
    def _write_metadata(self, trial_dir: Path, records: list[StepRecord],
                        trial_id: str) -> None:
        meta = {
            "trial_id": trial_id,
            "task": "pick_and_place",
            "robot": "Kuka_IIWA",
            "start_time": self.BASE_TIME.isoformat(),
            "total_steps": records[-1].t + 1 if records else 0,
            "step_period_ms": self.STEP_MS,
            "components": COMPONENT_DESCRIPTIONS,
            "files": {
                "controller/main.log": "Central controller log (component-tagged, alarms latched)",
                "controller/motion.csv": "Motion time series (EE pos, IK residual, loop period)",
                "components/servo/trace.csv": "Joint torque/velocity time series",
                "components/servo/alarms.log": "Servo alarm details (all repeats)",
                "components/gripper/events.log": "Gripper commands, force readings, events",
                "components/fieldbus/comm.log": "Sensor packet link status",
            },
        }
        (trial_dir / "metadata.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # ------------------------------------------------------------------
    def _ts(self, t: int) -> str:
        ts = self.BASE_TIME + datetime.timedelta(milliseconds=t * self.STEP_MS)
        return ts.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def _fmt(self, offset_ms: int, tag: str, level: str, message: str) -> str:
        ts = self.BASE_TIME + datetime.timedelta(milliseconds=offset_ms)
        return (f"[{ts.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] "
                f"[{tag:<6}] {level:<5} {message}")
