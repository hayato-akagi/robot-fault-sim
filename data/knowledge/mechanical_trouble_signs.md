# Mechanical Fault — Trouble Signs

## 特徴的な症状

- 関節トルクの定格超過（J1-J4: 8.8 Nm 以上、J5-J7: 6.6 Nm 以上）
- グリップ力の低下（グリッパーパッド摩耗による把持失敗、< 3.5 N）
- 軸受け摩耗による摩擦増加・異音
- アクチュエーター故障による動作停止
- 接触力の過大（> 30.0 N、衝突）
- エンドエフェクター速度超過（> 1.0 m/s）

## ログキーワード

- `torque exceeded`
- `FAULT DETECTED: joint_torque`
- `mechanical_stop`
- `grip_force below threshold`
- `joint_torque_overload`
- `joint_torque_warning`
- `mechanical_overload`
- `friction`
- `contact_force`
- `actuator_fault`

## 代表的なパラメータ仕様

| パラメータ | 定格 | 最大 | 故障閾値 |
|---|---|---|---|
| J1-J4 トルク | 6.0 Nm | 8.0 Nm | > 8.8 Nm |
| J5-J7 トルク | 4.0 Nm | 6.0 Nm | > 6.6 Nm |
| グリップ力 | 10.0 N | 15.0 N | < 3.5 N |
| 接触力 | 20.0 N | 30.0 N | > 30.0 N |
