# Software / Control Fault — Trouble Signs

## 特徴的な症状

- 制御ループ周期の超過（> 25 ms、定格の 250% 以上）
- IK（逆運動学）残差の発散（> 0.30）
- フェーズタイムアウト（> 120 ステップ）
- シーケンスデッドロック
- スケジューラー障害

## ログキーワード

- `loop_overrun`
- `ik_divergence`
- `phase_timeout`
- `sequence_error`
- `control period exceeded`
- `deadlock`
- `scheduler_fault`
- `control_loop_overrun`
- `software_fault`

## 代表的なパラメータ仕様

| パラメータ | 定格 | 公差 | 故障閾値 |
|---|---|---|---|
| 制御ループ周期 | 10.0 ms | ±2 ms | > 25 ms |
| IK 収束残差 | < 0.01 | — | 残差 > 0.30 |
| フェーズタイムアウト | 100 ステップ | — | > 120 ステップ |
| シーケンスステップ時間 | 50 ms | ±10% | > 120 ms |
