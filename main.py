"""Video2Text console test — pipeline end-to-end (audio + video)."""

"""
╔══════════════╗
║ 綠色椰子口味 ║
║ 乖 乖 █ █    ║
║ 有 綠 █ █    ║
║ 保 必 █ █    ║
║ 庇 備 █ █    ║
╚══════════════╝
┏━━━━━━━━━━━━━━┓
┃    乖  乖    ┃
┃   綠色椰子   ┃
┃  保佑程式碼  ┃
┃   穩定運作   ┃
┗━━━━━━━━━━━━━━┛
"""


# from __future__ import annotations

import asyncio
import base64
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from functools import cache
from io import BytesIO, StringIO
from itertools import batched
from itertools import count as Counter
from pathlib import Path

import numpy as np

# Load .env from project root
from dotenv import load_dotenv
from openai import AsyncOpenAI
from PIL.Image import Image as PILImage
from scipy.io import wavfile
from silero_vad import get_speech_timestamps, load_silero_vad
from silero_vad.utils_vad import OnnxWrapper as VAD_OnnxWrapper
from tqdm.asyncio import tqdm

from src.utils import IOCacheVideo, create_slices_indices, read_jsonl, write_jsonl

load_dotenv()

SAMPLING_RATE = 16_000
PBAR_COUNT = Counter()


@cache
def load_vad_model() -> VAD_OnnxWrapper:
    return load_silero_vad()


def is_cached(path: Path) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size > 0


async def wrap_task(task, pbar: tqdm):
    res = await task  # 執行原本的辨識任務
    pbar.update(1)  # 做完一項，進度條就前進一格（這裡是執行緒/非同步安全的）
    return res


async def transcribe_audio(
    sem: asyncio.Semaphore,
    start: int,
    end: int,
    model_name: str,
    client: AsyncOpenAI,
    sound: np.ndarray | BytesIO,
    language: str = "zh",
    prompt: str = "",
    do_vad: bool = True,
) -> dict[str, str | dict[str, int]]:
    if isinstance(sound, np.ndarray):
        if do_vad:
            speech_timestamps = get_speech_timestamps(
                sound,
                load_vad_model(),
                threshold=0.8,
                sampling_rate=SAMPLING_RATE,
                min_speech_duration_ms=500,
            )
            if not speech_timestamps:
                return {"at": {"start": start, "end": end}, "result": ""}

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
    # check if save path exists
    if is_cached(save_path):
        return

    slices_indices = create_slices_indices(0, video.duration, window=10, step=2)

    # check if audio track is empty
    if not np.any(
        video.get_audio(
            0,
            video.duration,
            max_clip_duration=video.duration,
            audio_streams=[track_index],
        )
    ):
        with open(save_path, "a") as f:
            for start, end in slices_indices:
                # write empty result for empty audio track
                write_jsonl(f, {"at": dict(start=start, end=end), "result": ""})
        return  # return early if audio track is empty

    # slice audio into chunks
    tasks = []
    with tqdm(total=len(slices_indices), desc="切音訊") as pbar:
        for start, end in slices_indices:
            sound = video.get_audio(start=start, end=end, audio_streams=[track_index])
            tasks.append(
                transcribe_audio(  # transcribe all tracks
                    sem=sem,
                    start=start,
                    end=end,
                    model_name=asr_name,
                    client=asr_client,
                    prompt="忽略背景雜訊與無聲段落 以空格分割 僅轉錄說話內容 轉錄下列這段音訊的逐字稿",
                    sound=sound[0],
                )
            )
            pbar.update(1)

    with tqdm(total=len(tasks), desc="提取音訊") as pbar:
        results = await asyncio.gather(*[wrap_task(task, pbar) for task in tasks])

    # save results
    with open(save_path, "a") as f:
        for result in results:
            write_jsonl(f, result)


