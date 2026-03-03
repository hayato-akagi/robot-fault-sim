"""
Colabデモ（https://colab.research.google.com/drive/1eXq-Tl3QKzmbXGSKU2hDk0u_EHdfKVd0）
をベースにしたKukaピック&プレースシミュレーション。

正常動作: Colabコードそのまま（750ステップ）
故障注入: 同じループ内で3箇所のパラメータを変えるだけ

フェーズ定義（Colabの t 条件と対応）:
  t   0-149  : APPROACH  （アームをキューブ上空へ）
  t 150-249  : GRASP     （グリッパを閉じて把持）
  t 250-399  : LIFT      （持ち上げ）
  t 400-599  : MOVE      （横移動）
  t 600-699  : HOLD      （目標位置で停止）
  t 700-749  : RELEASE   （解放）
"""

import math
import time
import numpy as np
import pybullet as p
import pybullet_data
from dataclasses import dataclass, field
from typing import Optional


# フェーズ境界（Colabの条件と完全一致）
PHASE_BOUNDARIES = [
    (0,   150, "APPROACH"),
    (150, 250, "GRASP"),
    (250, 400, "LIFT"),
    (400, 600, "MOVE"),
    (600, 700, "HOLD"),
    (700, 750, "RELEASE"),
]

def get_phase(t: int) -> str:
    for start, end, name in PHASE_BOUNDARIES:
        if start <= t < end:
            return name
    return "RELEASE"


@dataclass
class StepRecord:
    t: int
    phase: str
    # 関節センサ
    joint_positions: list[float]   # 7軸
    joint_velocities: list[float]  # 7軸
    joint_torques: list[float]     # 7軸
    # 手先
    ee_pos: list[float]
    target_pos: list[float]
    ik_residual: float
    # グリッパ
    gripper_val: float
    grip_force_actual: float
    # 制御
    loop_period_ms: float
    # 故障フラグ（センサ欠損）
    sensor_missing: bool
    # エンコーダノイズ量（electrical fault時に注入した値のRMS）
    encoder_noise_rms: float = 0.0
    # フレーム（GIF用、Noneの場合あり）
    rgb_frame: Optional[np.ndarray] = None


