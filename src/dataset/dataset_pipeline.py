"""
src/dataset/dataset_pipeline.py
---------------------------------
Dataset pipeline for merging:
  1. Isaac Lab synthetic data (sim-to-real)
  2. Teleop real-world demonstrations

Output format: HuggingFace LeRobot dataset format
  - Parquet files with episode data
  - info.json with dataset metadata
  - stats.json with normalization statistics

Usage:
    pipeline = DatasetPipeline(cfg)
    pipeline.merge_datasets(
        sim_dir="data/sim_episodes",
        teleop_dir="data/teleop_episodes",
        output_dir="data/merged_dataset",
    )
    pipeline.push_to_hub()
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Iterator, Optional

import numpy as np

log = logging.getLogger(__name__)


# ─── Episode Record ───────────────────────────────────────────────────────────

class DatasetPipeline:
    """
    Merge simulation and teleop episode data into LeRobot format.

    LeRobot dataset format (simplified):
    ├── data/
    │   └── chunk-000/
    │       ├── episode_000000.parquet
    │       └── ...
    ├── videos/
    │   └── chunk-000/
    │       ├── observation.images.front_episode_000000.mp4
    │       └── ...
    ├── meta/
    │   ├── info.json
    │   ├── episodes.jsonl
    │   └── stats.json

    Args:
        cfg: Full config dict
    """

    # Feature keys that the model expects
    OBS_KEYS = ["observation.state", "observation.images.front", "observation.images.wrist"]
    ACTION_KEY = "action"

    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        self.dataset_cfg = cfg["dataset"]
        self.fps: int = self.dataset_cfg.get("fps", 20)
        self.repo_id: str = self.dataset_cfg.get("repo_id", "username/dataset")
        self.local_dir: str = self.dataset_cfg.get("local_dir", "data/dataset")
        self.chunk_size: int = self.dataset_cfg.get("episode_chunk_size", 100)

    # ── Main Pipeline ─────────────────────────────────────────────────────────

    def merge_datasets(
        self,
        sim_dir: str | Path,
        teleop_dir: str | Path,
        output_dir: str | Path,
    ) -> None:
        """
        Merge simulation and teleop episodes into a single LeRobot dataset.

        Args:
            sim_dir: Directory of Isaac Lab exported episodes (npz files)
            teleop_dir: Directory of teleop recorded episodes (npz files)
            output_dir: Output directory for merged dataset
        """
        import pandas as pd

        sim_dir = Path(sim_dir)
        teleop_dir = Path(teleop_dir)
        output_dir = Path(output_dir)

        log.info("Merging datasets: sim=%s, teleop=%s → %s", sim_dir, teleop_dir, output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "data").mkdir(exist_ok=True)
        (output_dir / "meta").mkdir(exist_ok=True)

        all_episodes = []
        episode_idx = 0

        # Load sim episodes
        sim_episodes = list(sim_dir.glob("episode_*.npz")) if sim_dir.exists() else []
        teleop_episodes = list(teleop_dir.glob("episode_*.npz")) if teleop_dir.exists() else []

        log.info("Found %d sim episodes, %d teleop episodes", len(sim_episodes), len(teleop_episodes))

        for source, paths in [("sim", sim_episodes), ("teleop", teleop_episodes)]:
            for ep_path in sorted(paths):
                chunk_idx = episode_idx // self.chunk_size
                chunk_dir = output_dir / "data" / f"chunk-{chunk_idx:03d}"
                chunk_dir.mkdir(exist_ok=True)

                ep_info = self._convert_episode(
                    ep_path,
                    output_dir=chunk_dir,
                    episode_idx=episode_idx,
                    source=source,
                )
                all_episodes.append(ep_info)
                episode_idx += 1
                if episode_idx % 10 == 0:
                    log.info("Converted %d episodes...", episode_idx)

        # Write metadata
        self._write_info_json(output_dir, total_episodes=episode_idx)
        self._write_episodes_jsonl(output_dir, all_episodes)
        stats = self._compute_stats(output_dir, all_episodes)
        self._write_stats_json(output_dir, stats)

        log.info("Dataset merge complete: %d total episodes at %s", episode_idx, output_dir)

    def _convert_episode(
        self,
        ep_path: Path,
        output_dir: Path,
        episode_idx: int,
        source: str,
    ) -> dict:
        """
        Convert a single .npz episode file to LeRobot parquet format.

        Expected npz keys:
          - joint_positions: [T, 6] float32
          - actions: [T, 7] float32 (6 joints + gripper)
          - timestamps: [T] float64
          - front_images: [T, H, W, 3] uint8
          - wrist_images: [T, H, W, 3] uint8
          - task: str
        """
        import pandas as pd

        data = np.load(ep_path, allow_pickle=True)

        T = len(data["timestamps"])
        task = str(data.get("task", "3d_printer_automation"))

        # Build per-timestep records
        rows = []
        for t in range(T):
            row = {
                "episode_index": episode_idx,
                "frame_index": t,
                "timestamp": float(data["timestamps"][t]),
                "task": task,
                "source": source,
                # State: normalized joint positions
                **{f"observation.state_{i}": float(data["joint_positions"][t, i])
                   for i in range(data["joint_positions"].shape[1])},
                # Actions
                **{f"action_{i}": float(data["actions"][t, i])
                   for i in range(data["actions"].shape[1])},
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        out_path = output_dir / f"episode_{episode_idx:06d}.parquet"
        df.to_parquet(out_path, index=False)

        # Save video frames (if image data present)
        self._save_episode_video(data, output_dir.parent.parent, episode_idx)

        return {
            "episode_index": episode_idx,
            "tasks": [task],
            "length": T,
            "source": source,
        }

    def _save_episode_video(self, data: dict, output_dir: Path, episode_idx: int) -> None:
        """Save front and wrist camera data as MP4 videos."""
        import cv2
        from pathlib import Path

        chunk_idx = episode_idx // self.chunk_size
        vid_dir = output_dir / "videos" / f"chunk-{chunk_idx:03d}"
        vid_dir.mkdir(parents=True, exist_ok=True)

        for cam_key in ["front_images", "wrist_images"]:
            if cam_key not in data:
                continue
            frames = data[cam_key]  # [T, H, W, 3] RGB
            if len(frames) == 0:
                continue

            T, H, W, _ = frames.shape
            cam_label = cam_key.replace("_images", "")
            vid_path = vid_dir / f"observation.images.{cam_label}_episode_{episode_idx:06d}.mp4"

            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            writer = cv2.VideoWriter(str(vid_path), fourcc, self.fps, (W, H))
            for frame in frames:
                bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                writer.write(bgr)
            writer.release()

    def _compute_stats(self, output_dir: Path, episodes: list[dict]) -> dict:
        """
        Compute mean/std/min/max for all numeric features across all episodes.
        Used for normalization during VLA training.
        """
        import pandas as pd

        all_dfs = []
        for chunk_dir in sorted((output_dir / "data").glob("chunk-*")):
            for parquet in chunk_dir.glob("*.parquet"):
                all_dfs.append(pd.read_parquet(parquet))

        if not all_dfs:
            return {}

        combined = pd.concat(all_dfs, ignore_index=True)
        numeric = combined.select_dtypes(include=[np.number])

        stats = {}
        for col in numeric.columns:
            if col in ("episode_index", "frame_index"):
                continue
            stats[col] = {
                "mean": float(numeric[col].mean()),
                "std": float(numeric[col].std()),
                "min": float(numeric[col].min()),
                "max": float(numeric[col].max()),
            }
        return stats

    def _write_info_json(self, output_dir: Path, total_episodes: int) -> None:
        info = {
            "codebase_version": "v2.0",
            "robot_type": "so100",
            "fps": self.fps,
            "features": {
                "observation.state": {"dtype": "float32", "shape": [6], "names": None},
                "action": {"dtype": "float32", "shape": [7], "names": None},
                "observation.images.front": {"dtype": "video", "shape": [3, 480, 640]},
                "observation.images.wrist": {"dtype": "video", "shape": [3, 480, 640]},
                "timestamp": {"dtype": "float32", "shape": [1]},
                "task": {"dtype": "string"},
            },
            "total_episodes": total_episodes,
            "splits": {"train": f"0:{total_episodes}"},
            "data_path": "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
            "video_path": "videos/chunk-{episode_chunk:03d}/{video_key}_episode_{episode_index:06d}.mp4",
        }
        (output_dir / "meta" / "info.json").write_text(json.dumps(info, indent=2))

    def _write_episodes_jsonl(self, output_dir: Path, episodes: list[dict]) -> None:
        with open(output_dir / "meta" / "episodes.jsonl", "w") as f:
            for ep in episodes:
                f.write(json.dumps(ep) + "\n")

    def _write_stats_json(self, output_dir: Path, stats: dict) -> None:
        (output_dir / "meta" / "stats.json").write_text(json.dumps(stats, indent=2))

    # ── Hub Upload ────────────────────────────────────────────────────────────

    def push_to_hub(self, local_dir: str | Path | None = None) -> None:
        """
        Push merged dataset to HuggingFace Hub.

        Requires: huggingface_hub installed and HF_TOKEN env var set.
        """
        from huggingface_hub import HfApi

        local_dir = Path(local_dir or self.local_dir)
        api = HfApi()
        log.info("Pushing dataset to hub: %s", self.repo_id)
        api.upload_folder(
            folder_path=str(local_dir),
            repo_id=self.repo_id,
            repo_type="dataset",
        )
        log.info("Dataset pushed successfully: https://huggingface.co/datasets/%s", self.repo_id)