async def run_workflow_audio_transcription_cleanup(
    llm_name: str,
    llm_client: AsyncOpenAI,
    transcription_paths: list[Path],
    save_path: Path,
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

    text_buffer = StringIO()
    for (start, end), result in results.items():
        if not result:
            continue
        text_buffer.write(f"[{start:0.2f}s ~ {end:0.2f}s]\n")
        text_buffer.write("\n".join(result))
        text_buffer.write("\n\n")

    transcription = text_buffer.getvalue()
    messages = [
        {
            "role": "system",
            "content": "You are a helpful professional assistant.\nYour mission is to clean up the transcription.\nYou simply reduce redundancy without adding summaries or merging sentences yourself; you present it as it is.",
        },
        {
            "role": "user",
            "content": f"The following is a transcript of an automatic-speech-recognition:\n```\n{transcription}```\n\nYou reduce redundancy and provide clean subtitles.\nInclude time, dialogue, and tracks.",
        },
    ]
    response = await llm_client.chat.completions.create(
        model=llm_name,
        messages=messages,
        max_tokens=12000,  # 32_768
        temperature=1.0,
        top_p=0.95,
        extra_body={"top_k": 64, "chat_template_kwargs": {"enable_thinking": True}},
    )
    cleaned = response.choices[0].message.content
    if cleaned is None:
        raise ValueError(
            "response is None, Your thinking model might be stuck in a loop; please try again."
        )
    with open(save_path, "w") as f:
        f.write(cleaned)


async def run_workflow_audio_transcription_cleanup_chunked(
    llm_name: str,
    llm_client: AsyncOpenAI,
    transcription_paths: list[Path],
    save_path: Path,
    chunk_size: int = 20,  # 每次處理的合併時間區間數量，可依需求調整
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

    # 過濾掉沒有內容的時間區間，以利精準分片
    valid_results = [
        ((start, end), tracks) for (start, end), tracks in results.items() if tracks
    ]
    total_items = len(valid_results)

    async def process_chunk(messages, chunk_idx: int):
        try:
            async with sem:
                response = await llm_client.chat.completions.create(
                    model=llm_name,
                    messages=messages,
                    max_tokens=16000,  # 分片後單次輸出較少，可調低以節省資源並防範截斷
                    temperature=1.0,
                    top_p=0.95,
                    extra_body={
                        "top_k": 64,
                        "chat_template_kwargs": {"enable_thinking": True},
                    },
                )
        except Exception as e:
            raise RuntimeError(f"Failed at chunk {chunk_idx}: {e}")

        cleaned = response.choices[0].message.content
        if cleaned is None:
            raise ValueError(
                f"Response is None at chunk {chunk_idx}. "
                "Your thinking model might be stuck in a loop; please try again."
            )
        return cleaned.strip()

    # 將合併後的音軌內容分批處理
    tasks = []
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
                    f"The following is a transcript of an automatic-speech-recognition (Part {current_chunk_idx}/{total_chunks}):\n"
                    f"```\n{prompt_buffer.getvalue()}```\n\n"
                    "You reduce redundancy and provide clean subtitles.\n"
                    "Include time, dialogue, and tracks."
                ),
            },
        ]
        # 將 current_chunk_idx 作為參數傳入，避免閉包變數綁定錯誤
        tasks.append(process_chunk(messages, current_chunk_idx))

    # 等待所有任務完成，asyncio.gather 會保持與 tasks 相同的順序
    cleaned_parts = await asyncio.gather(*tasks)

    # 合併所有處理好的區段
    final_cleaned_text = "\n\n---\n\n".join(cleaned_parts)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(final_cleaned_text)


def pil_to_b64_url(image: PILImage) -> str:
    """Convert a PIL image to a base64-encoded data URI."""
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return f"data:image/jpeg;base64,{base64.b64encode(buffer.getvalue()).decode()}"


