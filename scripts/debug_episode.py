#!/usr/bin/env python3
"""
1エピソードだけ実行して詳細を出力する。
usage: python scripts/debug_episode.py [normal|mechanical|electrical|software]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml
import numpy as np
from src.simulation.kuka_sim import KukaSim
from src.pipeline import FAULT_PARAMS


def main():
    fault_type = sys.argv[1] if len(sys.argv) > 1 else "normal"

    with open("config/sim_config.yaml") as f:
        import yaml
        cfg = yaml.safe_load(f)

    print(f"\nfault_type: {fault_type}")
    print(f"fault_params: {FAULT_PARAMS.get(fault_type, {})}\n")

    sim = KukaSim(fault_params=FAULT_PARAMS.get(fault_type, {}))
    try:
        sim.setup()
        records, result = sim.run(save_frames=True)
    finally:
        sim.close()

    print(f"Result: {result}")
    print(f"Total records: {len(records)}\n")

    # フェーズごとの統計
    from collections import defaultdict
    phase_records = defaultdict(list)
    for r in records:
        phase_records[r.phase].append(r)

    for phase, recs in phase_records.items():
        valid = [r for r in recs if not r.sensor_missing]
        if valid:
            torques = np.array([r.joint_torques for r in valid])
            max_t = np.nanmax(torques)
            loop_ms = np.mean([r.loop_period_ms for r in recs])
            ik_max = max(r.ik_residual for r in recs)
        else:
            max_t = loop_ms = ik_max = float('nan')

        missing = sum(1 for r in recs if r.sensor_missing)
        print(f"  {phase:<10} steps={len(recs):<4} "
              f"max_torque={max_t:6.2f}  "
              f"max_ik={ik_max:.3f}m  "
              f"avg_loop={loop_ms:.1f}ms  "
              f"sensor_missing={missing}")

    # フレーム差分チェック
    frames = [r.rgb_frame for r in records if r.rgb_frame is not None]
    if frames:
        import imageio
        Path("output/viz").mkdir(parents=True, exist_ok=True)
        imageio.mimsave(f"output/viz/debug_{fault_type}.gif",
                        frames[::2], fps=15, loop=0)
        f0, fl = frames[0], frames[-1]
        diff = np.abs(f0.astype(int) - fl.astype(int)).mean()
        print(f"\nFrames: {len(frames)}  "
              f"diff(first vs last)={diff:.2f}  "
              f"← 0に近いと動いていない")
        print(f"GIF saved: output/viz/debug_{fault_type}.gif")

    # キューブ最終位置は records[-1].object_pos の代わりに result で確認
    print(f"\nEpisode result: {result}")


if __name__ == "__main__":
    main()
