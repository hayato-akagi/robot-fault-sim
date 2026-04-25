# robot-fault-sim

Kuka IIWA ロボットアームのピック&プレース故障シミュレーション。
ログテキスト・ナレッジベース・分類データセット（JSON）を生成し、
experiment-classifier へ渡すことを目的とする。

---

## データセットを作る手順

### Step 1: シミュレーション実行（ログ・ラベルの生成）

```bash
# 疎通確認（各カテゴリ 5 件、約 2〜3 分）
docker compose --profile quick up --build

# 本番生成（各カテゴリ 50 件、約 20 分）
docker compose up --build
```

生成物（中間ファイル）:

| パス | 内容 |
|------|------|
| `output/dataset/logs/log_XXXX.txt` | 各エピソードのロボットログ |
| `output/dataset/labels.csv` | ログ ID・故障種別の対応表（CSV） |
| `output/viz/*.gif` | 可視化 GIF |
| `output/viz/sensor_overview.png` | センサグラフ |

### システムブロック図（ログ出力・保存経路）

```mermaid
flowchart TD
  A[run_dataset.py] --> B[pipeline.py]
  B --> C[kuka_sim.py / controller.py]
  C --> D[sensor.py]
  D --> E[log_generator.py]
  D --> F[label_writer.py]
  C --> G[gif_renderer.py / plot_renderer.py]

  E --> H[output/dataset/logs/log_XXXX.txt]
  F --> I[output/dataset/labels.csv]
  B --> J[output/dataset/docs/robot_arm_spec.txt]
  G --> K[output/viz/*.gif]
  G --> L[output/viz/sensor_overview.png]

  H --> M[build_dataset_json.py]
  I --> M
  M --> N[data/sample_dataset.json]

  N --> O[build_compact_dataset_json.py]
  O --> P[data/sample_dataset_compact.json]

  N --> Q[export_to_classifier.sh]
  R[data/knowledge/*.md] --> Q
  Q --> S[experiment-classifier data/]
```

### システムブロック図（構成要素ベース）

```mermaid
flowchart LR
  subgraph ControllerSystem[制御系]
    C[コントローラ]
    P[シミュレーション設定]
    FI[故障注入モジュール]
  end

  subgraph RobotSystem[ロボット系]
    A[ロボットアーム]
    G[グリッパー]
    S[センサ群]
  end

  subgraph Workspace[作業空間]
    B1[対象の箱 Pick Box]
    B2[搬送先の箱 Place Box]
    T[机 Table]
  end

  subgraph Logging[ログ出力・保存]
    LG[ログ生成]
    LW[ラベル生成]
    L1[output/dataset/logs/log_XXXX.txt]
    L2[output/dataset/labels.csv]
  end

  C -->|関節指令 / 把持指令| A
  A --> G
  G -->|把持 / 解放| B1
  A -->|移動| B1
  A -->|移動| B2

  B1 -->|接触反力| G
  T -->|支持| B1
  T -->|支持| B2
  T -->|設置| A

  A -->|状態量| S
  G -->|把持力| S
  S -->|観測値| C

  P --> C

  P --> FI
  FI -->|mechanical: 摩擦増加 / 把持低下| A
  FI -->|electrical: ノイズ / 通信異常| S
  FI -->|software: ループ遅延 / IK発散| C

  C -->|フェーズ遷移・制御状態| LG
  S -->|観測値・異常検知| LG
  FI -->|注入イベント| LG
  LG --> L1

  FI -->|故障種別| LW
  C -->|エピソード結果| LW
  LW --> L2
```

### Step 2: JSON データセットへ変換

```bash
python scripts/build_dataset_json.py
```

`output/dataset/labels.csv` + `output/dataset/logs/*.txt` を読み込み、
`data/sample_dataset.json` を生成する。

**ラベル正規化ルール:**

