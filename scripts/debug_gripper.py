"""
グリッパの開閉動作だけを確認するスクリプト。
アームは動かさず、グリッパのみ開→閉→開を繰り返す。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import math, numpy as np, pybullet as p, pybullet_data, imageio

c = p.connect(p.DIRECT)
p.setAdditionalSearchPath(pybullet_data.getDataPath())
p.setGravity(0,0,-10)
p.loadURDF('plane.urdf')
kuka = p.loadURDF('kuka_iiwa/model_vr_limits.urdf', basePosition=[1.4,-0.2,0.6], baseOrientation=[0,0,0,1])
gripper = p.loadSDF('gripper/wsg50_one_motor_gripper_new_free_base.sdf')[0]
p.createConstraint(kuka,6,gripper,0,p.JOINT_FIXED,[0,0,0],[0,0,0.05],[0,0,0])
cid2 = p.createConstraint(gripper,4,gripper,6,jointType=p.JOINT_GEAR,jointAxis=[1,1,1],
    parentFramePosition=[0,0,0],childFramePosition=[0,0,0])
p.changeConstraint(cid2, gearRatio=-1, erp=0.5, relativePositionTarget=0, maxForce=100)

for i,a in enumerate([-0.0,-0.0,0.0,1.570793,0.0,-1.036725,0.000001]):
    p.resetJointState(kuka,i,a)
    p.setJointMotorControl2(kuka,i,p.POSITION_CONTROL,a,0)
p.resetBasePositionAndOrientation(gripper,[0.923103,-0.200000,1.250036],[-0.0,0.964531,-0.000002,-0.263970])
for _ in range(200): p.stepSimulation()

frames = []

def capture():
    vm = p.computeViewMatrixFromYawPitchRoll([0.85,-0.2,0.9], 0.8, -30, -40, 0, 2)
    pm = p.computeProjectionMatrixFOV(60, 480/360, 0.01, 100)
    _, _, rgb, _, _ = p.getCameraImage(480, 360, vm, pm, renderer=p.ER_TINY_RENDERER)
    return np.array(rgb, dtype=np.uint8).reshape(360,480,4)[:,:,:3]

print("開→閉→開 テスト")
# 開: 0.05, 閉: -0.01
for phase, target, label in [(60, 0.05, "OPEN"), (60, -0.01, "CLOSE"), (60, 0.05, "OPEN2")]:
    for t in range(phase):
        p.setJointMotorControl2(gripper,4,p.POSITION_CONTROL,targetPosition=target,force=100)
        p.setJointMotorControl2(gripper,6,p.POSITION_CONTROL,targetPosition=target,force=100)
        p.stepSimulation()
        if t % 4 == 0:
            frames.append(capture())
    j4 = p.getJointState(gripper,4)[0]
    j6 = p.getJointState(gripper,6)[0]
    print(f"  {label}: target={target:.3f}  J4={j4:.4f}  J6={j6:.4f}")

Path("output/viz").mkdir(parents=True, exist_ok=True)
imageio.mimsave("output/viz/gripper_test.gif", frames, fps=15, loop=0)
print("GIF saved: output/viz/gripper_test.gif")
p.disconnect()
