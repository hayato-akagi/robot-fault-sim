# Robot Arm System Specification
Version: 1.0 | Target: Kuka IIWA 7-Axis Arm (Simulated)

## 1. Overview
This document defines the operational limits and fault thresholds
for the Kuka IIWA robotic arm used in pick-and-place tasks.
The system performs cyclic pick-and-place operations, moving
objects from position A to position B using a parallel-jaw gripper.

Control architecture: position control with torque feedback,
1kHz sensor update rate, 100Hz control loop.

## 2. Mechanical Specifications

| Parameter | Rated Value | Max Limit | Fault Threshold |
|-----------|-------------|-----------|-----------------|
| Joint Torque J1-J4 | 6.0 Nm | 8.0 Nm | > 8.8 Nm (110%) |
| Joint Torque J5-J7 | 4.0 Nm | 6.0 Nm | > 6.6 Nm (110%) |
| Grip Force | 10.0 N | 15.0 N | < 3.5 N (grip failure) |
| Contact Force | 20.0 N | 30.0 N | > 30.0 N (collision) |
| End-effector Speed | 0.5 m/s | 1.0 m/s | > 1.0 m/s |

Fault keywords: torque, overload, friction, grip_force, mechanical_stop,
joint_limit, contact_force, actuator_fault, joint_torque_overload,
joint_torque_warning, mechanical_overload

## 3. Electrical Specifications

| Parameter | Rated Value | Tolerance | Fault Threshold |
|-----------|-------------|-----------|-----------------|
| Motor Voltage | 24.0 V | ±10% | < 14.4 V (60%) |
| Encoder Resolution | 0.001 rad | ±0.01 rad | deviation > 0.05 rad |
| Sensor Update Rate | 1000 Hz | ±5% | packet loss > 30 steps |
| Current Draw | 3.0 A | ±20% | > 5.0 A |

Fault keywords: sensor_noise, encoder_error, packet_timeout, voltage_drop,
communication_fault, position_deviation, signal_loss, encoder_deviation,
sensor_packet_timeout, electrical_fault, comm_blackout

## 4. Software / Control Specifications

| Parameter | Rated Value | Tolerance | Fault Threshold |
|-----------|-------------|-----------|-----------------|
| Control Loop Period | 10.0 ms | ±2 ms | > 25 ms (250%) |
| IK Convergence Residual | < 0.01 | — | residual > 0.30 |
| Phase Timeout | 100 steps | — | > 120 steps |
| Sequence Step Time | 50 ms | ±10% | > 120 ms |

Fault keywords: deadlock, loop_overrun, ik_divergence, phase_timeout,
sequence_error, control_period, scheduler_fault, control_loop_overrun,
ik_divergence, software_fault

## 5. Pick-and-Place Task Phases

| Phase | Name | Description |
|-------|------|-------------|
| 1 | HOME | Return to home position |
| 2 | APPROACH | Move end-effector above target object |
| 3 | PICK | Descend and close gripper |
| 4 | CARRY | Lift and move to target position |
| 5 | PLACE | Descend and release gripper |
| 6 | RETURN | Return to hover above target |

## 6. Fault Classification Summary

### 6.1 Mechanical Faults
Cause: Physical degradation, overload, friction increase, gripper wear.
Symptoms: Joint torque exceeds rated maximum, grip failure, collision.
Log indicators: "torque exceeded", "FAULT DETECTED: joint_torque",
"mechanical_stop", "grip_force below threshold"

### 6.2 Electrical Faults
Cause: Sensor malfunction, communication failure, voltage drop.
Symptoms: Encoder deviation, packet timeout, position error.
Log indicators: "packet timeout", "encoder_deviation", "signal_loss",
"comm_blackout", "voltage_drop"

### 6.3 Software Faults
Cause: Control loop overrun, IK divergence, sequence deadlock.
Symptoms: Loop period exceeds limit, IK residual diverges, phase timeout.
Log indicators: "loop_overrun", "ik_divergence", "phase_timeout",
"sequence_error", "control period exceeded"

## 7. Normal Operation Criteria
A cycle is NORMAL when all of the following hold:
- All joint torques remain below 110% of rated maximum throughout
- Encoder deviation < 0.05 rad at all timesteps
- No packet loss events occur
- Control loop period < 25 ms at all steps
- IK residual < 0.10 at convergence
- Cycle completes within max_steps_per_episode (500 steps)
