"""Video2Text console pipeline — two-phase (ASR → LLM).

Phase 1 (ASR):  掃完整個目錄，對所有 .mp4/.mkv 跑音軌辨識。
Phase 2 (LLM): 手動切換伺服器後，跑所有剩餘工作（清理、畫面提取、總結）。
"""

import argparse
import asyncio
import base64
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import cache, partial
from io import BytesIO, StringIO
from itertools import count as Counter
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
from openai import AsyncOpenAI
from PIL.Image import Image as PILImage
from scipy.io import wavfile
from silero_vad import get_speech_timestamps, load_silero_vad
from silero_vad.utils_vad import OnnxWrapper as VAD_OnnxWrapper
from tqdm.asyncio import tqdm

from src.utils import (
    IOCacheVideo,
    collect_video_tracks,
    create_slices_indices,
    has_vad_cache,
    load_vad_cache,
    read_jsonl,
    run_vad_preprocessing,
    save_vad_cache,
    write_jsonl,
)
from src.utils.vad_cache import load_all_vad_cache, vad_cache_path, vad_process_one

load_dotenv()

SAMPLING_RATE = 16_000
PBAR_COUNT = Counter()


# ──────────────────────────── 常數設定 ────────────────────────────

VIDEO_ROOT = Path("/mnt/hdd/b11223209/螢幕錄影/2026_06/")
VIDEO_EXTENSIONS = {".mp4", ".mkv"}

# 模型名稱 (可覆寫)
DEFAULT_ASR_NAME = "MediaTek-Research/Breeze-ASR-26"
DEFAULT_LLM_NAME = "google/gemma-4-12B-it-qat-w4a16-ct"


# ──────────────────────────── 工具函式 ────────────────────────────


@cache
def load_vad_model() -> VAD_OnnxWrapper:
    return load_silero_vad()


def is_cached(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


async def wrap_task(task, pbar: tqdm):
    res = await task
    pbar.update(1)
    return res


def pil_to_b64_url(image: PILImage) -> str:
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}"


# ──────────────────────────── ASR 階段 ────────────────────────────


def _extract_speech_segments(
    track: np.ndarray,
    max_speech_duration_s: float = 20.0,
) -> list[dict]:
    """對整條音軌跑 VAD 一次，回傳自動切好的說話區間。

    使用 max_speech_duration_s 讓 VAD 內部自動拆分超長段，
    不會把單字切斷（尋找 ≥100ms 靜音縫隙）。
    """
    if not np.any(track):
        return []

    speech_timestamps = get_speech_timestamps(
        track,
        load_vad_model(),
        sampling_rate=SAMPLING_RATE,
        threshold=0.5,
        min_speech_duration_ms=200,
        min_silence_duration_ms=300,
        speech_pad_ms=100,
        max_speech_duration_s=max_speech_duration_s,
        return_seconds=True,
    )
    return speech_timestamps


def _extract_speech_segments_chunked(
    track: np.ndarray,
    max_speech_duration_s: float = 20.0,
    chunk_seconds: float = 300.0,
) -> list[dict]:
    """對長音軌分塊跑 VAD，再合併結果。

    Silero VAD 是 RNN 模型，逐幀順序掃描，對 60 分鐘音軌（~57M 樣本）極慢。
    分成 5 分鐘的區塊各自跑 VAD，可顯著加速。

    Parameters
    ----------
    track: np.ndarray
        1-D audio array at 16 kHz sampling rate.
    max_speech_duration_s: float
        Passed to ``get_speech_timestamps``.
    chunk_seconds: float
        Size of each processing chunk in seconds. Default 5 min.

    Returns
    -------
    List of dicts with ``start`` and ``end`` keys (seconds).
    """
    sr = SAMPLING_RATE
    total_seconds = len(track) / sr
    if total_seconds <= 0:
        return []

    vad_model = load_vad_model()
    all_segments: list[dict] = []

    num_chunks = int(np.ceil(total_seconds / chunk_seconds))
    for i in range(num_chunks):
        offset_s = i * chunk_seconds
        chunk_start_s = offset_s
        chunk_end_s = min(offset_s + chunk_seconds, total_seconds)

        start_sample = int(chunk_start_s * sr)
        end_sample = int(chunk_end_s * sr)
        chunk = track[start_sample:end_sample]

        # Skip empty chunks
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

        # Shift timestamps to global time
        for seg in segments:
            seg["start"] = seg["start"] + chunk_start_s
            seg["end"] = seg["end"] + chunk_start_s

        all_segments.extend(segments)

    # Merge overlapping / adjacent segments across chunk boundaries.
    # VAD may split a single utterance at a chunk boundary.
    if not all_segments:
        return []

    all_segments.sort(key=lambda s: s["start"])
    merged: list[dict] = [dict(all_segments[0])]
    for seg in all_segments[1:]:
        prev = merged[-1]
        if seg["start"] <= prev["end"] + 0.1:  # ≤100ms gap → merge
            prev["end"] = max(prev["end"], seg["end"])
        else:
            merged.append(dict(seg))

    return merged


