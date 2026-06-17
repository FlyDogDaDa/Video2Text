"""VAD cache module — pre-computed speech segments stored on disk.

Usage in main.py (replace inline _extract_speech_segments_chunked):

    from src.utils.vad_cache import load_vad_cache

    segments = load_vad_cache(video_path, track_index)
    # → returns list[dict] with {"start": float, "end": float}
    #   cached segments can be consumed directly by the ASR loop
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

CACHE_DIR = Path("runs/vad_cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────── 快取路徑 ────────────────────────────


def _video_cache_dir(video_path: Path) -> Path:
    """回傳該影片快取資料夾的路徑。

    跟 main.py 做法一致，放在 `runs/{video_stem}/`。
    """
    return video_path.parent / video_path.stem


def vad_cache_path(video_path: Path) -> Path:
    """回傳單一影片 VAD 快取的 JSON 檔案路徑。

    所有音軌的 VAD 集中在同一個檔案，不跟轉錄檔名衝突。

    Parameters
    ----------
    video_path:
        影片檔案路徑。

    Returns
    -------
    Path to the JSON cache file.
    """
    return _video_cache_dir(video_path) / "vad_cache.json"


# ──────────────────────────── 寫入 ────────────────────────────


def save_vad_cache(
    video_path: Path | Any, track_index: int, segments: list[dict[str, float]]
) -> Path:
    """將 VAD 結果寫入快取 JSON 檔案（追加該軌道）。

    Parameters
    ----------
    video_path:
        原始影片路徑（``Path`` 或 ``IOCacheVideo``）。
        若傳入 ``IOCacheVideo`` 會從 ``_path`` 屬性提取路徑。
    track_index:
        音軌索引。
    segments:
        VAD 回傳的 segments，每筆需有 ``start`` 和 ``end`` key。

    Returns
    -------
    寫入的檔案路徑。
    """
    # Lazy import to avoid circular dependency
    from src.utils.video import IOCacheVideo

    if isinstance(video_path, IOCacheVideo):
        video_path = Path(video_path._path)
    cache_dir = _video_cache_dir(video_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    path = vad_cache_path(video_path)

    # 讀取既有快取
    cache: dict[str, list[dict[str, float]]] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)

    # 寫入/更新該軌道
    cache[f"track{track_index}"] = segments

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    logger.info(
        "Wrote VAD cache: %s (track %d, %d segments)",
        path,
        track_index,
        len(segments),
    )
    return path


def save_vad_cache_batch(
    video_path: Path, track_segments: dict[int, list[dict[str, float]]]
) -> Path:
    """批次寫入所有音軌的 VAD 快取。

    Parameters
    ----------
    video_path:
        原始影片路徑。
    track_segments:
        {track_index: segments} 的字典。

    Returns
    -------
    寫入的檔案路徑。
    """
    cache_dir = _video_cache_dir(video_path)
    cache_dir.mkdir(parents=True, exist_ok=True)

    path = vad_cache_path(video_path)

    cache: dict[str, list[dict[str, float]]] = {}
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)

    for track_idx, segments in track_segments.items():
        cache[f"track{track_idx}"] = segments

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

    total_segs = sum(len(s) for s in track_segments.values())
    logger.info(
        "Wrote VAD cache: %s (%d tracks, %d segments total)",
        path,
        len(track_segments),
        total_segs,
    )
    return path


# ──────────────────────────── 讀取 ────────────────────────────


def load_vad_cache(video_path: Path | Any, track_index: int) -> list[dict[str, float]]:
    """讀取已快取的 VAD segments。

    如果快取不存在或為空，回傳空清單。

    Parameters
    ----------
    video_path:
        原始影片路徑（``Path`` 或 ``IOCacheVideo``）。
        若傳入 ``IOCacheVideo`` 會從 ``_path`` 屬性提取路徑。
    track_index:
        音軌索引。

    Returns
    -------
    List of dicts with ``start`` and ``end`` keys (seconds).
    """
    # Lazy import to avoid circular dependency
    from src.utils.video import IOCacheVideo

    if isinstance(video_path, IOCacheVideo):
        video_path = Path(video_path._path)
    path = vad_cache_path(video_path)
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    key = f"track{track_index}"
    return cache.get(key, [])


def load_all_vad_cache(video_path: Path) -> dict[int, list[dict[str, float]]]:
    """讀取該影片所有音軌的 VAD 快取。

    Returns
    -------
    {track_index: segments} dictionary.
    """
    path = vad_cache_path(video_path)
    if not path.exists():
        return {}

    with open(path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    return {
        int(k.replace("track", "")): v
        for k, v in cache.items()
        if k.startswith("track")
    }


# ──────────────────────────── 檢查 ────────────────────────────


def has_vad_cache(video_path: Path, track_index: int) -> bool:
    """檢查特定音軌的 VAD 快取是否存在且非空。"""
    path = vad_cache_path(video_path)
    if not path.exists() or path.stat().st_size == 0:
        return False

    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return f"track{track_index}" in cache
    except (json.JSONDecodeError, OSError):
        return False


def get_vad_cache_info(video_path: Path) -> dict:
    """取得該影片 VAD 快取的統整資訊。

    Returns
    -------
    {"exists": bool, "tracks": int, "total_segments": int, ...}
    """
    path = vad_cache_path(video_path)
    if not path.exists():
        return {"exists": False}

    with open(path, "r", encoding="utf-8") as f:
        cache = json.load(f)

    info = {"exists": True, "tracks": len(cache), "total_segments": 0}
    for key, segments in cache.items():
        if isinstance(segments, list):
            info["total_segments"] += len(segments)
    return info


# ──────────────────────────── 清除 ────────────────────────────


def clear_vad_cache(video_path: Path | None = None) -> int:
    """清除 VAD 快取。

    Parameters
    ----------
    video_path:
        若指定則只清除該影片的快取。若為 None 則清除全部快取（所有 `runs/*/vad_cache.json`）。

    Returns
    -------
    刪除的快取目錄數量。
    """
    import shutil

    if video_path is None:
        # 清除所有 runs/*/vad_cache.json 對應的目錄
        count = 0
        for d in Path("runs").iterdir():
            if d.is_dir():
                vad_cache = d / "vad_cache.json"
                if vad_cache.exists():
                    shutil.rmtree(d)
                    count += 1
        logger.info("Cleared %d VAD cache directories under runs/", count)
        return count

    cache_dir = _video_cache_dir(video_path)
    if cache_dir.is_dir():
        count = 1  # 目錄數
        shutil.rmtree(cache_dir)
        logger.info("Cleared VAD cache for %s", video_path.name)
        return count

    return 0


# ──────────────────────────── 統整 ────────────────────────────


def collect_video_tracks(video_root: Path) -> list[tuple[Path, int]]:
    """收集所有未快取的音軌，回傳 (video_path, track_index) 清單。

    用於 vad_preprocess.py 的批次掃描。
    """
    VIDEO_EXTENSIONS = {".mp4", ".mkv"}
    from src.utils.video import IOCacheVideo

    candidates: list[tuple[Path, int]] = []
    for vpath in sorted(video_root.rglob("*")):
        if vpath.suffix not in VIDEO_EXTENSIONS:
            continue
        try:
            with IOCacheVideo(vpath, cached=False) as video:
                for track_idx in range(len(video.audio_streams)):
                    if not has_vad_cache(vpath, track_idx):
                        candidates.append((vpath, track_idx))
        except Exception as exc:
            logger.warning("Skipping %s (%s)", vpath.name, exc)
            continue

    logger.info("Found %d un-cached tracks in %s", len(candidates), video_root)
    return candidates


# ──────────────────────────── 執行預處理 ────────────────────────────


def run_vad_preprocessing(
    video_root: Path,
    workers: int | None = None,
    force: bool = False,
) -> tuple[int, int]:
    """批次預處理所有音軌的 VAD 結果。

    在單一 process 內執行（不適用 ProcessPool），
    適合在 vad_preprocess.py 中被 subprocess 呼叫。

    每部影片只 open 一次 IOCacheVideo，跑完所有音軌再 close，
    避免頻繁載入同一檔案的記憶體開銷。

    Parameters
    ----------
    video_root:
        包含 .mp4/.mkv 的根目錄。
    workers:
        此函式本身不使用平行處理，保留參數用於 API 一致性。
    force:
        是否強制重新計算（忽略既有快取）。

    Returns
    -------
    (processed, cached) — 處理的音軌數 / 使用快取的音軌數。
    """
    import time

    from src.utils.video import IOCacheVideo

    # 1. 先收集所有影片（force 時只收集，不檢查個別軌道快取）
    VIDEO_EXTENSIONS = {".mp4", ".mkv"}
    video_paths: list[Path] = []
    for vpath in sorted(video_root.rglob("*")):
        if vpath.suffix not in VIDEO_EXTENSIONS:
            continue
        try:
            with IOCacheVideo(vpath, cached=False) as video:
                video_paths.append(vpath)
        except Exception:
            continue

    if not video_paths:
        logger.info("No video files found.")
        return 0, 0

    # 2. 每部影片 open 一次，算完所有音軌
    total_start = time.monotonic()
    processed = 0
    cached_count = 0

    for video_path in video_paths:
        try:
            with IOCacheVideo(video_path, cached=False) as video:
                # 收集本影片需要處理的軌道
                tracks_to_process: list[int] = []
                tracks_skipped: list[int] = []
                for track_idx in range(len(video.audio_streams)):
                    if force or not has_vad_cache(video_path, track_idx):
                        tracks_to_process.append(track_idx)
                    else:
                        tracks_skipped.append(track_idx)

                cached_count += len(tracks_skipped)
                if tracks_skipped:
                    logger.info(
                        "%s: %d tracks already cached, skipped",
                        video_path.name,
                        len(tracks_skipped),
                    )

                if not tracks_to_process:
                    continue

                # 批量處理所有未快取的軌道
                track_segments: dict[int, list[dict[str, float]]] = {}
                silent_tracks: list[int] = []

                for track_idx in tracks_to_process:
                    track = video.get_audio(
                        0,
                        video.duration,
                        max_clip_duration=video.duration,
                        audio_streams=[track_idx],
                    )[0]

                    if not np.any(track):
                        silent_tracks.append(track_idx)
                        continue

                    segments = _extract_speech_segments_chunked(track)
                    track_segments[track_idx] = segments

                # 一次寫入所有軌道
                if track_segments:
                    save_vad_cache_batch(video_path, track_segments)
                    processed += len(track_segments)

                # 記錄靜音軌
                cached_count += len(silent_tracks)

                if (processed + cached_count) % 10 == 0:
                    elapsed = time.monotonic() - total_start
                    logger.info(
                        "Progress: %d processed, %d cached, %.1fs elapsed",
                        processed + cached_count,
                        cached_count,
                        elapsed,
                    )

        except Exception as exc:
            logger.error(
                "Failed to process %s: %s",
                video_path.name,
                exc,
            )
            processed += 1

    elapsed = time.monotonic() - total_start
    logger.info(
        "VAD preprocessing complete: %d processed, %d cached, %.1fs total",
        processed,
        cached_count,
        elapsed,
    )
    return processed, cached_count


# ──────────────────────────── VAD 執行（供 process 使用） ────────────────────────────

# 每個 process 只需要載入一次 VAD 模型
_vad_model_cache: Any = None


def _load_vad_model_for_worker() -> Any:
    """在 process 內部載入 VAD 模型（只執行一次）。"""
    global _vad_model_cache
    if _vad_model_cache is None:
        from silero_vad import load_silero_vad

        _vad_model_cache = load_silero_vad()
    return _vad_model_cache


SAMPLING_RATE = 16_000


def _extract_speech_segments_chunked(
    track: np.ndarray,
    max_speech_duration_s: float = 20.0,
    chunk_seconds: float = 300.0,
) -> list[dict[str, float]]:
    """對長音軌分塊跑 VAD，再合併結果。

    此函式被 ProcessPoolExecutor 的 worker 呼叫，
    會在本 process 快取的 VAD 模型上執行。
    """
    from silero_vad import get_speech_timestamps

    sr = SAMPLING_RATE
    total_seconds = len(track) / sr
    if total_seconds <= 0:
        return []

    vad_model = _load_vad_model_for_worker()
    all_segments: list[dict[str, float]] = []

    num_chunks = int(np.ceil(total_seconds / chunk_seconds))
    for i in range(num_chunks):
        offset_s = i * chunk_seconds
        chunk_start_s = offset_s
        chunk_end_s = min(offset_s + chunk_seconds, total_seconds)

        start_sample = int(chunk_start_s * sr)
        end_sample = int(chunk_end_s * sr)
        chunk = track[start_sample:end_sample]

        if not np.any(chunk):
            continue

        segments = get_speech_timestamps(
            chunk,
            vad_model,
            sampling_rate=SAMPLING_RATE,
            threshold=0.5,
            min_speech_duration_ms=200,
            min_silence_duration_ms=300,
            speech_pad_ms=100,
            max_speech_duration_s=max_speech_duration_s,
            return_seconds=True,
        )

        for seg in segments:
            seg["start"] = seg["start"] + chunk_start_s
            seg["end"] = seg["end"] + chunk_start_s

        all_segments.extend(segments)

    if not all_segments:
        return []

    all_segments.sort(key=lambda s: s["start"])
    merged: list[dict[str, float]] = [dict(all_segments[0])]
    for seg in all_segments[1:]:
        prev = merged[-1]
        if seg["start"] <= prev["end"] + 0.1:
            prev["end"] = max(prev["end"], seg["end"])
        else:
            merged.append(dict(seg))

    return merged


def vad_process_one(video_path: str, track_index: int) -> int:
    """單一音軌的 VAD 處理函式（供 ProcessPoolExecutor 的 worker 呼叫）。

    如果影片超過 20 分鐘，會分段處理以避免載入完整音軌時 OOM。
    使用上一個 chunk 的倒數第二段 ([-2]) end 作為下一段的 boundary，
    避免在語音中間切斷。

    回傳 segments 數量。

    Parameters
    ----------
    video_path:
        影片檔案絕對路徑（字串）。
    track_index:
        音軌索引。

    Returns
    -------
    Number of VAD segments produced.
    """
    import logging
    import traceback

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    try:
        from src.utils.video import IOCacheVideo

        path = Path(video_path)
        CHUNK_SECONDS = 900  # 15 分鐘/chunk，控制記憶體用量

        with IOCacheVideo(path, cached=True) as video:
            if video.duration <= 0:
                return 0

            need_chunked = video.duration > 1200  # 20 分鐘閾值
            all_segments: list[dict[str, float]] = []

            if need_chunked:
                num_chunks = int(np.ceil(video.duration / CHUNK_SECONDS))
                boundary: float | None = None

                for chunk_idx in range(num_chunks):
                    chunk_start = chunk_idx * CHUNK_SECONDS
                    chunk_end = min((chunk_idx + 1) * CHUNK_SECONDS, video.duration)

                    # 用上一個 chunk [-2] end 作為起始點，避免切斷語音
                    if boundary is not None and chunk_idx > 0:
                        if chunk_start < boundary:
                            chunk_start = boundary
                        if chunk_start >= chunk_end:
                            boundary = None
                            continue

                    track = video.get_audio(
                        chunk_start,
                        chunk_end,
                        max_clip_duration=chunk_end - chunk_start,
                        audio_streams=[track_index],
                    )

                    if not track or not np.any(track[0]):
                        boundary = None
                        continue

                    segments = _extract_speech_segments_chunked(
                        track[0], chunk_seconds=CHUNK_SECONDS
                    )

                    # 將 timestamps 轉換為絕對影片時間
                    offset = chunk_start
                    for s in segments:
                        s["start"] += offset
                        s["end"] += offset

                    # 過濾掉 boundary 之前的段落（避免重複）
                    if boundary is not None and len(all_segments) >= 2:
                        seg_boundary = all_segments[-2]["end"]
                        segments = [s for s in segments if s["start"] >= seg_boundary]

                    all_segments.extend(segments)

                    # 更新 boundary 為全域列表的 [-2] end，供下一 chunk 使用
                    if len(all_segments) >= 2:
                        boundary = all_segments[-2]["end"]
                    else:
                        boundary = None
            else:
                track = video.get_audio(
                    0,
                    video.duration,
                    max_clip_duration=video.duration,
                    audio_streams=[track_index],
                )[0]

                if not np.any(track):
                    return 0

                segments = _extract_speech_segments_chunked(track)
                all_segments.extend(segments)

            if not all_segments:
                save_vad_cache(path, track_index, [])
                return 0

            save_vad_cache(path, track_index, all_segments)
            return len(all_segments)
    except Exception as exc:
        logger.error(
            "%s track %d: %s\n%s", video_path, track_index, exc, traceback.format_exc()
        )
        return -1
