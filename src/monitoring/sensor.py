"""
StepRecord を解析してイベントログを生成する。

検出ロジック（カテゴリ別）:
- Mechanical: GRASP中の grip_force_actual が閾値未満
- Electrical: encoder_noise_rms > 閾値 / sensor_missing=True
- Software:   loop_period_ms > 25ms / ik_residual > 0.25m
"""

import math
import numpy as np
from dataclasses import dataclass
from src.simulation.kuka_sim import StepRecord


LOOP_LIMIT_MS      = 25.0
IK_RESIDUAL_WARN   = 0.15
IK_RESIDUAL_ERR    = 0.25
ENCODER_TOL_RAD    = 0.05
GRIP_FORCE_WARN    = 60.0   # 正常=100N
GRIP_FORCE_ERR     = 5.0    # 2Nをキャッチ


@dataclass
class SensorEvent:
    t: int
    phase: str
    level: str          # INFO / WARN / ERROR
    category: str       # mechanical / electrical / software / normal
    event_type: str
    message: str
    values: dict


class SensorMonitor:
    def __init__(self, cfg: dict):
        self.spec = cfg["robot_spec"]

    def analyze(self, records: list[StepRecord], fault_type: str = "normal"
                ) -> list[SensorEvent]:
        events: list[SensorEvent] = []
        for r in records:
            events += self._check_mechanical(r)
            events += self._check_electrical(r)
            events += self._check_software(r)
            if r.t % 20 == 0:
                events += self._emit_info(r)
        return events

    # ------------------------------------------------------------------
    def _check_mechanical(self, r: StepRecord) -> list[SensorEvent]:
        """グリップ力を監視。GRASPフェーズで把持しようとしているときのみチェック。"""
        if r.phase not in ("GRASP", "LIFT", "MOVE", "HOLD"):
            return []

        evs = []
        force = r.grip_force_actual

        if r.phase == "GRASP" and r.gripper_val == 1:
            if force < GRIP_FORCE_ERR:
                evs.append(SensorEvent(
                    t=r.t, phase=r.phase, level="ERROR",
                    category="mechanical",
                    event_type="grip_force_insufficient",
                    message=(
                        f"Gripper force critical at t={r.t} phase={r.phase}: "
                        f"actual={force:.1f}N < threshold={GRIP_FORCE_ERR:.0f}N. "
                        f"Object grasp failed. Possible actuator degradation."
                    ),
                    values={"grip_force_actual": round(force, 2),
                            "threshold": GRIP_FORCE_ERR,
                            "gripper_val": r.gripper_val},
                ))
            elif force < GRIP_FORCE_WARN:
                evs.append(SensorEvent(
                    t=r.t, phase=r.phase, level="WARN",
                    category="mechanical",
                    event_type="grip_force_degraded",
                    message=(
                        f"Gripper force degraded at t={r.t} phase={r.phase}: "
                        f"actual={force:.1f}N < nominal={GRIP_FORCE_WARN:.0f}N. "
                        f"Grasp reliability reduced."
                    ),
                    values={"grip_force_actual": round(force, 2),
                            "nominal": GRIP_FORCE_WARN},
                ))

        # LIFT/MOVE/HOLDでグリップ力が低い = 把持が外れている
        if r.phase in ("LIFT", "MOVE", "HOLD") and r.gripper_val == 1:
            if force < GRIP_FORCE_ERR:
                evs.append(SensorEvent(
                    t=r.t, phase=r.phase, level="ERROR",
                    category="mechanical",
                    event_type="grip_lost_during_transport",
                    message=(
                        f"Grip lost during transport at t={r.t} phase={r.phase}: "
                        f"force={force:.1f}N. Object drop likely."
                    ),
                    values={"grip_force_actual": round(force, 2),
                            "phase": r.phase},
                ))
        return evs

    # ------------------------------------------------------------------
    def _check_electrical(self, r: StepRecord) -> list[SensorEvent]:
        evs = []

        if r.sensor_missing:
            evs.append(SensorEvent(
                t=r.t, phase=r.phase, level="ERROR",
                category="electrical",
                event_type="sensor_packet_timeout",
                message=(
                    f"Sensor communication blackout at t={r.t} phase={r.phase}. "
                    f"No joint state packet within "
                    f"{self.spec['sensor_timeout_ms']:.0f}ms threshold. "
                    f"Possible cable fault or EMI."
                ),
                values={"t": r.t, "phase": r.phase,
                        "timeout_ms": self.spec["sensor_timeout_ms"]},
            ))
            return evs

        if r.encoder_noise_rms > ENCODER_TOL_RAD:
            evs.append(SensorEvent(
                t=r.t, phase=r.phase, level="WARN",
                category="electrical",
                event_type="encoder_deviation",
                message=(
                    f"Encoder signal anomaly at t={r.t} phase={r.phase}: "
                    f"noise_rms={r.encoder_noise_rms:.4f}rad "
                    f"exceeds tolerance={ENCODER_TOL_RAD}rad. "
                    f"Possible sensor degradation or EMI interference."
                ),
                values={"noise_rms": round(r.encoder_noise_rms, 4),
                        "tolerance_rad": ENCODER_TOL_RAD},
            ))

        return evs

    # ------------------------------------------------------------------
    def _check_software(self, r: StepRecord) -> list[SensorEvent]:
        evs = []

        if r.loop_period_ms > LOOP_LIMIT_MS:
            evs.append(SensorEvent(
                t=r.t, phase=r.phase, level="WARN",
                category="software",
                event_type="control_loop_overrun",
                message=(
                    f"Control loop overrun at t={r.t} phase={r.phase}: "
                    f"period={r.loop_period_ms:.1f}ms "
                    f"exceeds limit={LOOP_LIMIT_MS:.1f}ms "
                    f"({r.loop_period_ms/LOOP_LIMIT_MS*100:.0f}% of limit). "
                    f"Real-time constraint violated."
                ),
                values={"period_ms": round(r.loop_period_ms, 2),
                        "limit_ms": LOOP_LIMIT_MS},
            ))

        if r.ik_residual > IK_RESIDUAL_ERR and r.phase not in ("APPROACH",):
            evs.append(SensorEvent(
                t=r.t, phase=r.phase, level="ERROR",
                category="software",
                event_type="ik_divergence",
                message=(
                    f"IK divergence at t={r.t} phase={r.phase}: "
                    f"residual={r.ik_residual:.4f}m "
                    f"exceeds threshold={IK_RESIDUAL_ERR:.4f}m. "
                    f"Trajectory planning failure."
                ),
                values={"residual": round(r.ik_residual, 4),
                        "threshold": IK_RESIDUAL_ERR},
            ))
        elif r.ik_residual > IK_RESIDUAL_WARN and r.phase not in ("APPROACH",):
            evs.append(SensorEvent(
                t=r.t, phase=r.phase, level="WARN",
                category="software",
                event_type="ik_position_error",
                message=(
                    f"IK position error at t={r.t} phase={r.phase}: "
                    f"residual={r.ik_residual:.4f}m "
                    f"exceeds warning threshold={IK_RESIDUAL_WARN:.4f}m."
                ),
                values={"residual": round(r.ik_residual, 4)},
            ))

        return evs

    # ------------------------------------------------------------------
    def _emit_info(self, r: StepRecord) -> list[SensorEvent]:
        if r.sensor_missing:
            torque_str = "N/A (sensor missing)"
            pos_str = "N/A"
        else:
            torques = {f"J{i+1}": round(v, 2)
                       for i, v in enumerate(r.joint_torques)}
            torque_str = str(torques)
            pos_str = f"[{r.ee_pos[0]:.3f},{r.ee_pos[1]:.3f},{r.ee_pos[2]:.3f}]"

        return [SensorEvent(
            t=r.t, phase=r.phase, level="INFO",
            category="normal",
            event_type="periodic_status",
            message=(
                f"t={r.t} phase={r.phase} "
                f"ee={pos_str} "
                f"ik_residual={r.ik_residual:.3f}m "
                f"grip={'open' if r.gripper_val == 1 else 'closed'} "
                f"grip_force={r.grip_force_actual:.1f}N "
                f"loop={r.loop_period_ms:.1f}ms "
                f"torques={torque_str}"
            ),
            values={
                "t": r.t, "phase": r.phase,
                "ee_pos": r.ee_pos,
                "ik_residual": round(r.ik_residual, 4),
                "loop_ms": round(r.loop_period_ms, 2),
                "grip_force": round(r.grip_force_actual, 2),
            },
        )]