async def transcribe_audio(
    sem: asyncio.Semaphore,
    start: float,
    end: float,
    model_name: str,
    client: AsyncOpenAI,
    sound: np.ndarray | BytesIO,
    language: str = "zh",
    prompt: str = "",
) -> dict[str, str | dict[str, float]]:
    """對一段已經切好的音訊區間送 ASR 辨識。"""
    if isinstance(sound, np.ndarray):
        buffer = BytesIO()
        wavfile.write(buffer, SAMPLING_RATE, sound)
        buffer.seek(0)
        buffer.name = "audio.wav"
        sound = buffer
    elif not isinstance(sound, BytesIO):
        raise TypeError("sound must be a numpy array or BytesIO")

    async with sem:
        result = await client.audio.transcriptions.create(
            model=model_name,
            file=sound,
            language=language,
            response_format="json",
            extra_body={"prompt": prompt} if prompt else {},
        )
    return {"at": {"start": start, "end": end}, "result": result.text}


async def run_workflow_transcribe_audio_track(
    sem: asyncio.Semaphore,
    video: IOCacheVideo,
    asr_name: str,
    asr_client: AsyncOpenAI,
    track_index: int,
    save_path: Path,
):
    """對單一音軌：VAD 查快取 → 只讀說話區間音軌 → 送 ASR。

    有 VAD 快取時，不對整軌跑 get_audio，而是對每個 segment 獨立讀取。
    """
    if is_cached(save_path):
        return

    # 整軌跑 VAD（先查快取）
    speech_segments = load_vad_cache(video, track_index)

    # 沒快取才讀整軌來算 VAD
    if not speech_segments:
        CHUNK_SECONDS = 900  # 15 分鐘/chunk，控制記憶體用量
        need_chunked = video.duration > 1200  # 20 分鐘閾值

        if need_chunked:
            speech_segments = []
            boundary: float | None = None
            num_chunks = int(np.ceil(video.duration / CHUNK_SECONDS))

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

                track_chunk = video.get_audio(
                    chunk_start,
                    chunk_end,
                    max_clip_duration=chunk_end - chunk_start,
                    audio_streams=[track_index],
                )

                if not track_chunk or not np.any(track_chunk[0]):
                    boundary = None
                    continue

                segments = _extract_speech_segments_chunked(
                    track_chunk[0], chunk_seconds=CHUNK_SECONDS
                )

                # 將 timestamps 轉換為絕對影片時間
                offset = chunk_start
                for s in segments:
                    s["start"] += offset
                    s["end"] += offset

                # 過濾掉 boundary 之前的段落（避免重複）
                if boundary is not None and len(speech_segments) >= 2:
                    seg_boundary = speech_segments[-2]["end"]
                    segments = [s for s in segments if s["start"] >= seg_boundary]

                speech_segments.extend(segments)

                # 更新 boundary 為全域列表的 [-2] end，供下一 chunk 使用
                if len(speech_segments) >= 2:
                    boundary = speech_segments[-2]["end"]
                else:
                    boundary = None
        else:
            track = video.get_audio(
                0,
                video.duration,
                max_clip_duration=video.duration,
                audio_streams=[track_index],
            )[0]

            # 跳過完全靜音的軌
            if not np.any(track):
                return

            speech_segments = _extract_speech_segments_chunked(track)

        if not speech_segments:
            return  # 無人聲，不寫任何 JSONL

        save_vad_cache(video, track_index, speech_segments)

    # 對每個說話區間送 ASR（只讀該區間音軌）
    tasks = []
    with tqdm(
        total=len(speech_segments),
        desc=f"音軌 {track_index} 辨識",
        position=2,
    ) as pbar:
        for seg in speech_segments:
            start_s = seg["start"]
            end_s = seg["end"]

            # 只讀該說話區間的音軌，不讀整軌
            track_chunk = video.get_audio(
                start_s,
                end_s,
                max_clip_duration=end_s - start_s,
                audio_streams=[track_index],
            )[0]

            tasks.append(
                wrap_task(
                    transcribe_audio(
                        sem=sem,
                        start=start_s,
                        end=end_s,
                        model_name=asr_name,
                        client=asr_client,
                        sound=track_chunk,
                        prompt="忽略背景雜訊與無聲段落 以空格分割 僅轉錄說話內容 轉錄下列這段音訊的逐字稿",
                    ),
                    pbar,
                )
            )

        results = await asyncio.gather(*tasks)

    with open(save_path, "a") as f:
        for result in results:
            write_jsonl(f, result)


