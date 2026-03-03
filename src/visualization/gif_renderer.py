"""オフスクリーンフレームから GIF を生成する。"""

import imageio
import numpy as np
from pathlib import Path


class GifRenderer:
    def __init__(self, cfg: dict):
        self.fps = cfg["visualization"]["gif_fps"]
        self.out_dir = Path(cfg["output"]["viz_dir"])
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def save(self, frames: list[np.ndarray], filename: str) -> str:
        path = self.out_dir / filename
        # 1フレームおきに間引いてファイルサイズを抑える
        sampled = frames[::2] if len(frames) > 60 else frames
        imageio.mimsave(str(path), sampled, fps=self.fps, loop=0)
        print(f"  GIF saved: {path}  ({len(sampled)} frames)")
        return str(path)
