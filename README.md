# robot-fault-sim

PyBullet を使った Kuka IIWA ロボットアームのピック&プレース故障シミュレーション。 ログ・仕様書・正解ラベルを生成する。

## 生成物

| 種別 | パス | 用途 |
|------|------|------|
| ログテキスト | `output/dataset/logs/log_XXXX.txt` | experiment-classifier の推論入力 |
| 正解ラベル | `output/dataset/labels.csv` | 精度計算 |
| 仕様書 | `output/dataset/docs/robot_arm_spec.txt` | KG 構築元 |
| GIF | `output/viz/*.gif` | 論文 Figure |
| センサグラフ | `output/viz/sensor_overview.png` | 論文 Figure |

## クイックスタート

```bash
# 疎通確認（各カテゴリ5件 + GIF、約2〜3分）
docker compose --profile quick up --build

# 本番生成（各カテゴリ50件 + GIF、約20分）
docker compose up --build

# experiment-classifier へエクスポート
docker compose --profile export up
```

## フォルダ構成

```
robot-fault-sim/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── config/
│   └── sim_config.yaml        # 件数・閾値・故障パラメータ
├── specs/
│   └── robot_arm_spec.md      # 仕様書（KG 構築のソース）
├── src/
│   ├── simulation/
│   │   ├── env.py             # PyBullet 環境
│   │   ├── controller.py      # ピック&プレース 6フェーズ制御
│   │   └── fault_injector.py  # 故障注入（摩擦/ノイズ/遅延）
│   ├── monitoring/
│   │   ├── sensor.py          # 閾値超過検出 → SensorEvent
│   │   ├── log_generator.py   # テキストログ生成
│   │   └── label_writer.py    # 正解ラベル CSV 出力
│   ├── visualization/
│   │   ├── gif_renderer.py    # GIF 生成
│   │   └── plot_renderer.py   # センサグラフ PNG 生成
│   └── pipeline.py            # 統合実行
└── scripts/
    ├── run_dataset.py          # データセット生成
    └── export_to_classifier.sh # experiment-classifier へコピー
```

## 故障カテゴリ

| カテゴリ | 注入方法 | ログのキーワード |
|---------|---------|----------------|
| `mechanical` | 関節摩擦係数を増大・グリップ力低下 | `joint_torque_overload`, `torque_warning` |
| `electrical` | エンコーダノイズ付加・通信タイムアウト | `encoder_deviation`, `packet_timeout` |
| `software` | 制御ループ遅延・IK 発散 | `control_loop_overrun`, `ik_divergence` |
| `normal` | なし | `periodic_status` のみ |

## experiment-classifier 側の設定変更

`config/experiment.yaml` のカテゴリを以下に変更する:

```yaml
categories:
  - mechanical
  - electrical
  - software
```

## 件数・パラメータの変更

`config/sim_config.yaml` の `dataset` セクションを編集する:

```yaml
dataset:
  normal: 50      # 変更可能
  mechanical: 50
  electrical: 50
  software: 50
```