async def run_single_file_asr(
    video_path: Path,
    asr_name: str,
    asr_client: AsyncOpenAI,
    asr_batch_size: int,
):
    """對單一檔案執行 Phase 1：音軌辨識 (ASR)。"""
    save_dir = video_path.parent / video_path.stem / "results"
    save_dir.mkdir(exist_ok=True, parents=True)

    audio_transcription_dir = save_dir / "audio_transcriptions"
    audio_transcription_dir.mkdir(exist_ok=True)

    tqdm.write(f"[{video_path.name}] Phase 1 — 音軌辨識 (ASR)...")

    with IOCacheVideo(video_path, cached=True) as video:
        transcription_paths = [
            audio_transcription_dir / f"track_{track_index}.jsonl"
            for track_index in range(len(video.audio_streams))
        ]

        skipped = sum(1 for p in transcription_paths if is_cached(p))
        running = len(transcription_paths) - skipped

        sem = asyncio.Semaphore(asr_batch_size)
        tasks = [
            run_workflow_transcribe_audio_track(
                sem=sem,
                video=video,
                asr_name=asr_name,
                asr_client=asr_client,
                track_index=track_index,
                save_path=path,
            )
            for track_index, path in enumerate(transcription_paths)
        ]

        with tqdm(
            total=len(transcription_paths),
            desc=f"[{video_path.name}] 音軌辨識",
            position=1,
        ) as pbar:
            if skipped:
                tqdm.write(f"[{video_path.name}] 跳過 {skipped} 軌 (已存在)")
                pbar.set_description(f"{video_path.name} [已完成 {skipped} 軌]")
            await asyncio.gather(*[wrap_task(task, pbar) for task in tasks])

        tqdm.write(f"[{video_path.name}] 音軌辨識完成 ({len(transcription_paths)} 軌)")


# ──────────────────────────── LLM 階段 ────────────────────────────

# --- 音軌清理 (chunked) ---


async def run_workflow_audio_transcription_cleanup_chunked(
    llm_name: str,
    llm_client: AsyncOpenAI,
    transcription_paths: list[Path],
    save_path: Path,
    chunk_size: int = 30,
    sem: asyncio.Semaphore = None,
):
    if is_cached(save_path):
        return

    transcriptions = [list(read_jsonl(path)) for path in transcription_paths]
    results = dict()
    for i, transcription in enumerate(transcriptions, start=1):
        for item in transcription:
            key = tuple(item["at"].values())
            text = item["result"].strip()
            if key not in results:
                results[key] = list()
            if text:
                results[key].append(f"Track{i}: {text}")

    valid_results = [
        ((start, end), tracks) for (start, end), tracks in results.items() if tracks
    ]
    total_items = len(valid_results)

    async def process_chunk(messages, chunk_idx: int, pbar: tqdm):
        async with sem:
            response = await llm_client.chat.completions.create(
                model=llm_name,
                messages=messages,
                max_tokens=16000,
                temperature=1.0,
                top_p=0.95,
                extra_body={
                    "top_k": 64,
                    "chat_template_kwargs": {"enable_thinking": True},
                },
            )

        cleaned = response.choices[0].message.content
        if cleaned is None:
            raise ValueError(
                f"Response is None at chunk {chunk_idx}. "
                "Your thinking model might be stuck in a loop; please try again."
            )
        pbar.update(1)
        return cleaned.strip()

    tasks = []
    with tqdm(total=total_items, desc="清理音訊逐字稿", position=2) as pbar:
        for i in range(0, total_items, chunk_size):
            chunk = valid_results[i : i + chunk_size]
            current_chunk_idx = (i // chunk_size) + 1
            total_chunks = (total_items + chunk_size - 1) // chunk_size

            prompt_buffer = StringIO()
            for (start, end), tracks in chunk:
                prompt_buffer.write(f"[{start:0.2f}s ~ {end:0.2f}s]\n")
                prompt_buffer.write("\n".join(tracks))
                prompt_buffer.write("\n\n")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful professional assistant.\n"
                        "Your mission is to clean up the transcription.\n"
                        "You simply reduce redundancy without adding summaries or merging sentences yourself; "
                        "you present it as it is."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"The following is a transcript of an automatic-speech-recognition "
                        f"(Part {current_chunk_idx}/{total_chunks}):\n"
                        f"```\n{prompt_buffer.getvalue()}```\n\n"
                        "You reduce redundancy and provide clean subtitles.\n"
                        "Include time, dialogue, and tracks."
                    ),
                },
            ]
            tasks.append(process_chunk(messages, current_chunk_idx, pbar))

        cleaned_parts = await asyncio.gather(*tasks)

    cleaned_merged = "\n---\n".join(cleaned_parts)

    # 第二輪：整體總結
    summary_messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful professional assistant.\n"
                "Your mission is to organize information.\n"
                "You summarize without adding your own conjectures; present it as it is.\n"
                "Divide the content into segments according to topic, "
                "and mark the start and end timestamps for each topic.\n"
                "Add supplementary information after each topic that is not included "
                "in the main topic but exists within it.\n"
                "Finally, provide an overall summary."
            ),
        },
        {
            "role": "user",
            "content": (
                "The following is a cleaned transcript of an automatic-speech-recognition:\n"
                f"```\n{cleaned_merged}\n```\n\n"
                "Please summarize it by organizing into topic-based segments with timestamps, "
                "and provide an overall summary at the end."
            ),
        },
    ]

    response = await llm_client.chat.completions.create(
        model=llm_name,
        messages=summary_messages,
        max_tokens=12000,
        temperature=1.0,
        top_p=0.95,
        extra_body={"top_k": 64, "chat_template_kwargs": {"enable_thinking": True}},
    )
    final_text = response.choices[0].message.content
    if final_text is None:
        raise ValueError(
            "Summary response is None. "
            "Your thinking model might be stuck in a loop; please try again."
        )

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(final_text)


