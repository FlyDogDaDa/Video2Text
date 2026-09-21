# Token Classify

Source: https://github.com/vllm-project/vllm/tree/main/examples/pooling/token_classify

## Forced Alignment Offline

```python
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
# Adapted from Qwen3-ForcedAligner inference:
# https://github.com/QwenLM/Qwen3-ASR

"""
Offline forced alignment example using Qwen3-ForcedAligner-0.6B.

Forced alignment takes audio and reference text as input and produces
word-level timestamps. The model predicts a time bin at each <timestamp>
token position; multiplying by ``timestamp_segment_time`` gives milliseconds.

Usage::

    python forced_alignment_offline.py \
        --model Qwen/Qwen3-ForcedAligner-0.6B
"""

from argparse import Namespace

import numpy as np

from vllm import LLM, EngineArgs
from vllm.utils.argparse_utils import FlexibleArgumentParser

def parse_args():
    parser = FlexibleArgumentParser()
    parser = EngineArgs.add_cli_args(parser)
    parser.set_defaults(
        model="Qwen/Qwen3-ForcedAligner-0.6B",
        runner="pooling",
        enforce_eager=True,
        hf_overrides={"architectures": ["Qwen3ASRForcedAlignerForTokenClassification"]},
    )
    return parser.parse_args()

def build_prompt(words: list[str]) -> str:
    """Build the forced alignment prompt from a word list.

    Format:  <audio-prefix>
            word1<timestamp><timestamp>word2<timestamp><timestamp>...
    """
    body = "<timestamp><timestamp>".join(words) + "<timestamp><timestamp>"
    return f"<audio-prefix>{body}"

def main(args: Namespace):
    llm = LLM(**vars(args))

    config = llm.llm_engine.vllm_config.model_config.hf_config
    timestamp_token_id = config.timestamp_token_id
    timestamp_segment_time = config.timestamp_segment_time

    # Example: align these words against a 5-second audio clip
    words = ["Hello", "world"]
    prompt = build_prompt(words)

    # Use a 5-second silent audio as placeholder (replace with real audio)
    sample_rate = 16000
    audio = np.zeros(sample_rate * 5, dtype=np.float32)

    outputs = llm.encode(
        [{"prompt": prompt, "multi_modal_data": {"audio": audio}}],
        pooling_task="token_classify",
    )

    for output in outputs:
        logits = output.outputs.data  # [num_tokens, classify_num]
        predictions = logits.argmax(dim=-1)
        token_ids = output.prompt_token_ids

        # Extract timestamps at <timestamp> positions
        ts_predictions = [
            pred.item() * timestamp_segment_time
            for tid, pred in zip(token_ids, predictions)
            if tid == timestamp_token_id
        ]

        # Pair up start/end times per word
        for i, word in enumerate(words):
            start_ms = ts_predictions[i * 2]
            end_ms = ts_predictions[i * 2 + 1]
            print(f"{word:15s} {start_ms / 1000:.3f}s - {end_ms / 1000:.3f}s")

if __name__ == "__main__":
    args = parse_args()
    main(args)

```

## Forced Alignment Online

