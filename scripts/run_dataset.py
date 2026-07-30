#!/usr/bin/env python3
"""
データセット一括生成スクリプト。

Usage:
  python scripts/run_dataset.py           # 本番生成（各50件）
  python scripts/run_dataset.py --quick   # 疎通確認（各5件）
  python scripts/run_dataset.py --gif     # 各タイプ1件のGIFを追加生成
"""

import argparse
import time
import sys
from pathlib import Path

import yaml

# プロジェクトルートを sys.path に追加
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import SimulationPipeline
from src.visualization.plot_renderer import PlotRenderer


def load_config(path: str = "config/sim_config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def main():
    parser = argparse.ArgumentParser(description="robot-fault-sim dataset generator")
    parser.add_argument("--quick", action="store_true",
                        help="各カテゴリ 5 件のみ（疎通確認用）")
    parser.add_argument("--gif", action="store_true",
                        help="各カテゴリ最初の 1 件を GIF 出力")
    parser.add_argument("--config", default="config/sim_config.yaml",
                        help="設定ファイルのパス")
    args = parser.parse_args()

    cfg = load_config(args.config)
    pipeline = SimulationPipeline(cfg)

    counts: dict[str, int] = dict(cfg["dataset"])
    if args.quick:
        counts = {k: 5 for k in counts}

    total = sum(counts.values())
    print(f"\n{'='*55}")
    print(f"  robot-fault-sim  |  episodes={total}  quick={args.quick}  gif={args.gif}")
    print(f"{'='*55}\n")

    pipeline.export_spec_doc()

    episode_num = 0
    all_histories: dict = {}
    t_start = time.time()

    for fault_type, n_episodes in counts.items():
        print(f"\n[{fault_type.upper()}]  {n_episodes} episodes")
        type_histories = []

        # mechanical は4バリアントを均等に割り当て
        variants = None
        if fault_type == "mechanical":
            from src.pipeline import FAULT_PARAMS
            variants = FAULT_PARAMS["mechanical_variants"]

        for i in range(n_episodes):
            episode_num += 1
            log_id = f"log_{episode_num:04d}"
            save_gif = args.gif and i == 0

            # バリアントがある場合はラウンドロビンで割り当て
            if variants:
                variant = variants[i % len(variants)]
                result = pipeline.run_episode(
                    log_id=log_id,
                    fault_type=fault_type,
                    save_gif=save_gif,
                    fault_params_override=variant,
                )
            else:
                result = pipeline.run_episode(
                    log_id=log_id,
                    fault_type=fault_type,
                    save_gif=save_gif,
                )
            type_histories.append(result["records"])

            mark = "✓" if result["result"] == "success" else "✗"
            print(f"  {mark} {log_id}  result={result['result']:<8}  "
                  f"events={result['n_events']}  errors={result['n_errors']}")

        if type_histories:
            all_histories[fault_type] = type_histories[0]

    # センサ時系列グラフ（全カテゴリ揃った場合のみ）
    if len(all_histories) >= 2:
        print("\nGenerating sensor plots...")
        plotter = PlotRenderer(cfg)
        plotter.save_sensor_overview(all_histories)
        plotter.save_fault_comparison(all_histories)

    elapsed = time.time() - t_start
    print(f"\n{'='*55}")
    print(f"  Done.  {total} episodes in {elapsed:.1f}s")
    print(f"  Trials : {cfg['output']['trials_dir']}")
    print(f"  Labels : {cfg['output']['labels_file']}")
    print(f"  Docs   : {cfg['output']['docs_dir']}")
    print(f"  Viz    : {cfg['output']['viz_dir']}")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()