# --- 畫面提取 ---


async def run_workflow_transcribe_video(
    sem: asyncio.Semaphore,
    video: IOCacheVideo,
    audio_prompt: str,
    llm_name: str,
    llm_client: AsyncOpenAI,
    save_path: Path,
):
    fps = 1
    if save_path.exists():
        return

    async def process_slice(messages, start, end):
        async with sem:
            response = await llm_client.chat.completions.create(
                model=llm_name,
                messages=messages,
                max_tokens=12000,
                temperature=1.0,
                top_p=0.95,
                extra_body={
                    "top_k": 64,
                    "chat_template_kwargs": {"enable_thinking": True},
                },
            )
        result = response.choices[0].message.content
        if result is None:
            raise ValueError(
                "response is None, Your thinking model might be stuck in a loop; "
                "please try again."
            )
        return {"at": {"start": start, "end": end}, "result": result}

    tasks = []
    slices_indices = create_slices_indices(0, video.duration, window=20, step=20)
    with tqdm(total=len(slices_indices), desc="切圖", position=3) as pbar:
        for start, end in slices_indices:
            contents = [
                {
                    "type": "text",
                    "text": (
                        "The following is a transcript of automatic-speech-recognition "
                        "as an audio reference:\n```\n"
                        f"{audio_prompt}\n```\n\n"
                        "The following are frames from the video that were skipped "
                        "at {fps} FPS:"
                    ).format(fps=fps),
                },
            ]
            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful professional assistant. Your mission is "
                        "to objectively describe what you see in an image. Provide "
                        "a description of the content without guessing its meaning; "
                        "present it as it is, including the time you saw the content, "
                        "a clear description, and the connection between the images."
                    ),
                },
                {"role": "user", "content": contents},
            ]
            frames = video.get_frames(start, end, sample_fps=fps)
            frame_timestamps = np.linspace(start, end, len(frames), endpoint=False)
            for second, frame in zip(frame_timestamps, frames):
                contents.append({"type": "text", "text": f"[{second:0.2f}s]"})
                contents.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": pil_to_b64_url(frame)},
                    }
                )
            contents.append(
                {
                    "type": "text",
                    "text": (
                        "\n\nDescribe what you see in each picture here, "
                        "and which second you see it.\n\n"
                    ),
                }
            )
            tasks.append(process_slice(messages, start, end))
            pbar.update(1)

    with tqdm(total=len(tasks), desc="提取畫面", position=3) as pbar:
        results = await asyncio.gather(*[wrap_task(task, pbar) for task in tasks])

    with open(save_path, "w") as f:
        for result in results:
            write_jsonl(f, result)


# --- 影音清理 (chunked) ---


