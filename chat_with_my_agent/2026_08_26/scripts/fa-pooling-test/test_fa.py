#!/usr/bin/env python3
"""測試 Qwen3-ForcedAligner-0.6B（vLLM 部署，/pooling 端點）的時間對齊。

背景：
- 模型以 vLLM pooling（token_classify）模式部署，沒有 /v1/chat/completions。
- 每個 token 位置會輸出 5000 個時間桶（bin）的 logits，
  在 <timestamp> token 位置取 argmax × timestamp_segment_time(80ms) 即得該單位時間。
- 伺服器未開啟 --trust-request-chat-template，因此不能自訂 chat_template，
  改用伺服器的預設模板；用 /tokenize（同樣的 messages）取得實際 token 序列，
  再依據 audio pad 的擴充偏移量把 <timestamp> 對回正確位置。

用法:
    .venv/bin/python scripts/test_fa.py [--audio PATH] [--text TEXT]
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://10.46.219.5:8755"
MODEL = "Qwen/Qwen3-ForcedAligner-0.6B"
TIMESTAMP_TOKEN_ID = 151705
TIMESTAMP_SEGMENT_MS = 80  # config.json: timestamp_segment_time
CLASSIFY_NUM = 5000  # config.json: classify_num
AUDIO_PAD_TOKEN_ID = 151676
# 官方 forced_alignment_online.py 的前綴（< 與 > 用 unicode escape 避免寫入時被損毀）：
# <|audio_start|><|audio_pad|><|audio_end|>
PROMPT_PREFIX = (
    "\u003c|audio_start|\u003e\u003c|audio_pad|\u003e\u003c|audio_end|\u003e"
)
# 官方 forced_alignment_online.py 的 raw-content 模板：
# 讓伺服器把 messages[0] 的 content 直接當 prompt，不套 vLLM 預設 chat template
# （預設模板會把 text part 丟掉，導致對齊全錯）。伺服器需以
# --trust-request-chat-template 啟動才接受自訂模板。
RAW_CONTENT_CHAT_TEMPLATE = "{{ messages[0]['content'] }}"


def split_text_units(text: str) -> list[str]:
    """切成對齊單位：CJK 單字各算一個單位，連續 ASCII 字母/數字併成一個單位。

    例: "是我用AI跑出來的" -> ["是", "我", "用", "AI", "跑", "出", "來", "的"]
    """
    units: list[str] = []
    buffer: list[str] = []

    def flush_ascii() -> None:
        if buffer:
            units.append("".join(buffer))
            buffer.clear()

    for char in text:
        if "\u4e00" <= char <= "\u9fff" or "\u3400" <= char <= "\u4dbf":
            flush_ascii()
            units.append(char)
        elif char.isascii() and char.isalnum():
            buffer.append(char)
        else:
            flush_ascii()
    flush_ascii()
    return [unit for unit in units if unit]


def build_prompt(words: list[str]) -> str:
    body = "<timestamp><timestamp>".join(words)
    return f"{PROMPT_PREFIX}{body}<timestamp><timestamp>"


def data_uri(content: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(content).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def probe_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def convert_to_wav(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(source),
            "-ar",
            "16000",
            "-ac",
            "1",
            "-sample_fmt",
            "s16",
            "-vn",
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )


def tokenize_messages(
    client: httpx.Client, messages: list[dict], base_url: str, model: str
) -> list[int]:
    """用與 /pooling 完全相同的 messages + chat_template 讓伺服器端 tokenize，
    確保 token 序列一致。"""
    response = client.post(
        f"{base_url}/tokenize",
        json={
            "model": model,
            "messages": messages,
            "return_token_strs": True,
            "chat_template": RAW_CONTENT_CHAT_TEMPLATE,
        },
        timeout=120,
    )
    response.raise_for_status()
    data = response.json()

    tokens = data.get("tokens", data)
    if isinstance(tokens, dict):
        for key in ("input_ids", "token_ids", "ids"):
            if key in tokens:
                return [int(x) for x in tokens[key]]
    if isinstance(tokens, list):
        return [int(x) for x in tokens]
    raise ValueError(
        f"不認識的 /tokenize 回應格式: {json.dumps(data, ensure_ascii=False)[:800]}"
    )


def argmax(row: list[float]) -> int:
    best_index = 0
    best_value = -float("inf")
    for index, value in enumerate(row):
        if value > best_value:
            best_value = value
            best_index = index
    return best_index


def parse_pooling_rows(raw: list, classify_num: int) -> list[list[float]]:
    if not raw:
        raise ValueError("pooling 回應沒有 data。")
    if isinstance(raw[0], list):
        return [[float(x) for x in row] for row in raw]
    flat = [float(x) for x in raw]
    if len(flat) % classify_num != 0:
        raise ValueError(
            f"flat pooling 長度 {len(flat)} 無法被 classify_num={classify_num} 整除。"
        )
    row_count = len(flat) // classify_num
    return [flat[i * classify_num : (i + 1) * classify_num] for i in range(row_count)]


def align_text_with_audio(
    client: httpx.Client, audio_path: Path, text: str, base_url: str, model: str
) -> dict:
    words = split_text_units(text)
    prompt = build_prompt(words)
    wav_path = audio_path.parent / "fa_test_16k_mono.wav"
    convert_to_wav(audio_path, wav_path)
    audio_uri = data_uri(wav_path.read_bytes(), "audio/wav")

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "audio_url", "audio_url": {"url": audio_uri}},
            ],
        }
    ]

    # 1) 先用 /tokenize 取得伺服器實際使用的 token 序列
    token_ids = tokenize_messages(client, messages, base_url, model)
    print(
        f"[diag] token 數 = {len(token_ids)}, audio_pad(151676) 存在 = {AUDIO_PAD_TOKEN_ID in token_ids}"
    )
    if AUDIO_PAD_TOKEN_ID in token_ids:
        print(f"[diag] audio_pad 位置 = {token_ids.index(AUDIO_PAD_TOKEN_ID)}")
    print(f"[diag] 前 20 tokens = {token_ids[:20]}")
    print(f"[diag] 後 10 tokens = {token_ids[-10:]}")

    # 2) 送 /pooling 拿每個 token 的時間桶 logits（官方做法：自訂 raw-content 模板）
    payload = {
        "model": model,
        "messages": messages,
        "task": "token_classify",
        "chat_template": RAW_CONTENT_CHAT_TEMPLATE,
    }
    start = time.monotonic()
    response = client.post(f"{base_url}/pooling", json=payload, timeout=300)
    latency_seconds = time.monotonic() - start
    if response.status_code != 200:
        raise RuntimeError(
            f"/pooling 回傳 {response.status_code}: {response.text[:1000]}"
        )
    data = response.json()
    if "data" not in data or not data["data"]:
        raise ValueError(
            f"pooling 回應缺 data: {json.dumps(data, ensure_ascii=False)[:1000]}"
        )

    rows = parse_pooling_rows(data["data"][0]["data"], CLASSIFY_NUM)
    predictions = [argmax(row) for row in rows]
    usage = data.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    print(f"[diag] predictions 數 = {len(predictions)}, 延遲 = {latency_seconds:.2f}s")
    if prompt_tokens is not None and prompt_tokens != len(predictions):
        print(
            f"[warn] usage.prompt_tokens={prompt_tokens} != predictions={len(predictions)}"
        )
    if len(predictions) < len(token_ids):
        raise ValueError(
            f"predictions 長度 {len(predictions)} 小於 tokenize 長度 {len(token_ids)}，對齊會失誤。"
        )

    # 3) 依 audio pad 前後計算 offset，把 <timestamp> 對到正確位置
    audio_token_shift = len(predictions) - len(token_ids)
    audio_pad_index = (
        token_ids.index(AUDIO_PAD_TOKEN_ID) if AUDIO_PAD_TOKEN_ID in token_ids else -1
    )
    print(f"[diag] audio_token_shift = {audio_token_shift}")

    timestamps_ms: list[float] = []
    for i, token_id in enumerate(token_ids):
        if token_id != TIMESTAMP_TOKEN_ID:
            continue
        prediction_index = (
            i + audio_token_shift
            if (audio_pad_index >= 0 and i > audio_pad_index)
            else i
        )
        if prediction_index >= len(predictions):
            raise ValueError(
                f"timestamp token 位置 {i} (+shift={audio_token_shift}) 超出 predictions 長度 {len(predictions)}。"
            )
        timestamps_ms.append(predictions[prediction_index] * TIMESTAMP_SEGMENT_MS)

    if len(timestamps_ms) < len(words) * 2:
        raise ValueError(
            f"預期 {len(words) * 2} 個 timestamp 預測，實際 {len(timestamps_ms)} 個。"
        )

    aligned = []
    for i, word in enumerate(words):
        start_ms = timestamps_ms[i * 2]
        end_ms = timestamps_ms[i * 2 + 1]
        aligned.append(
            {
                "unit": word,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "start_s": round(start_ms / 1000, 3),
                "end_s": round(end_ms / 1000, 3),
            }
        )

    return {
        "server": base_url.rstrip("/"),
        "model": model,
        "audio_path": str(audio_path),
        "text": text,
        "audio_duration_s": probe_audio_duration(audio_path),
        "prompt": prompt,
        "token_count": len(token_ids),
        "prediction_count": len(predictions),
        "audio_pad_index": audio_pad_index,
        "audio_token_shift": audio_token_shift,
        "usage_prompt_tokens": prompt_tokens,
        "latency_s": round(latency_seconds, 3),
        "alignments": aligned,
    }


def sanity_check(result: dict) -> bool:
    """檢查對齊結果是否合理（單調、在音訊長度內）。"""
    duration_ms = result["audio_duration_s"] * 1000
    ok = True
    prev_end = 0.0
    for item in result["alignments"]:
        if item["start_ms"] < prev_end - 1 or item["end_ms"] < item["start_ms"]:
            print(
                f"[warn] 非單調/倒序: {item['unit']} {item['start_ms']:.0f} -> {item['end_ms']:.0f}"
            )
            ok = False
        if item["end_ms"] > duration_ms * 1.1:
            print(
                f"[warn] 超出音訊長度: {item['unit']} end={item['end_ms']:.0f}ms > {duration_ms:.0f}ms"
            )
            ok = False
        prev_end = max(prev_end, item["end_ms"])
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(
        description="測試 Qwen3-ForcedAligner 的 /pooling 對齊"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--audio", default="output/是我用AI跑出來的.aac")
    parser.add_argument("--text", default="是我用AI跑出來的")
    parser.add_argument("--output", default="exp/N9boWvU-KkA/test_fa_result.json")
    args = parser.parse_args()

    audio_path = Path(args.audio)
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到音訊檔案: {audio_path}")

    base_url = args.base_url.rstrip("/")
    with httpx.Client() as client:
        result = align_text_with_audio(
            client, audio_path, args.text, base_url, args.model
        )

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n音訊: {audio_path} ({result['audio_duration_s']:.3f}s)")
    print(f"文字: {result['text']}")
    print(f"對齊結果（相對音訊起點）:")
    for item in result["alignments"]:
        print(f"  {item['start_s']:8.3f} - {item['end_s']:8.3f}  {item['unit']}")
    print(f"存檔: {output_path}")
    if not sanity_check(result):
        raise SystemExit("對齊結果 sanity check 未通過，請檢查上面 [warn] 行。")
    print("sanity check: OK")


if __name__ == "__main__":
    main()