class KukaSim:
    """
    fault_params の値だけ変えることで同じコードで正常/故障を切り替える。

    正常:
        fault_params = {}

    Mechanical（グリップ力不足 + 関節摩擦増大）:
        fault_params = {
            "grip_force": 35,          # 正常=100
            "joint_friction": 5.0,     # 正常=1.0
        }

    Electrical（エンコーダノイズ + 通信断絶）:
        fault_params = {
            "encoder_noise_std": 0.08,     # 正常=0.0
            "sensor_missing_prob": 0.03,   # 正常=0.0
            "sensor_missing_steps": 30,    # 欠損が続くステップ数
        }

    Software（ループ遅延 + IKターゲットノイズ）:
        fault_params = {
            "loop_delay_ms": 28.0,         # 正常=0.0
            "ik_target_noise": 0.15,       # 正常=0.0  (IKターゲットにm単位のオフセット)
        }
    """

    # Colabと同じ初期設定
    KUKA_BASE_POS  = [1.4, -0.2, 0.6]
    KUKA_BASE_ORN  = [0, 0, 0, 1]
    TABLE_POS      = [1.0, -0.2, 0.0]
    TABLE_ORN      = [0, 0, 0.7071, 0.7071]
    CUBE_START_POS = [0.85, -0.2, 0.65]
    CUBE_TARGET_Y  = 0.2
    KUKA_EE_IDX    = 6
    TOTAL_STEPS    = 750

    # Colabと同じカメラ設定
    CAM_TARGET  = [0.95, -0.2, 0.2]
    CAM_DIST    = 2.05
    CAM_YAW     = -50
    CAM_PITCH   = -40
    CAM_W, CAM_H = 480, 360
    CAM_FOV     = 60

    # 正常時のグリップ力
    GRIP_FORCE_NORMAL = 100

    def __init__(self, fault_params: dict = None, capture_every: int = 8):
        self.fp = fault_params or {}
        self.capture_every = capture_every  # Colabは8ステップに1フレーム
        self.client = None
        self.kuka_id = None
        self.gripper_id = None
        self.cube_id = None
        self._sensor_missing_remaining = 0

    def setup(self):
        """Colabの初期化コードをそのまま移植。"""
        self.client = p.connect(p.DIRECT)
        p.setAdditionalSearchPath(pybullet_data.getDataPath(),
                                  physicsClientId=self.client)
        p.setGravity(0, 0, -10, physicsClientId=self.client)

        p.loadURDF("plane.urdf", physicsClientId=self.client)

        # Kuka アーム（Colabと同じURFとpose）
        self.kuka_id = p.loadURDF(
            "kuka_iiwa/model_vr_limits.urdf",
            basePosition=self.KUKA_BASE_POS,
            baseOrientation=self.KUKA_BASE_ORN,
            physicsClientId=self.client,
        )

        # グリッパ（Colabと同じSDF）
        self.gripper_id = p.loadSDF(
            "gripper/wsg50_one_motor_gripper_new_free_base.sdf",
            physicsClientId=self.client,
        )[0]

        p.loadURDF("table/table.urdf",
                   basePosition=self.TABLE_POS,
                   baseOrientation=self.TABLE_ORN,
                   physicsClientId=self.client)

        self.cube_id = p.loadURDF(
            "cube.urdf",
            basePosition=self.CUBE_START_POS,
            globalScaling=0.05,
            physicsClientId=self.client,
        )
        # キューブの摩擦設定（正常時）
        p.changeDynamics(self.cube_id, -1,
                         lateralFriction=2.0,
                         spinningFriction=0.1,
                         rollingFriction=0.1,
                         physicsClientId=self.client)

        # グリッパ指の摩擦設定
        gripper_friction = self.fp.get("gripper_friction", 2.0)  # mechanical時は0.1
        for link in range(p.getNumJoints(self.gripper_id, physicsClientId=self.client)):
            p.changeDynamics(self.gripper_id, link,
                             lateralFriction=gripper_friction,
                             physicsClientId=self.client)

        # グリッパをアームに接続（Colabと同じ制約）
        p.createConstraint(
            self.kuka_id, 6, self.gripper_id, 0,
            p.JOINT_FIXED, [0,0,0], [0,0,0.05], [0,0,0],
            physicsClientId=self.client,
        )
        kuka_cid2 = p.createConstraint(
            self.gripper_id, 4, self.gripper_id, 6,
            jointType=p.JOINT_GEAR, jointAxis=[1,1,1],
            parentFramePosition=[0,0,0], childFramePosition=[0,0,0],
            physicsClientId=self.client,
        )
        p.changeConstraint(kuka_cid2, gearRatio=-1, erp=0.5,
                           relativePositionTarget=0, maxForce=100,
                           physicsClientId=self.client)

        # Kukaリセット（Colabと同じ初期姿勢）
        joint_positions = [-0.0, -0.0, 0.0, 1.570793, 0.0, -1.036725, 0.000001]
        for i in range(p.getNumJoints(self.kuka_id, physicsClientId=self.client)):
            p.resetJointState(self.kuka_id, i, joint_positions[i],
                              physicsClientId=self.client)
            p.setJointMotorControl2(self.kuka_id, i, p.POSITION_CONTROL,
                                    joint_positions[i], 0,
                                    physicsClientId=self.client)

        # グリッパリセット（Colabと同じ）
        p.resetBasePositionAndOrientation(
            self.gripper_id,
            [0.923103, -0.200000, 1.250036],
            [-0.0, 0.964531, -0.000002, -0.263970],
            physicsClientId=self.client,
        )
        gripper_joint_positions = [0.0, -0.011130, -0.206421, 0.205143,
                                    -0.009999, 0.0, -0.010055, 0.0]
        for i in range(p.getNumJoints(self.gripper_id, physicsClientId=self.client)):
            p.resetJointState(self.gripper_id, i, gripper_joint_positions[i],
                              physicsClientId=self.client)
            p.setJointMotorControl2(self.gripper_id, i, p.POSITION_CONTROL,
                                    gripper_joint_positions[i], 0,
                                    physicsClientId=self.client)

        # Mechanical fault: 関節摩擦増大
        joint_friction = self.fp.get("joint_friction", 1.0)
        if joint_friction != 1.0:
            for i in range(p.getNumJoints(self.kuka_id, physicsClientId=self.client)):
                p.changeDynamics(
                    self.kuka_id, i,
                    lateralFriction=joint_friction,
                    jointDamping=0.5 * joint_friction,
                    physicsClientId=self.client,
                )

    def run(self, save_frames: bool = False) -> tuple[list[StepRecord], str]:
        """
        Colabの750ステップループを実行しrecordを返す。
        result: "success" | "fault"
        """
        records: list[StepRecord] = []
        num_joints = p.getNumJoints(self.kuka_id, physicsClientId=self.client)
        target_orn = p.getQuaternionFromEuler([0, 1.01 * math.pi, 0])

        for t in range(self.TOTAL_STEPS):
            t0 = time.perf_counter()

            # ----------------------------------------------------------
            # Software fault: ループ遅延
            # ----------------------------------------------------------
            delay_ms = self.fp.get("loop_delay_ms", 0.0)
            if delay_ms > 0:
                time.sleep(delay_ms / 1000.0)

            # ----------------------------------------------------------
            # Colabと同じ target_pos / gripper_val の決定ロジック
            # ----------------------------------------------------------
            target_pos = [0.85, -0.2, 0.97]
            gripper_val = 1  # 1=開, 0=閉

            if t >= 150 and t < 250:
                target_pos, gripper_val = [0.85, -0.2, 0.97], 0  # 把持
            elif t >= 250 and t < 400:
                target_pos = [0.85, -0.2, 0.97 + 0.13*(t-250)/150.]
                gripper_val = 0  # 持ち上げ
            elif t >= 400 and t < 600:
                target_pos = [0.85, -0.2 + 0.4*(t-400)/200., 1.1]
                gripper_val = 0  # 移動
            elif t >= 600 and t < 700:
                target_pos, gripper_val = [0.85, 0.2, 1.1], 0  # 停止
            elif t >= 700:
                target_pos, gripper_val = [0.85, 0.2, 1.1], 1  # 解放

            # ----------------------------------------------------------
            # Software fault: IKターゲットにノイズ（GRASP以降）
            # ----------------------------------------------------------
            ik_noise = self.fp.get("ik_target_noise", 0.0)
            noisy_target = list(target_pos)
            if ik_noise > 0 and t >= 150:
                noisy_target[0] += np.random.uniform(-ik_noise, ik_noise)
                noisy_target[1] += np.random.uniform(-ik_noise, ik_noise)

            # IK計算
            joint_poses = p.calculateInverseKinematics(
                self.kuka_id, self.KUKA_EE_IDX,
                noisy_target, target_orn,
                physicsClientId=self.client,
            )

            # 関節制御
            for j in range(num_joints):
                p.setJointMotorControl2(
                    bodyIndex=self.kuka_id,
                    jointIndex=j,
                    controlMode=p.POSITION_CONTROL,
                    targetPosition=joint_poses[j],
                    physicsClientId=self.client,
                )

            # ----------------------------------------------------------
            # Mechanical fault: グリップ力低下
            # ----------------------------------------------------------
            grip_force = self.fp.get("grip_force", self.GRIP_FORCE_NORMAL)
            # gripper_val=0: 開(0.05), gripper_val=1: 閉(-0.01)
            gripper_pos = 0.05 - gripper_val * 0.06

            p.setJointMotorControl2(
                self.gripper_id, 4, p.POSITION_CONTROL,
                targetPosition=gripper_pos,
                force=grip_force,
                physicsClientId=self.client,
            )
            p.setJointMotorControl2(
                self.gripper_id, 6, p.POSITION_CONTROL,
                targetPosition=gripper_pos,
                force=grip_force,
                physicsClientId=self.client,
            )

            p.stepSimulation(physicsClientId=self.client)

            # ----------------------------------------------------------
            # センサ取得
            # ----------------------------------------------------------
            loop_ms = (time.perf_counter() - t0) * 1000.0 + delay_ms

            # Electrical fault: センサ欠損（通信断絶）
            sensor_missing = self._check_sensor_missing()

            if not sensor_missing:
                js = [p.getJointState(self.kuka_id, j,
                                      physicsClientId=self.client)
                      for j in range(num_joints)]
                positions  = [s[0] for s in js]
                velocities = [s[1] for s in js]
                torques    = [abs(s[3]) for s in js]

                # Electrical fault: エンコーダノイズ
                noise_std = self.fp.get("encoder_noise_std", 0.0)
                if noise_std > 0:
                    noise = np.random.normal(0, noise_std, num_joints)
                    positions = [p_val + n for p_val, n in zip(positions, noise)]
                    encoder_noise_rms = float(np.sqrt(np.mean(noise**2)))
                else:
                    encoder_noise_rms = 0.0
            else:
                # センサ欠損時は前回値をNaNで代替
                positions  = [float('nan')] * num_joints
                velocities = [float('nan')] * num_joints
                torques    = [float('nan')] * num_joints
                encoder_noise_rms = 0.0

            # 手先位置
            ee_state = p.getLinkState(self.kuka_id, self.KUKA_EE_IDX,
                                      physicsClientId=self.client)
            ee_pos = list(ee_state[0])
            ik_residual = float(np.linalg.norm(
                np.array(ee_pos) - np.array(target_pos)
            ))

            # グリッパの実際の把持力（gripper joint 4のトルクを近似）
            gs = p.getJointState(self.gripper_id, 4,
                                  physicsClientId=self.client)
            grip_force_actual = abs(gs[3])

            # フレームキャプチャ（GIF用）
            rgb_frame = None
            if save_frames and t % self.capture_every == 0:
                rgb_frame = self._capture()

            records.append(StepRecord(
                t=t,
                phase=get_phase(t),
                joint_positions=positions,
                joint_velocities=velocities,
                joint_torques=torques,
                ee_pos=ee_pos,
                target_pos=list(target_pos),
                ik_residual=ik_residual,
                gripper_val=gripper_val,
                grip_force_actual=grip_force_actual,
                loop_period_ms=loop_ms,
                sensor_missing=sensor_missing,
                encoder_noise_rms=encoder_noise_rms,
                rgb_frame=rgb_frame,
            ))

        # 成否判定: キューブがY=0.2付近に移動したか
        cube_pos, _ = p.getBasePositionAndOrientation(
            self.cube_id, physicsClientId=self.client)
        dist = abs(cube_pos[1] - self.CUBE_TARGET_Y)
        result = "success" if dist < 0.15 else "fault"

        return records, result

    def _check_sensor_missing(self) -> bool:
        """電気系: 確率的な通信断絶を模擬。"""
        prob = self.fp.get("sensor_missing_prob", 0.0)
        if self._sensor_missing_remaining > 0:
            self._sensor_missing_remaining -= 1
            return True
        if prob > 0 and np.random.random() < prob:
            self._sensor_missing_remaining = self.fp.get("sensor_missing_steps", 30)
            return True
        return False

    def _capture(self) -> np.ndarray:
        vm = p.computeViewMatrixFromYawPitchRoll(
            self.CAM_TARGET, self.CAM_DIST,
            self.CAM_YAW, self.CAM_PITCH, 0, 2,
        )
        pm = p.computeProjectionMatrixFOV(
            self.CAM_FOV, self.CAM_W / self.CAM_H, 0.01, 100)
        _, _, rgb, _, _ = p.getCameraImage(
            self.CAM_W, self.CAM_H, vm, pm,
            renderer=p.ER_TINY_RENDERER,
            physicsClientId=self.client,
        )
        frame = np.array(rgb, dtype=np.uint8).reshape(self.CAM_H, self.CAM_W, 4)
        return frame[:, :, :3]

    def close(self):
        if self.client is not None:
            p.disconnect(self.client)
            self.client = None