async def run_workflow_transcribe_video(
    sem: asyncio.Semaphore,
    video: IOCacheVideo,
    audio_prompt: str,
    llm_name: str,
    llm_client: AsyncOpenAI,
    save_path: Path,
):
    fps = 1
    # check if save path exists
    if save_path.exists():
        return

    async def process_slice(messages, start, end):
        async with sem:
            response = await llm_client.chat.completions.create(
                model=llm_name,
                messages=messages,
                max_tokens=12000,  # 32_768
                temperature=1.0,
                top_p=0.95,
                extra_body={
                    "top_k": 64,
                    "chat_template_kwargs": {"enable_thinking": True},
                },
                # timeout=float("inf"),
            )
        result = response.choices[0].message.content
        if result is None:
            raise ValueError(
                "response is None, Your thinking model might be stuck in a loop; please try again."
            )
        return {
            "at": {"start": start, "end": end},
            "result": result,
        }

    tasks = []
    slices_indices = create_slices_indices(0, video.duration, window=20, step=10)
    with tqdm(total=len(slices_indices), desc="切圖") as pbar:
        for start, end in slices_indices:
            contents = [
                {
                    "type": "text",
                    "text": f"The following is a transcript of automatic-speech-recognition as an audio reference:\n```\n{audio_prompt}\n```\n\nThe following are frames from the video that were skipped at {fps} FPS:",
                },
            ]
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful professional assistant. Your mission is to objectively describe what you see in an image. Provide a description of the content without guessing its meaning; present it as it is, including the time you saw the content, a clear description, and the connection between the images.",
                },
                {"role": "user", "content": contents},
            ]
            frames = video.get_frames(start, end, sample_fps=fps)
            frame_timestamps = np.linspace(start, end, len(frames), endpoint=False)
            for second, frame in zip(frame_timestamps, frames):
                contents.append({"type": "text", "text": f"[{second:0.2f}s]"})
                contents.append(
                    {"type": "image_url", "image_url": {"url": pil_to_b64_url(frame)}}
                )
            contents.append(
                {
                    "type": "text",
                    "text": "\n\nDescribe what you see in each picture here, and which second you see it.\n\n",
                }
            )
            tasks.append(process_slice(messages, start, end))
            pbar.update(1)

    with tqdm(total=len(tasks), desc="提取畫面") as pbar:
        results = await asyncio.gather(*[wrap_task(task, pbar) for task in tasks])

    with open(save_path, "w") as f:
        for result in results:
            write_jsonl(f, result)


async def run_workflow_video_transcription_cleanup(
    llm_name: str,
    llm_client: AsyncOpenAI,
    transcription_path: Path,
    save_path: Path,
):
    if is_cached(save_path):
        return
    transcription = read_jsonl(transcription_path)
    prompt_buffer = StringIO()
    for item in transcription:
        start = item["at"]["start"]
        end = item["at"]["end"]
        prompt_buffer.write(f"[{start:0.2f}s ~ {end:0.2f}s] ")
        prompt_buffer.write(item["result"].strip())
        prompt_buffer.write("\n")

    messages = [
        {
            "role": "system",
            "content": "You are a helpful professional assistant.\nYour mission is to clean up the transcription.\nYou simply reduce redundancy without adding summaries or merging sentences yourself; you present it as it is.",
        },
        {
            "role": "user",
            "content": f"The following is a visual transcript of video:\n```\n{prompt_buffer.getvalue()}```\n\nYou reduce redundancy and provide clean text.\nInclude time, differences, and what viewers can see.",
        },
    ]
    response = await llm_client.chat.completions.create(
        model=llm_name,
        messages=messages,
        max_tokens=12000,  # 32_768
        temperature=1.0,
        top_p=0.95,
        extra_body={"top_k": 64, "chat_template_kwargs": {"enable_thinking": True}},
    )
    cleaned = response.choices[0].message.content
    if cleaned is None:
        raise ValueError(
            "response is None, Your thinking model might be stuck in a loop; please try again."
        )
    with open(save_path, "w") as f:
        f.write(cleaned)