async def run_workflow_video_transcription_cleanup_chunked(
    llm_name: str,
    llm_client: AsyncOpenAI,
    transcription_path: Path,
    save_path: Path,
    chunk_size: int = 40,
    sem: asyncio.Semaphore = None,
):
    if is_cached(save_path):
        return

    transcription = list(read_jsonl(transcription_path))
    total_items = len(transcription)
    cleaned_parts = []

    async def process_chunk(messages, pbar: tqdm):
        try:
            async with sem:
                response = await llm_client.chat.completions.create(
                    model=llm_name,
                    messages=messages,
                    max_tokens=16384,
                    temperature=1.0,
                    top_p=0.95,
                    extra_body={
                        "top_k": 64,
                        "chat_template_kwargs": {"enable_thinking": True},
                    },
                )
        except Exception as e:
            raise RuntimeError(f"Failed at chunk processing: {e}")

        cleaned = response.choices[0].message.content
        if cleaned is None:
            raise ValueError(
                "Response is None. "
                "Your thinking model might be stuck in a loop; please try again."
            )

        cleaned_parts.append(cleaned.strip())
        pbar.update(1)

    tasks = []
    with tqdm(total=total_items, desc="清理影音逐字稿", position=3) as pbar:
        for i in range(0, total_items, chunk_size):
            chunk = transcription[i : i + chunk_size]
            current_chunk_idx = (i // chunk_size) + 1
            total_chunks = (total_items + chunk_size - 1) // chunk_size

            prompt_buffer = StringIO()
            for item in chunk:
                start = item["at"]["start"]
                end = item["at"]["end"]
                prompt_buffer.write(f"[{start:0.2f}s ~ {end:0.2f}s] ")
                prompt_buffer.write(item["result"].strip())
                prompt_buffer.write("\n")

            messages = [
                {
                    "role": "system",
                    "content": (
                        "You are a helpful professional assistant.\n"
                        "Your mission is to clean up the transcription.\n"
                        "You simply reduce redundancy without adding summaries "
                        "or merging sentences yourself; you present it as it is."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"The following is a visual transcript of video "
                        f"(Part {current_chunk_idx}/{total_chunks}):\n"
                        f"```\n{prompt_buffer.getvalue()}```\n\n"
                        "You reduce redundancy and provide clean text.\n"
                        "Include time, differences, and what viewers can see."
                    ),
                },
            ]
            tasks.append(process_chunk(messages, pbar))

        await asyncio.gather(*tasks)

    cleaned_merged = "\n---\n".join(cleaned_parts)

    # 第二輪：整體總結
    summary_messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful professional assistant.\n"
                "Your mission is to organize information.\n"
                "You summarize without adding your own conjectures; present it as it is.\n"
                "Divide the content into segments according to topic, "
                "and mark the start and end timestamps for each topic.\n"
                "Add supplementary information after each topic that is not included "
                "in the main topic but exists within it.\n"
                "Finally, provide an overall summary."
            ),
        },
        {
            "role": "user",
            "content": (
                "The following is a cleaned visual transcript of video:\n"
                f"```\n{cleaned_merged}\n```\n\n"
                "Please summarize it by organizing into topic-based segments "
                "with timestamps, and provide an overall summary at the end."
            ),
        },
    ]

    response = await llm_client.chat.completions.create(
        model=llm_name,
        messages=summary_messages,
        max_tokens=12000,
        temperature=1.0,
        top_p=0.95,
        extra_body={"top_k": 64, "chat_template_kwargs": {"enable_thinking": True}},
    )
    final_text = response.choices[0].message.content
    if final_text is None:
        raise ValueError(
            "Summary response is None. "
            "Your thinking model might be stuck in a loop; please try again."
        )

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(final_text)


# --- 總結 ---


async def run_workflow_summarize(
    llm_name: str,
    llm_client: AsyncOpenAI,
    video_transcription_path: Path,
    audio_transcription_path: Path,
    save_path: Path,
):
    if is_cached(save_path):
        return

    video_transcription = video_transcription_path.read_text()
    audio_transcription = audio_transcription_path.read_text()

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful professional assistant.\n"
                "Your mission is to organize information.\n"
                "You summarize without adding your own conjectures; "
                "present it as it is."
            ),
        },
        {
            "role": "user",
            "content": (
                "These materials come from the same record.\n"
                "You combine the audio and video information, divide it into "
                "segments according to topic, and mark the start and end "
                "timestamps for each topic.\n"
                "You add supplementary information after each topic that is "
                "not included in the main topic but exists within it.\n"
                "Finally, you provide an overall summary.\n\n"
                f"The following is a audio transcript of an automatic-speech-recognition:\n"
                f"```\n{audio_transcription}```\n\n"
                f"The following is a visual transcript of video:\n"
                f"```\n{video_transcription}```\n\n"
                "You summarize it."
            ),
        },
    ]

    response = await llm_client.chat.completions.create(
        model=llm_name,
        messages=messages,
        max_tokens=12000,
        temperature=1.0,
        top_p=0.95,
        extra_body={"top_k": 64, "chat_template_kwargs": {"enable_thinking": True}},
    )
    cleaned = response.choices[0].message.content
    if cleaned is None:
        raise ValueError(
            "response is None, Your thinking model might be stuck in a loop; "
            "please try again."
        )
    with open(save_path, "w") as f:
        f.write(cleaned)


