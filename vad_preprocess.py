#!/usr/bin/env python3
"""VAD 預處理工具 — 使用 ProcessPoolExecutor 平行掃描所有音軌並快取結果。

使用方式：
    uv run vad_preprocess.py --dir /path/to/videos [--workers 8]
    uv run vad_preprocess.py --dir /path/to/videos --force

快取存放於 runs/{video_stem}/vad_cache.json

跑完後，main.py 的 ASR 階段會自動載入快取，不再需要重新跑 VAD。
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Final

from tqdm import tqdm

from src.utils.vad_cache import (
    collect_video_tracks,
    run_vad_preprocessing,
    vad_cache_path,
    vad_process_one,
)
from src.utils.video import IOCacheVideo

CACHE_DIR: Final[Path] = Path("runs/vad_cache")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="VAD 預處理 — 平行掃描所有音軌，快取說話區間。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "使用範例：\n"
            "  %(prog)s --dir /path/to/videos\n"
            "  %(prog)s --dir /path/to/videos --workers 8\n"
            "  %(prog)s --dir /path/to/videos --force\n"
            "  %(prog)s --dir /path/to/videos --single video.mp4\n"
            "\n"
            "快取存放位置：runs/vad_cache/\n"
            "清除快取：python vad_preprocess.py --dir /path --clear\n"
        ),
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="影片根目錄（預設: VIDEO_ROOT）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help="平行處理數量（預設: CPU 核心數）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="強制重新計算所有音軌（忽略既有快取）",
    )
    parser.add_argument(
        "--single",
        type=Path,
        default=None,
        help="只處理單一影片檔案（用於測試）",
    )
    parser.add_argument(
        "--single-track",
        type=int,
        default=0,
        help="--single 模式要處理的音軌索引（預設 0）",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="清除所有 VAD 快取",
    )
    parser.add_argument(
        "--clear-video",
        type=Path,
        default=None,
        help="只清除指定影片的 VAD 快取",
    )
    parser.add_argument(
        "--mode",
        choices=["multiprocess", "single"],
        default="multiprocess",
        help="處理模式：multiprocess (平行) / single (單一 process，用於除錯)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日誌等級（預設: INFO）",
    )
    return parser


def run_multiprocess(video_root: Path, workers: int, force: bool) -> None:
    """使用 ProcessPoolExecutor 平行處理。"""
    from src.utils.vad_cache import has_vad_cache

    VIDEO_EXTENSIONS = {".mp4", ".mkv"}

    # 收集工作項目
    work_items: list[tuple[str, int]] = []

    if video_root.exists():
        if force:
            all_paths = sorted(
                f for f in video_root.rglob("*") if f.suffix in VIDEO_EXTENSIONS
            )
        else:
            candidates = collect_video_tracks(video_root)
            all_paths_uniq: dict[Path, list[int]] = {}
            for vpath, track_idx in candidates:
                all_paths_uniq.setdefault(vpath, []).append(track_idx)
            all_paths = []
            for vpath, tracks in all_paths_uniq.items():
                all_paths.extend((vpath, t) for t in tracks)
    else:
        all_paths = []

    for vpath, track_idx in all_paths:
        work_items.append((str(vpath), track_idx))

    if not work_items:
        print("沒有找到需要處理的音軌。")
        return

    total = len(work_items)
    print(f"[VAD] 共 {total} 個音軌需要處理，使用 {workers} 個平行工作程序")

    cached_count = 0
    processed_count = 0
    error_count = 0

    start_time = time.monotonic()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(vad_process_one, vpath, track_idx): (vpath, track_idx)
            for vpath, track_idx in work_items
        }

        with tqdm(total=total, desc="[VAD] 總進度") as pbar:
            for future in as_completed(futures):
                vpath_str, track_idx = futures[future]
                vpath = Path(vpath_str)
                try:
                    seg_count = future.result()
                    if seg_count is None:
                        seg_count = 0

                    is_cache = has_vad_cache(vpath, track_idx)

                    if seg_count == 0:
                        cached_count += 1
                        msg = f"[VAD] {vpath.name} track {track_idx}: silent, cached"
                    else:
                        processed_count += 1
                        msg = (
                            f"[VAD] {vpath.name} track {track_idx}: "
                            f"{seg_count} segments"
                        )

                    tqdm.write(msg)
                except Exception as exc:
                    error_count += 1
                    msg = (
                        f"[VAD] {Path(vpath_str).name} track {track_idx}: ERROR - {exc}"
                    )
                    tqdm.write(msg)
                    logger.exception(msg)

                pbar.update(1)

    elapsed = time.monotonic() - start_time
    print(
        f"[VAD] 完成！處理 {processed_count} 個，靜音 {cached_count} 個，"
        f"錯誤 {error_count} 個，共用 {elapsed:.1f}s"
    )


def run_single_process(video_root: Path, force: bool) -> None:
    """使用單一 process 處理（用於除錯或測試）。"""
    processed, cached = run_vad_preprocessing(video_root, force=force)
    print(f"[VAD] 完成！處理 {processed} 個，使用快取 {cached} 個")


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # 設定日誌等級
    logger.setLevel(getattr(logging, args.log_level, logging.INFO))

    # VIDEO_ROOT 預設值（與 main.py 一致）
    VIDEO_ROOT = Path("/mnt/hdd/b11223209/螢幕錄影/2026_06/")

    video_dir = args.dir or VIDEO_ROOT

    # 清除快取模式
    if args.clear:
        from src.utils.vad_cache import clear_vad_cache

        count = clear_vad_cache()
        print(f"[VAD] 已清除所有 VAD 快取")
        return

    if args.clear_video:
        from src.utils.vad_cache import clear_vad_cache

        count = clear_vad_cache(args.clear_video)
        print(f"[VAD] 已清除 {args.clear_video.name} 的 VAD 快取")
        return

    # 單一檔案測試模式
    if args.single:
        from src.utils.vad_cache import save_vad_cache

        video_path = args.single
        if not video_path.exists():
            print(f"[VAD] 找不到檔案：{video_path}")
            sys.exit(1)

        print(f"[VAD] 測試模式：{video_path}")
        with IOCacheVideo(video_path, cached=True) as video:
            track_idx = min(args.single_track, len(video.audio_streams) - 1)
            print(f"[VAD] 音軌 {track_idx} ({len(video.audio_streams)} 軌)")

            track = video.get_audio(
                0,
                video.duration,
                max_clip_duration=video.duration,
                audio_streams=[track_idx],
            )[0]

            if not any(track):
                print(f"[VAD] 靜音軌，跳過")
                return

            from src.utils.vad_cache import _extract_speech_segments_chunked

            segments = _extract_speech_segments_chunked(track)
            save_vad_cache(video_path, track_idx, segments)
            print(f"[VAD] {len(segments)} 個區間已快取到 {vad_cache_path(video_path)}")
        return

    # 主處理模式
    if args.mode == "multiprocess":
        workers = args.workers or 4  # 預設 4 個工作程序
        run_multiprocess(video_dir, workers, args.force)
    else:
        run_single_process(video_dir, args.force)


if __name__ == "__main__":
    main()