async def run_workflow_video_transcription_cleanup_chunked(
    llm_name: str,
    llm_client: AsyncOpenAI,
    transcription_path: Path,
    save_path: Path,
    chunk_size: int = 30,  # 每次處理的逐字稿條數，可依需求調整
    sem: asyncio.Semaphore = None,
):
    if is_cached(save_path):
        return

    transcription = list(read_jsonl(transcription_path))
    total_items = len(transcription)
    cleaned_parts = []

    async def process_chunk(messages):
        try:
            async with sem:
                response = await llm_client.chat.completions.create(
                    model=llm_name,
                    messages=messages,
                    max_tokens=16384,  # 單次分片內容較少，可調低 max_tokens 以節省資源並防範輸出截斷
                    temperature=1.0,
                    top_p=0.95,
                    extra_body={
                        "top_k": 64,
                        "chat_template_kwargs": {"enable_thinking": True},
                    },
                )
        except Exception as e:
            # 記錄錯誤或進行重試邏輯
            raise RuntimeError(f"Failed at chunk {current_chunk_idx}: {e}")

        cleaned = response.choices[0].message.content
        if cleaned is None:
            raise ValueError(
                f"Response is None at chunk {current_chunk_idx}. "
                "Your thinking model might be stuck in a loop; please try again."
            )

        cleaned_parts.append(cleaned.strip())

    # 將逐字稿分批處理
    tasks = []
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
                    "You simply reduce redundancy without adding summaries or merging sentences yourself; "
                    "you present it as it is."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"The following is a visual transcript of video (Part {current_chunk_idx}/{total_chunks}):\n"
                    f"```\n{prompt_buffer.getvalue()}```\n\n"
                    "You reduce redundancy and provide clean text.\n"
                    "Include time, differences, and what viewers can see."
                ),
            },
        ]
        tasks.append(process_chunk(messages))

    # 等待所有任務完成
    await asyncio.gather(*tasks)

    # 合併所有處理好的區段
    final_cleaned_text = "\n---\n".join(cleaned_parts)

    with open(save_path, "w", encoding="utf-8") as f:
        f.write(final_cleaned_text)


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
            "content": "You are a helpful professional assistant.\nYour mission is to organize information.\nYou summarize without adding your own conjectures; present it as it is.",
        },
        {
            "role": "user",
            "content": f"These materials come from the same record.\nYou combine the audio and video information, divide it into segments according to topic, and mark the start and end timestamps for each topic.\nYou add supplementary information after each topic that is not included in the main topic but exists within it.\nFinally, you provide an overall summary.\n\nThe following is a audio transcript of an automatic-speech-recognition:\n```\n{audio_transcription}```\n\nThe following is a visual transcript of video:\n```\n{video_transcription}```\n\nYou summarize it.",
        },
    ]
    response = await llm_client.chat.completions.create(
        model=llm_name,
        messages=messages,
        max_tokens=12000,  # 32_768
        temperature=1.0,
        top_p=0.95,
        extra_body={"top_k": 64, "chat_template_kwargs": {"enable_thinking": True}},
    )
    cleaned = response.choices[0].message.content
    if cleaned is None:
        raise ValueError(
            "response is None, Your thinking model might be stuck in a loop; please try again."
        )
    with open(save_path, "w") as f:
        f.write(cleaned)


async def run_workflow(
    video_path: Path,
    llm_name: str,
    asr_name: str,
    llm_client: AsyncOpenAI,
    asr_client: AsyncOpenAI,
    asr_batch_size: int,
    llm_batch_size: int,
):
    save_dir = video_path.parent / video_path.stem / "results"
    save_dir.mkdir(exist_ok=True, parents=True)

    audio_transcription_dir = save_dir / "audio_transcriptions"
    audio_transcription_dir.mkdir(exist_ok=True)
    audio_transcription_cleaned_path = save_dir / "transcriptions_cleaned.md"

    video_transcription_dir = save_dir / "video_transcriptions"
    video_transcription_dir.mkdir(exist_ok=True)
    video_transcription_cleaned_path = save_dir / "video_transcriptions_cleaned.md"

    summary_path = save_dir / "summary.md"
    asr_sem = asyncio.Semaphore(asr_batch_size)
    llm_sem = asyncio.Semaphore(llm_batch_size)

    #
    with tqdm(total=5, desc=video_path.name) as pbar:
        with IOCacheVideo(video_path, cached=True) as video:
            # Transcribe each audio track asynchronously
            tqdm.write("Transcribing audio tracks...")
            transcription_paths = [
                audio_transcription_dir / f"track_{track_index}.jsonl"
                for track_index in range(len(video.audio_streams))
            ]
            tasks = [
                (
                    run_workflow_transcribe_audio_track(
                        sem=asr_sem,
                        video=video,
                        asr_name=asr_name,
                        asr_client=asr_client,
                        track_index=track_index,
                        save_path=path,
                    )
                )
                for track_index, path in enumerate(transcription_paths)
            ]

            with tqdm(total=len(tasks), desc="處理音軌") as pbar:
                await asyncio.gather(*[wrap_task(task, pbar) for task in tasks])

            # Clean up audio transcriptions
            tqdm.write("Cleaning up audio transcriptions...")
            await run_workflow_audio_transcription_cleanup_chunked(
                llm_name=llm_name,
                llm_client=llm_client,
                transcription_paths=transcription_paths,
                save_path=audio_transcription_cleaned_path,
                sem=llm_sem,
            )
            pbar.update()

            # Transcribe video
            tqdm.write("Transcribing video...")
            video_transcription_path = video_transcription_dir / "transcription.jsonl"
            audio_prompt = audio_transcription_cleaned_path.read_text()
            await run_workflow_transcribe_video(
                sem=llm_sem,
                video=video,
                audio_prompt=audio_prompt,
                llm_name=llm_name,
                llm_client=llm_client,
                save_path=video_transcription_path,
            )
            pbar.update()

            # Clean up video transcriptions
            tqdm.write("Cleaning up video transcriptions...")
            await run_workflow_video_transcription_cleanup_chunked(
                llm_name=llm_name,
                llm_client=llm_client,
                transcription_path=video_transcription_path,
                save_path=video_transcription_cleaned_path,
                sem=llm_sem,
            )
            pbar.update()

            # Summarize
            tqdm.write("Summarizing...")
            await run_workflow_summarize(
                llm_name=llm_name,
                llm_client=llm_client,
                video_transcription_path=video_transcription_cleaned_path,
                audio_transcription_path=audio_transcription_cleaned_path,
                save_path=summary_path,
            )
            pbar.update()