async def run_single_file_llm(
    video_path: Path,
    llm_name: str,
    llm_client: AsyncOpenAI,
    llm_batch_size: int,
):
    """對單一檔案執行 Phase 2：所有 LLM 工作。"""
    save_dir = video_path.parent / video_path.stem / "results"
    save_dir.mkdir(exist_ok=True, parents=True)

    audio_transcription_dir = save_dir / "audio_transcriptions"
    audio_transcription_cleaned_path = save_dir / "audio_transcriptions_cleaned.md"

    video_transcription_dir = save_dir / "video_transcriptions"
    video_transcription_dir.mkdir(exist_ok=True)
    video_transcription_path = video_transcription_dir / "transcription.jsonl"
    video_transcription_cleaned_path = save_dir / "video_transcriptions_cleaned.md"

    summary_path = save_dir / "summary.md"

    llm_sem = asyncio.Semaphore(llm_batch_size)

    with IOCacheVideo(video_path, cached=True) as video:
        # ── 1. 音軌清理 ──────────────────────────────────────────
        if is_cached(audio_transcription_cleaned_path):
            tqdm.write(f"[{video_path.name}] ① 音軌清理 - 已存在，跳過")
        else:
            tqdm.write(f"[{video_path.name}] ① 音軌清理...")
            transcription_paths = [
                audio_transcription_dir / f"track_{i}.jsonl"
                for i in range(len(video.audio_streams))
            ]
            await run_workflow_audio_transcription_cleanup_chunked(
                llm_name=llm_name,
                llm_client=llm_client,
                transcription_paths=transcription_paths,
                save_path=audio_transcription_cleaned_path,
                sem=llm_sem,
            )

        # ── 2. 畫面提取 ───────────────────────────────────────────
        if is_cached(video_transcription_path):
            tqdm.write(f"[{video_path.name}] ② 畫面提取 - 已存在，跳過")
        else:
            tqdm.write(f"[{video_path.name}] ② 畫面提取...")
            audio_prompt = audio_transcription_cleaned_path.read_text()
            await run_workflow_transcribe_video(
                sem=llm_sem,
                video=video,
                audio_prompt=audio_prompt,
                llm_name=llm_name,
                llm_client=llm_client,
                save_path=video_transcription_path,
            )

        # ── 3. 影音清理 ──────────────────────────────────────────
        if is_cached(video_transcription_cleaned_path):
            tqdm.write(f"[{video_path.name}] ③ 影音清理 - 已存在，跳過")
        else:
            tqdm.write(f"[{video_path.name}] ③ 影音清理...")
            await run_workflow_video_transcription_cleanup_chunked(
                llm_name=llm_name,
                llm_client=llm_client,
                transcription_path=video_transcription_path,
                save_path=video_transcription_cleaned_path,
                sem=llm_sem,
            )

        # ── 4. 總結 ──────────────────────────────────────────────
        if is_cached(summary_path):
            tqdm.write(f"[{video_path.name}] ④ 總結 - 已存在，跳過")
        else:
            tqdm.write(f"[{video_path.name}] ④ 總結...")
            await run_workflow_summarize(
                llm_name=llm_name,
                llm_client=llm_client,
                video_transcription_path=video_transcription_cleaned_path,
                audio_transcription_path=audio_transcription_cleaned_path,
                save_path=summary_path,
            )

    tqdm.write(f"[{video_path.name}] Phase 2 完成")


# ──────────────────────────── 批次掃描 ────────────────────────────


def _collect_video_paths(video_root: Path):
    """收集所有 .mp4 / .mkv 檔案並排序。"""
    return sorted([f for f in video_root.rglob("*") if f.suffix in VIDEO_EXTENSIONS])


async def scan_and_run_phase1(
    video_root: Path,
    asr_name: str,
    asr_client: AsyncOpenAI,
    asr_batch_size: int,
    max_concurrent: int = 1,
):
    """掃整目錄，對所有檔案執行 Phase 1 (ASR)。"""
    video_paths = _collect_video_paths(video_root)
    tqdm.write(f"Phase 1 — 共 {len(video_paths)} 個檔案，開始 ASR 辨識")

    sem = asyncio.Semaphore(max_concurrent)
    futures = [
        asyncio.create_task(
            _run_one_file_asr_wrapper(
                video_path, asr_name, asr_client, asr_batch_size, sem
            )
        )
        for video_path in video_paths
    ]

    for f in tqdm(
        asyncio.as_completed(futures), total=len(futures), desc="Phase 1 總進度"
    ):
        try:
            await f
        except Exception as e:
            tqdm.write(f"Error: {e}")

    tqdm.write("Phase 1 全部完成！現在可以手動切換 LLM 伺服器，然後執行 Phase 2。")