```python
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
# Adapted from Qwen3-ForcedAligner inference:
# https://github.com/QwenLM/Qwen3-ASR

"""
Online forced alignment example using Qwen3-ForcedAligner-0.6B.

Forced alignment takes audio and reference text as input and produces
word-level timestamps. The model predicts a time bin at each <timestamp>
token position; multiplying by ``timestamp_segment_time`` gives milliseconds.

Start the server with:

    vllm serve Qwen/Qwen3-ForcedAligner-0.6B \\
        --runner pooling \\
        --enforce-eager \\
        --trust-request-chat-template \\
        --hf-overrides \\
        '{"architectures": ["Qwen3ASRForcedAlignerForTokenClassification"]}'

Then run:

    python forced_alignment_online.py
"""

import argparse
import json
import mimetypes
import wave
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pybase64 as base64
import requests
import torch
from huggingface_hub import hf_hub_download

RAW_CONTENT_CHAT_TEMPLATE = "{{ messages[0]['content'] }}"

def build_prompt(words: list[str]) -> str:
    """Build the forced alignment prompt from a word list.

    Format:  <audio-prefix>
            word1<timestamp><timestamp>word2<timestamp><timestamp>...
    """
    body = "<timestamp><timestamp>".join(words) + "<timestamp><timestamp>"
    return f"<audio-prefix>{body}"

def encode_audio_data_uri(audio_path: Path) -> str:
    mime_type = mimetypes.guess_type(audio_path)[0] or "audio/wav"
    audio_base64 = base64.b64encode(audio_path.read_bytes()).decode("utf-8")
    return f"data:{mime_type};base64,{audio_base64}"

def encode_silent_wav_data_uri(sample_rate: int = 16000, duration_s: int = 5) -> str:
    audio = np.zeros(sample_rate * duration_s, dtype=np.int16)

    with BytesIO() as audio_buffer:
        with wave.open(audio_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(np.dtype(np.int16).itemsize)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(audio.tobytes())

    audio_base64 = base64.b64encode(audio_buffer.getvalue()).decode("utf-8")
    return f"data:audio/wav;base64,{audio_base64}"

def build_payload(model: str, prompt: str, audio_uri: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "audio_url", "audio_url": {"url": audio_uri}},
                ],
            }
        ],
        "task": "token_classify",
        "chat_template": RAW_CONTENT_CHAT_TEMPLATE,
    }

def post_http_request(payload: dict[str, Any], api_url: str) -> requests.Response:
    headers = {"User-Agent": "Test Client"}
    return requests.post(api_url, headers=headers, json=payload)

def parse_response(response: requests.Response) -> dict[str, Any]:
    try:
        result = response.json()
    except ValueError as exc:
        raise RuntimeError(
            f"Server returned non-JSON response: {response.text}"
        ) from exc

    if response.status_code != 200 or "data" not in result:
        raise RuntimeError(f"Server error ({response.status_code}): {result}")

    return result

def load_timestamp_config(model: str) -> tuple[int, float]:
    model_path = Path(model)
    config_path = (
        model_path / "config.json"
        if model_path.exists()
        else Path(hf_hub_download(repo_id=model, filename="config.json"))
    )

    with config_path.open() as f:
        config = json.load(f)

    return config["timestamp_token_id"], config["timestamp_segment_time"]

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--model",
        type=str,
        default="Qwen/Qwen3-ForcedAligner-0.6B",
    )
    parser.add_argument(
        "--audio-path",
        type=Path,
        default=None,
        help="Optional audio file. Defaults to a 5-second silent WAV.",
    )
    parser.add_argument(
        "--words",
        nargs="+",
        default=["Hello", "world"],
        help="Reference words to align against the audio.",
    )
    return parser.parse_args()

def main(args):
    from transformers import AutoTokenizer

    api_url = f"http://{args.host}:{args.port}/pooling"
    prompt = build_prompt(args.words)
    audio_uri = (
        encode_audio_data_uri(args.audio_path)
        if args.audio_path
        else encode_silent_wav_data_uri()
    )
    payload = build_payload(args.model, prompt, audio_uri)

    pooling_response = post_http_request(payload=payload, api_url=api_url)
    result = parse_response(pooling_response)

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    timestamp_token_id, timestamp_segment_time = load_timestamp_config(args.model)

    output = result["data"][0]
    logits = torch.tensor(output["data"])
    predictions = logits.argmax(dim=-1)
    token_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    audio_pad_token_id = tokenizer.convert_tokens_to_ids("<|AUDIO_PAD|>")

    usage = result.get("usage") or {}
    prompt_tokens = usage.get("prompt_tokens")
    if prompt_tokens is not None and prompt_tokens != len(predictions):
        raise RuntimeError(
            "The response length does not match the reported prompt token count."
        )

    try:
        audio_pad_index = token_ids.index(audio_pad_token_id)
    except ValueError as exc:
        raise RuntimeError("The prompt does not contain the audio pad token.") from exc

    audio_token_shift = len(predictions) - len(token_ids)
    if audio_token_shift < 0:
        raise RuntimeError(
            "The response is shorter than the locally tokenized prompt. "
            "Check that the server was started with --trust-request-chat-template."
        )

    ts_predictions = []
    for i, token_id in enumerate(token_ids):
        if token_id != timestamp_token_id:
            continue

        prediction_index = i + audio_token_shift if i > audio_pad_index else i
        ts_predictions.append(
            predictions[prediction_index].item() * timestamp_segment_time
        )

    if len(ts_predictions) < len(args.words) * 2:
        raise RuntimeError("The model did not return enough timestamp predictions.")

    for i, word in enumerate(args.words):
        start_ms = ts_predictions[i * 2]
        end_ms = ts_predictions[i * 2 + 1]
        print(f"{word:15s} {start_ms / 1000:.3f}s - {end_ms / 1000:.3f}s")

if __name__ == "__main__":
    args = parse_args()
    main(args)

```

