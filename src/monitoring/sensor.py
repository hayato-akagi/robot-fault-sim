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

# 関節トルク超過アラームの閾値（軸ごと）。
#
# J2・J4（肩・肘）はアーム自重を支えるだけで通常時から数十Nmの保持トルクを要する
# （debug_episode で実測: J2 median≈53Nm p99≈110Nm、J4 median≈25Nm p99≈110Nm）。
# 旧値の一律 8.8Nm/6.6Nm はこれを大きく下回っており、normal を含む全カテゴリで
# ほぼ毎ステップ超過していた（ALM-JNT-OVR が故障の指標として機能していなかった
# バグ）。ここは正常時の実測レンジ（p99 + 余裕）まで引き上げ、software 故障時の
# 継続的な飽和（IKターゲットが暴れて全軸が定格上限に張り付く）とだけ区別できる
# ようにする。
JOINT_TORQUE_LIMITS_NM = [45.0, 130.0, 35.0, 180.0, 10.0, 25.0, 5.0]  # J1..J7

# 固着兆候（低速なのに高トルク）の閾値も同じ理由で見直し。旧値 5.5Nm は上記と
# 同じくアームの自重保持トルクを下回っており、HOLD 等の静止フェーズで
# ほぼ常時成立していた（実測: normal でも 750 ステップ中 138 回、mechanical と
# 同水準）。低速時の実測最大値（正常・mechanical とも約65〜70Nm）を上回る値まで
# 引き上げる。
AXIS_STICTION_TORQUE_NM = 110.0

# 現場ログ風の診断コード定義（ラベル名を直接含めない）
EVENT_DEFINITIONS = {
    # Mechanical-like
    "joint_torque_overload": {
        "level": "ERROR",
        "code": "ALM-JNT-OVR",
        "summary": "Joint torque exceeded alarm limit.",
    },
    "grip_force_degraded": {
        "level": "WARN",
        "code": "WRN-GRP-LOW",
        "summary": "Grip force dropped below nominal hold range.",
    },
    "grip_lost_during_transport": {
        "level": "ERROR",
        "code": "ALM-GRP-SLP",
        "summary": "Object holding became unstable during transfer.",
    },
    "axis_stiction_suspected": {
        "level": "WARN",
        "code": "WRN-AXS-STK",
        "summary": "Axis motion appears constrained under high load.",
    },
    # Electrical-like
    "sensor_packet_timeout": {
        "level": "ERROR",
        "code": "ALM-COM-TO",
        "summary": "Joint state packet timeout detected.",
    },
    "encoder_deviation": {
        "level": "WARN",
        "code": "WRN-ENC-DEV",
        "summary": "Encoder signal deviation exceeded tolerance.",
    },
    # Software-like
    "control_loop_overrun": {
        "level": "WARN",
        "code": "WRN-CTL-OVR",
        "summary": "Control loop period exceeded real-time budget.",
    },
    "ik_divergence": {
        "level": "ERROR",
        "code": "ALM-IK-DIV",
        "summary": "Inverse-kinematics residual diverged.",
    },
    "ik_position_error": {
        "level": "WARN",
        "code": "WRN-IK-RES",
        "summary": "Inverse-kinematics residual above warning threshold.",
    },
    # Periodic
    "periodic_status": {
        "level": "INFO",
        "code": "INF-STAT-20",
        "summary": "Periodic status snapshot.",
    },
}


def event_code(event_type: str) -> str:
    return EVENT_DEFINITIONS.get(event_type, {}).get("code", "INF-UNDEF")


@dataclass
class SensorEvent:
    t: int
    phase: str
    level: str          # INFO / WARN / ERROR
    category: str       # mechanical / electrical / software / normal
    event_type: str
    code: str
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

        # 関節トルク超過（軸ごとの実測ベース閾値、JOINT_TORQUE_LIMITS_NM 参照）
        for i, tq in enumerate(r.joint_torques):
            limit = JOINT_TORQUE_LIMITS_NM[i]
            if abs(tq) > limit:
                evs.append(SensorEvent(
                    t=r.t, phase=r.phase, level="ERROR",
                    category="mechanical",
                    event_type="joint_torque_overload",
                    code=event_code("joint_torque_overload"),
                    message=(
                        f"Joint load exceeded limit at axis=J{i+1}: "
                        f"torque={abs(tq):.2f}Nm > limit={limit:.2f}Nm "
                        f"during phase={r.phase}."
                    ),
                    values={
                        "axis": f"J{i+1}",
                        "torque_nm": round(abs(tq), 3),
                        "limit_nm": limit,
                        "phase": r.phase,
                    },
                ))

        # 固着兆候: 速度ほぼゼロ + トルク高負荷
        max_vel = max(abs(v) for v in r.joint_velocities) if r.joint_velocities else 0.0
        max_tq = max(abs(v) for v in r.joint_torques) if r.joint_torques else 0.0
        if r.phase in ("GRASP", "LIFT", "MOVE", "HOLD") and max_vel < 0.02 and max_tq > AXIS_STICTION_TORQUE_NM:
            axis_idx = int(np.argmax(np.abs(r.joint_torques))) if r.joint_torques else 0
            evs.append(SensorEvent(
                t=r.t, phase=r.phase, level="WARN",
                category="mechanical",
                event_type="axis_stiction_suspected",
                code=event_code("axis_stiction_suspected"),
                message=(
                    f"Axis response lag under load: axis=J{axis_idx+1} "
                    f"peak_torque={max_tq:.2f}Nm with near-zero velocity "
                    f"({max_vel:.3f}rad/s)."
                ),
                values={
                    "axis": f"J{axis_idx+1}",
                    "peak_torque_nm": round(max_tq, 3),
                    "max_velocity_rad_s": round(max_vel, 4),
                },
            ))

        if r.phase == "GRASP" and r.gripper_val == 0:
            if force < GRIP_FORCE_ERR:
                evs.append(SensorEvent(
                    t=r.t, phase=r.phase, level="ERROR",
                    category="mechanical",
                    event_type="grip_force_insufficient",
                    code=event_code("grip_lost_during_transport"),
                    message=(
                        f"Holding force below minimum requirement: "
                        f"actual={force:.1f}N, required>={GRIP_FORCE_ERR:.1f}N "
                        f"at phase={r.phase}."
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
                    code=event_code("grip_force_degraded"),
                    message=(
                        f"Grip margin reduced: actual={force:.1f}N, "
                        f"nominal>={GRIP_FORCE_WARN:.0f}N at phase={r.phase}."
                    ),
                    values={"grip_force_actual": round(force, 2),
                            "nominal": GRIP_FORCE_WARN},
                ))

        # LIFT/MOVE/HOLDでグリップ力が低い = 把持が外れている（gripper_val=0: 閉指令中）
        if r.phase in ("LIFT", "MOVE", "HOLD") and r.gripper_val == 0:
            if force < GRIP_FORCE_ERR:
                evs.append(SensorEvent(
                    t=r.t, phase=r.phase, level="ERROR",
                    category="mechanical",
                    event_type="grip_lost_during_transport",
                    code=event_code("grip_lost_during_transport"),
                    message=(
                        f"Object retention unstable during transfer: "
                        f"grip_force={force:.1f}N at phase={r.phase}."
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
                code=event_code("sensor_packet_timeout"),
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
                code=event_code("encoder_deviation"),
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
                code=event_code("control_loop_overrun"),
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
                code=event_code("ik_divergence"),
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
                code=event_code("ik_position_error"),
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
            code=event_code("periodic_status"),
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