def for_each_file(
    video_path: Path, asr_batch_size: int = 4, llm_batch_size: int = 1
) -> bool:
    llm_name = "google/gemma-4-12B-it-qat-w4a16-ct"
    asr_name = "MediaTek-Research/Breeze-ASR-26"
    llm_client = AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:65500/v1",
    )
    asr_client = AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:8750/v1",
    )
    try:
        asyncio.run(
            run_workflow(
                video_path=video_path,
                llm_name=llm_name,
                llm_client=llm_client,
                asr_name=asr_name,
                asr_batch_size=asr_batch_size,
                llm_batch_size=llm_batch_size,
                asr_client=asr_client,
            )
        )
        return True
    except Exception as e:
        import traceback

        traceback.print_exc()
        print(f"Error: {e}")
        return False


async def for_each_file_async(
    video_path: Path,
    asr_batch_size: int = 4,
    llm_batch_size: int = 1,
    sem: asyncio.Semaphore = None,
) -> bool:
    llm_name = "google/gemma-4-12B-it-qat-w4a16-ct"
    asr_name = "MediaTek-Research/Breeze-ASR-26"
    llm_client = AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:65500/v1",
    )
    asr_client = AsyncOpenAI(
        api_key="EMPTY",
        base_url="http://localhost:8750/v1",
    )
    async with sem:
        await run_workflow(
            video_path=video_path,
            llm_name=llm_name,
            llm_client=llm_client,
            asr_name=asr_name,
            asr_client=asr_client,
            asr_batch_size=asr_batch_size,
            llm_batch_size=llm_batch_size,
        )


async def main():
    # Settings
    if len(sys.argv) == 1:
        # short_test.mp4 #2026_03_17-20_27_48.mkv
        sem = asyncio.Semaphore(1)
        await for_each_file_async(
            Path("2026_03_17-20_27_48.mkv"),
            asr_batch_size=6,
            llm_batch_size=8,
            sem=sem,
        )
        return

    video_root = Path("/mnt/hdd/b11223209/螢幕錄影/2026_06/")
    video_paths = [f for f in video_root.rglob("*") if f.suffix in [".mp4", ".mkv"]]

    sem = asyncio.Semaphore(1)
    for video_path in video_paths:
        await for_each_file_async(video_path, 8, 8, sem)
    tqdm.write("All files processed")

    # sem = asyncio.Semaphore(2)
    # futures = [for_each_file_async(video_path, 3, 2, sem) for video_path in video_paths]
    # await asyncio.gather(*futures)
    # tqdm.write("All files processed")

    # error_count = 0
    # tqdm.write(f"Total files: {len(video_paths)}")
    # with ProcessPoolExecutor(max_workers=4) as executor:
    #     futures = [
    #         executor.submit(for_each_file, video_path, 3, 2)
    #         for video_path in video_paths
    #     ]
    #     for future in as_completed(futures):
    #         error_count += not future.result()

    # tqdm.write(f"All {len(video_paths)} files processed")
    # if error_count == 0:
    #     tqdm.write("No errors")
    # else:
    #     tqdm.write(f"Total errors: {error_count}")


import time
import traceback

if __name__ == "__main__":
    asyncio.run(main())
