# Electrical Fault — Trouble Signs

## 特徴的な症状

- エンコーダ偏差の増大（> 0.05 rad）
- センサーパケットロス・タイムアウト（> 30 ステップ）
- モーター電圧の低下（< 14.4 V、定格の 60% 以下）
- 電流過大（> 5.0 A）
- 通信断絶（comm_blackout）
- 位置偏差の発生

## ログキーワード

- `packet timeout`
- `encoder_deviation`
- `signal_loss`
- `comm_blackout`
- `voltage_drop`
- `sensor_noise`
- `encoder_error`
- `communication_fault`
- `position_deviation`
- `sensor_packet_timeout`
- `electrical_fault`

## 代表的なパラメータ仕様

| パラメータ | 定格 | 公差 | 故障閾値 |
|---|---|---|---|
| モーター電圧 | 24.0 V | ±10% | < 14.4 V |
| エンコーダ分解能 | 0.001 rad | ±0.01 rad | 偏差 > 0.05 rad |
| センサー更新レート | 1000 Hz | ±5% | パケットロス > 30 ステップ |
| 電流 | 3.0 A | ±20% | > 5.0 A |