| CSV の `label` 値 | JSON の `ground_truth` |
|---|---|
| `normal` | `[]` |
| `mechanical_*`（pad_wear / bearing / actuator / combined） | `["mechanical"]` |
| `electrical` | `["electrical"]` |
| `software` | `["software"]` |

### Step 3: experiment-classifier へエクスポート

```bash
bash scripts/export_to_classifier.sh [path/to/experiment-classifier]
```

内部で Step 2 を自動実行し、以下をコピーする:

- `data/sample_dataset.json` → `$DEST/data/`
- `data/knowledge/*.md` → `$DEST/data/knowledge/`

---

## 生成物（ターゲット形式）

| パス | 内容 | 用途 |
|------|------|------|
| `data/sample_dataset.json` | 分類データセット（JSON 配列） | experiment-classifier のバッチ実行 |
| `data/knowledge/*.md` | ナレッジベース（トピック別 MD） | Knowledge ページへ登録 |
| `data/eval_results/<run_id>/` | バッチ評価結果 | 精度比較 |
| `data/experiments/<experiment_id>/` | 実験設定・分類結果 | 再現・比較 |

### `data/sample_dataset.json` のスキーマ

```json
[
  {
    "log_id":       "log_0001",
    "log_text":     "<ログ本文（複数行テキスト）>",
    "ground_truth": []
  },
  {
    "log_id":       "log_0051",
    "log_text":     "<ログ本文>",
    "ground_truth": ["mechanical"]
  }
]
```

---

## フォルダ構成

```
robot-fault-sim/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── config/
│   └── sim_config.yaml              # 件数・閾値・故障パラメータ
├── specs/
│   └── robot_arm_spec.md            # 仕様書（参照用）
├── data/                            # ★ ターゲット形式の出力先
│   ├── sample_dataset.json          #   分類データセット（JSON）
│   ├── knowledge/                   #   ナレッジベース（トピック別）
│   │   ├── mechanical_trouble_signs.md
│   │   ├── electrical_trouble_signs.md
│   │   ├── software_trouble_signs.md
│   │   └── normal_operation_criteria.md
│   ├── eval_results/                #   バッチ評価結果
│   └── experiments/                 #   実験設定・分類結果
├── output/                          # シミュレーション中間出力
│   └── dataset/
│       ├── logs/log_XXXX.txt
│       ├── labels.csv
│       └── docs/robot_arm_spec.txt
├── src/
│   ├── simulation/
│   │   ├── controller.py            # ピック&プレース 6 フェーズ制御
│   │   └── kuka_sim.py              # Kuka シミュレーター
│   ├── monitoring/
│   │   ├── sensor.py                # 閾値超過検出 → SensorEvent
│   │   ├── log_generator.py         # テキストログ生成
│   │   └── label_writer.py          # 正解ラベル CSV 出力
│   ├── visualization/
│   │   ├── gif_renderer.py          # GIF 生成
│   │   └── plot_renderer.py         # センサグラフ PNG 生成
│   └── pipeline.py                  # 統合実行
└── scripts/
    ├── run_dataset.py               # シミュレーション実行
    ├── build_dataset_json.py        # ★ CSV+ログ → JSON 変換
    └── export_to_classifier.sh      # ★ experiment-classifier へエクスポート
```

---

## 故障カテゴリ

| ラベル | 注入方法 | ログのキーワード |
|--------|---------|----------------|
| `mechanical` | 関節摩擦係数を増大・グリップ力低下 | `joint_torque_overload`, `torque_warning` |
| `electrical` | エンコーダノイズ付加・通信タイムアウト | `encoder_deviation`, `packet_timeout` |
| `software` | 制御ループ遅延・IK 発散 | `control_loop_overrun`, `ik_divergence` |
| *(正常)* | なし | `periodic_status` のみ → `ground_truth: []` |

---

## 件数・パラメータの変更

`config/sim_config.yaml` の `dataset` セクションを編集する:

```yaml
dataset:
  normal: 50      # 変更可能
  mechanical: 50
  electrical: 50
  software: 50
```