## NER Offline

```python
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
# Adapted from https://huggingface.co/boltuix/NeuroBERT-NER

"""
Offline example using boltuix/NeuroBERT-NER.

Usage::

    python ner_offline.py
"""

from argparse import Namespace

from vllm import LLM, EngineArgs
from vllm.utils.argparse_utils import FlexibleArgumentParser

def parse_args():
    parser = FlexibleArgumentParser()
    parser = EngineArgs.add_cli_args(parser)
    parser.set_defaults(
        model="boltuix/NeuroBERT-NER",
        runner="pooling",
        trust_remote_code=True,
    )
    return parser.parse_args()

def main(args: Namespace):
    llm = LLM(**vars(args))

    prompts = [
        "Barack Obama visited Microsoft headquarters in Seattle in January 2025."
    ]
    tokenizer = llm.get_tokenizer()
    label_map = llm.llm_engine.vllm_config.model_config.hf_config.id2label

    # Run inference
    outputs = llm.encode(prompts, pooling_task="token_classify")

    for prompt, output in zip(prompts, outputs):
        logits = output.outputs.data  # [num_tokens, num_labels]
        predictions = logits.argmax(dim=-1)

        # Map predictions to labels
        tokens = tokenizer.convert_ids_to_tokens(output.prompt_token_ids)
        labels = [label_map[p.item()] for p in predictions]

        # Print token-label pairs
        for token, label in zip(tokens, labels):
            if token not in tokenizer.all_special_tokens:
                print(f"{token:15s} -> {label}")

if __name__ == "__main__":
    args = parse_args()
    main(args)

```

## NER Online

```python
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
# Adapted from https://huggingface.co/boltuix/NeuroBERT-NER

"""
Online example using boltuix/NeuroBERT-NER via the Pooling API.

Run `vllm serve <model> --runner pooling`
to start up the vLLM server. e.g.

    vllm serve boltuix/NeuroBERT-NER

Then run:

    python ner_online.py
"""

import argparse
import requests
import torch

def post_http_request(prompt: dict, api_url: str) -> requests.Response:
    headers = {"User-Agent": "Test Client"}
    response = requests.post(api_url, headers=headers, json=prompt)
    return response

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", type=str, default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--model",
        type=str,
        default="boltuix/NeuroBERT-NER",
    )
    return parser.parse_args()

def main(args):
    from transformers import AutoConfig, AutoTokenizer

    api_url = f"http://{args.host}:{args.port}/pooling"
    model_name = args.model

    # Load tokenizer and config
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    config = AutoConfig.from_pretrained(model_name)
    label_map = config.id2label

    # Input text
    text = "Barack Obama visited Microsoft headquarters in Seattle in January 2025."

    prompt = {"model": model_name, "input": text}

    pooling_response = post_http_request(prompt=prompt, api_url=api_url)
    result = pooling_response.json()

    # Run inference
    output = result["data"][0]
    logits = torch.tensor(output["data"])
    predictions = logits.argmax(dim=-1)
    inputs = tokenizer(text, return_tensors="pt")

    # Map predictions to labels
    tokens = tokenizer.convert_ids_to_tokens(inputs["input_ids"][0])
    labels = [label_map[p.item()] for p in predictions]
    assert len(tokens) == len(predictions)

    # Print token-label pairs
    for token, label in zip(tokens, labels):
        if token not in tokenizer.all_special_tokens:
            print(f"{token:15s} -> {label}")

if __name__ == "__main__":
    args = parse_args()
    main(args)

```