async def _run_one_file_asr_wrapper(
    video_path: Path,
    asr_name: str,
    asr_client: AsyncOpenAI,
    asr_batch_size: int,
    sem: asyncio.Semaphore,
):
    async with sem:
        await run_single_file_asr(video_path, asr_name, asr_client, asr_batch_size)


async def scan_and_run_phase2(
    video_root: Path,
    llm_name: str,
    llm_client: AsyncOpenAI,
    llm_batch_size: int,
    max_concurrent: int = 1,
):
    """掃整目錄，對所有檔案執行 Phase 2 (LLM)。"""
    video_paths = _collect_video_paths(video_root)
    tqdm.write(f"Phase 2 — 共 {len(video_paths)} 個檔案，開始 LLM 處理")

    sem = asyncio.Semaphore(max_concurrent)
    futures = [
        asyncio.create_task(
            _run_one_file_llm_wrapper(
                video_path, llm_name, llm_client, llm_batch_size, sem
            )
        )
        for video_path in video_paths
    ]

    for f in tqdm(
        asyncio.as_completed(futures), total=len(futures), desc="Phase 2 總進度"
    ):
        try:
            await f
        except Exception as e:
            tqdm.write(f"Error: {e}")

    tqdm.write("Phase 2 全部完成！")


async def _run_one_file_llm_wrapper(
    video_path: Path,
    llm_name: str,
    llm_client: AsyncOpenAI,
    llm_batch_size: int,
    sem: asyncio.Semaphore,
):
    async with sem:
        await run_single_file_llm(video_path, llm_name, llm_client, llm_batch_size)


# ──────────────────────────── VAD 階段 ────────────────────────────


def run_phase_vad(video_root: Path, workers: int) -> None:
    """平行掃完整個目錄，對所有音軌跑 VAD 並快取結果。

    每部影片只開一次 IOCacheVideo，跑完所有軌道再 close。
    已快取的影片只讀 JSON 檔，不 open 影片。
    """
    from concurrent.futures import as_completed

    video_paths = _collect_video_paths(video_root)
    if not video_paths:
        tqdm.write(f"[VAD] 在 {video_root} 找不到任何 .mp4 / .mkv 檔案")
        return

    from src.utils.video import IOCacheVideo

    work_items: list[tuple[Path, int]] = []
    cached_count = 0

    for video_path in video_paths:
        cache_path = vad_cache_path(video_path)

        # 快取已存在 → 只讀 JSON 就知道軌道數
        if cache_path.exists():
            all_cache = load_all_vad_cache(video_path)
            cached_count += len(all_cache)
            for track_idx in all_cache.keys():
                tqdm.write(f"[VAD] {video_path.name} track {track_idx}: 已快取，跳過")
            continue

        # 無快取才 open 影片
        try:
            with IOCacheVideo(video_path, cached=True) as video:
                for track_idx in range(len(video.audio_streams)):
                    if not has_vad_cache(video_path, track_idx):
                        work_items.append((video_path, track_idx))
                    else:
                        tqdm.write(
                            f"[VAD] {video_path.name} track {track_idx}: 已快取，跳過"
                        )
        except Exception as exc:
            tqdm.write(f"[VAD] 讀取 {video_path.name} 失敗: {exc}")

    if not work_items:
        tqdm.write(f"[VAD] 所有音軌已快取，無需處理")
        return

    total_tracks = len(work_items)
    tqdm.write(f"[VAD] 共 {len(video_paths)} 個檔案、{total_tracks} 個音軌要處理")
    tqdm.write(f"[VAD] 平行數: {workers}")

    processed_count = 0
    start_time = __import__("time").monotonic()

    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(vad_process_one, str(vp), ti): (vp, ti)
            for vp, ti in work_items
        }

        with tqdm(total=total_tracks, desc="[VAD] 總進度") as pbar:
            for future in as_completed(futures):
                vpath, track_idx = futures[future]
                try:
                    seg_count = future.result()
                    if seg_count is not None and seg_count > 0:
                        processed_count += 1
                        tqdm.write(
                            f"[VAD] {vpath.name} track {track_idx}: {seg_count} segments"
                        )
                    else:
                        cached_count += 1
                        tqdm.write(
                            f"[VAD] {vpath.name} track {track_idx}: 靜音，快取空"
                        )
                except Exception as exc:
                    tqdm.write(f"[VAD] {vpath.name} track {track_idx}: ERROR - {exc}")
                    import traceback

                    traceback.print_exc()
                finally:
                    pbar.update(1)

    elapsed = __import__("time").monotonic() - start_time
    tqdm.write(
        f"[VAD] 完成！處理 {processed_count} 個音軌，靜音 {cached_count} 個，共用 {elapsed:.1f}s"
    )


# ──────────────────────────── CLI 入口 ────────────────────────────


async def main_async():
    parser = argparse.ArgumentParser(description="Video2Text 兩階段處理")
    parser.add_argument(
        "--phase",
        choices=["vad", "asr", "llm"],
        default=None,
        help="執行階段：vad (預跑 VAD) / asr (Phase 1) / llm (Phase 2)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help="視訊資料夾路徑 (預設: VIDEO_ROOT)",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="單一測試檔案 (僅用於快速測試)",
    )
    parser.add_argument("--asr-name", default=None, help="ASR 模型名稱")
    parser.add_argument("--llm-name", default=None, help="LLM 模型名稱")
    parser.add_argument("--asr-batch", type=int, default=64, help="ASR 并发數量")
    parser.add_argument("--llm-batch", type=int, default=32, help="LLM 并发數量")
    parser.add_argument(
        "--max-workers", type=int, default=2, help="批次掃描最大并行檔案數"
    )
    parser.add_argument(
        "--vad-workers", type=int, default=1, help="VAD 平行處理數量 (預設: 16)"
    )

    args = parser.parse_args()

    video_dir = args.dir or VIDEO_ROOT
    asr_name = args.asr_name or DEFAULT_ASR_NAME
    llm_name = args.llm_name or DEFAULT_LLM_NAME
    asr_batch = args.asr_batch
    llm_batch = args.llm_batch
    max_workers = args.max_workers
    vad_workers = args.vad_workers

    asr_client = AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:8750/v1",
    )
    llm_client = AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:65500/v1",
    )

    # 快速測試：單一檔案
    if args.file:
        tqdm.write(f"快速測試: {args.file}")

        if args.phase == "vad":
            # 單一檔案 VAD 測試
            from src.utils.vad_cache import vad_cache_path

            try:
                with IOCacheVideo(args.file, cached=False) as video:
                    for track_idx in range(len(video.audio_streams)):
                        if vad_cache_path(args.file).is_file():
                            tqdm.write(
                                f"[{args.file.name}] track {track_idx}: 已快取，跳過"
                            )
                            continue

                        seg_count = vad_process_one(str(args.file), track_idx)
                        if seg_count > 0:
                            tqdm.write(
                                f"[{args.file.name}] track {track_idx}: {seg_count} segments"
                            )
                        else:
                            tqdm.write(
                                f"[{args.file.name}] track {track_idx}: 靜音，快取空"
                            )
            except Exception as exc:
                tqdm.write(f"[{args.file.name}] VAD 處理失敗: {exc}")
                import traceback

                traceback.print_exc()
            return

        if args.phase == "asr":
            await run_single_file_asr(args.file, asr_name, asr_client, asr_batch)
            return

        if args.phase == "llm":
            await run_single_file_llm(args.file, llm_name, llm_client, llm_batch)
            return

        # 預設行為：完整跑完
        tqdm.write("未指定 --phase，完整跑完 ASR + LLM")
        await run_single_file_asr(args.file, asr_name, asr_client, asr_batch)
        await run_single_file_llm(args.file, llm_name, llm_client, llm_batch)
        return

    # 明確指定階段
    if args.phase == "vad":
        run_phase_vad(video_dir, vad_workers)
        return

    if args.phase == "asr":
        await scan_and_run_phase1(
            video_dir, asr_name, asr_client, asr_batch, max_workers
        )
        return

    if args.phase == "llm":
        await scan_and_run_phase2(
            video_dir, llm_name, llm_client, llm_batch, max_workers
        )
        return

    # 預設行為：只跑一個檔案的完整流程 (測試)
    video_paths = _collect_video_paths(video_dir)
    if not video_paths:
        tqdm.write(f"[警告] 在 {video_dir} 找不到任何 .mp4 / .mkv 檔案")
        return

    # 取第一個檔案做快速測試
    test_file = video_paths[0]
    tqdm.write(f"預設模式 — 對單一檔案測試完整流程: {test_file}")
    tqdm.write("使用 --phase asr / --phase llm 執行批次掃描")

    await run_single_file_asr(test_file, asr_name, asr_client, asr_batch)
    await run_single_file_llm(test_file, llm_name, llm_client, llm_batch)


if __name__ == "__main__":
    asyncio.run(main_async())
