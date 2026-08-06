"""Speech-to-Text 工作流程：Speaker 辨識 + 語音轉文字

整合 voicetag (Speaker Diarization) + Breeze-ASR-26 (STT) 的端到端流程：

1. 從參考資料夾自動註冊 speaker
2. 對輸入音訊執行 speaker diarization
3. 將每個 segment 送給 Breeze-ASR-26 轉錄
4. 輸出「誰在何時講了什麼」的 JSON

Usage (CLI):
    # 使用預設 config.yaml (device=auto)
    uv run --python=3.10 --directory serve/voicetag -- python ../workflows/speech-to-text.py

    # 指定自訂 config
    uv run --python=3.10 --directory serve/voicetag -- python ../workflows/speech-to-text.py --config my-config.yaml

    # 覆蓋參數
    uv run --python=3.10 --directory serve/voicetag -- python ../workflows/speech-to-text.py \
        --input test-audio/meeting_30s.wav \
        --output output/test-result.json

Usage (import):
    from workflows.speech_to_text import run_pipeline

    result = run_pipeline(
        input_audio="test-audio/meeting.wav",
        speaker_ref_dir="test-audio/speaker-ref",
        output_json="output/result.json",
    )
"""

from __future__ import annotations

# ── 修正 sys.path 優先級，避免 circular import ──────────────
# workflows/voicetag.py 和 voicetag package 同名。當 PYTHONPATH
# 把專案根目錄加到 sys.path 時，Python 會找到 workflows/voicetag.py
# 而不是 site-packages/voicetag。這裡先把 voicetag package
# 載入 sys.modules，後續 import 就不会被遮蔽。
import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any, Optional

_voicetag_pkg_dir = (
    Path(__file__).resolve().parent.parent
    / "serve"
    / "voicetag"
    / ".venv"
    / "lib"
    / "python3.10"
    / "site-packages"
    / "voicetag"
)
if _voicetag_pkg_dir.is_dir():
    _spec = importlib.util.spec_from_file_location(
        "voicetag", _voicetag_pkg_dir / "__init__.py"
    )
    _voicetag_mod = importlib.util.module_from_spec(_spec)
    sys.modules["voicetag"] = _voicetag_mod
    _spec.loader.exec_module(_voicetag_mod)

import yaml


def resolve_device(config_device: str) -> str:
    """將 ``"auto"`` 轉換為實際裝置，否則回傳原值.

    Parameters
    ----------
    config_device:
        來自 config.yaml 的 device 設定，``"auto"`` / ``"cpu"`` / ``"cuda:0"`` 等。

    Returns
    -------
    str
        ``"cuda:0"`` (若 CUDA 可用)、``"cpu"`` 或其他原始值。
    """
    if config_device.lower() != "auto":
        return config_device

    try:
        import torch

        if torch.cuda.is_available():
            device = "cuda:0"
        else:
            device = "cpu"
    except ImportError:
        device = "cpu"

    print(f"[speech-to-text] 自動偵測：device=auto → {device}")
    return device


# Load .env before importing voicetag
_env_file = Path(__file__).resolve().parent.parent / "serve" / "voicetag" / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(str(_env_file))
    except ImportError:
        pass
del _env_file

from voicetag import VoiceTag, VoiceTagConfig  # noqa: E402


def load_config(config_path: str | Path) -> dict[str, Any]:
    """載入 YAML 設定檔."""
    path = Path(config_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def discover_speakers(speaker_ref_dir: str | Path) -> list[str]:
    """從參考資料夾自動發現 speaker 名稱.

    規則：目錄內所有 .wav/.mp3/.flac 的檔案名稱（不含副檔名）即為 speaker 名稱。

    Returns
    -------
    list[str]
        按字母排序的 speaker 名稱列表
    """
    ref_dir = Path(speaker_ref_dir)
    if not ref_dir.is_dir():
        print(f"[speech-to-text] 警告：參考資料夾不存在：{ref_dir}，跳過 speaker 註冊")
        return []

    audio_exts = {".wav", ".mp3", ".flac", ".ogg"}
    speakers = []
    for f in sorted(ref_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in audio_exts:
            speakers.append(f.stem)

    print(f"[speech-to-text] 發現 {len(speakers)} 位 speaker：{speakers}")
    return speakers


def run_pipeline(
    input_audio: str | Path,
    speaker_ref_dir: str | Path | None = None,
    output_json: str | Path | None = None,
    config_path: str | Path | None = None,
    device: str = "auto",
    similarity_threshold: float = 0.5,
    base_url: str = "http://localhost:8750/v1",
    stt_model: str = "MediaTek-Research/Breeze-ASR-26",
    stt_provider: str = "openai",
    stt_language: str = "zh",
    stt_api_key: str = "breeze-asr",
    hf_token: str | None = None,
) -> dict[str, Any]:
    """執行完整的 Speech-to-Text 流程.

    Parameters
    ----------
    input_audio:
        輸入音訊檔路徑。
    speaker_ref_dir:
        Speaker 參考音訊資料夾。檔案名稱 = speaker 名稱。
        如果為 None，則不會註冊 speaker（ diarization 會標記為 UNKNOWN）。
    output_json:
        輸出 JSON 檔案路徑。如果為 None，則只印到終端機。
    config_path:
        YAML 設定檔路徑。如果提供，會與參數合併（參數優先覆蓋）。
    device:
        運算裝置：``"auto"``（自動偵測）、``"cpu"`` 或 ``"cuda:0"`` 等。
    similarity_threshold:
        聲紋比對閾值 (0.0–1.0)。
    base_url:
        Breeze-ASR-26 的 OpenAI 相容 API endpoint。
    stt_model:
        STT 模型名稱。
    stt_provider:
        STT 提供者（預設 ``"openai"``，支援 OpenAI 相容 API）。
    stt_language:
        語言提示（例如 ``"zh"`` 中文、``"en"`` 英文）。
    stt_api_key:
        API key（自部署只要非空字串即可）。
    hf_token:
        HuggingFace token（用於 pyannote 模型）。從 ``.env`` 自動載入。

    Returns
    -------
    dict[str, Any]
        JSON 可序列化的結果。
    """
    # ── Step 0: 載入 config ──────────────────────────────────────
    if config_path:
        cfg = load_config(config_path)
        stt_cfg = cfg.get("speech_to_text", {}).get("stt", {})
        vt_cfg = cfg.get("speech_to_text", {}).get("voicetag", {})

        # 參數優先：直接傳入的參數覆蓋 config.yaml
        base_url = stt_cfg.get("base_url", base_url)
        stt_model = stt_cfg.get("model", stt_model)
        stt_provider = stt_cfg.get("provider", stt_provider)
        stt_language = stt_cfg.get("language", stt_language)
        stt_api_key = stt_cfg.get("api_key", stt_api_key)
        device = vt_cfg.get("device", device)
        similarity_threshold = vt_cfg.get("similarity_threshold", similarity_threshold)

    # ── 解析 device (auto → cuda/cpu) ────────────────────────────
    device = resolve_device(device)

    input_audio = Path(input_audio)
    if not input_audio.exists():
        raise FileNotFoundError(f"輸入音訊不存在：{input_audio}")

    print(f"[speech-to-text] ═══════════════════════════════════════════")
    print(f"[speech-to-text] 音訊：{input_audio.name}")
    print(f"[speech-to-text] Speaker 參考：{speaker_ref_dir}")
    print(f"[speech-to-text] 輸出：{output_json}")
    print(f"[speech-to-text] 裝置：{device}")
    print(f"[speech-to-text] STT：{stt_provider} @ {base_url}")
    print(f"[speech-to-text] ═══════════════════════════════════════════")

    # ── Step 1: 初始化 VoiceTag ──────────────────────────────────
    print("\n[step 1] 初始化 VoiceTag...")
    config = VoiceTagConfig(
        hf_token=hf_token,
        device=device,
        similarity_threshold=similarity_threshold,
    )
    vt = VoiceTag(config=config)
    print(f"[step 1] VoiceTag 已就緒 (device={device})")

    # ── Step 2: 註冊 Speaker ─────────────────────────────────────
    if speaker_ref_dir:
        print("\n[step 2] 註冊 Speaker...")
        speakers = discover_speakers(speaker_ref_dir)
        for name in speakers:
            ref_files = list(Path(speaker_ref_dir).glob(f"{name}.*"))
            # Filter only audio files
            ref_files = [
                f
                for f in ref_files
                if f.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg"}
            ]
            if ref_files:
                profile = vt.enroll(name, [str(f) for f in ref_files])
                print(f"  ✓ 已註冊 speaker「{name}」({profile.num_samples} 個樣本)")
            else:
                print(f"  ⚠ 找不到 speaker「{name}」的音訊檔")
        print(f"[step 2] 共註冊 {len(vt.enrolled_speakers)} 位 speaker")
    else:
        print("\n[step 2] 跳過 Speaker 註冊（ diarization 將標記為 UNKNOWN）")

    # ── Step 3: 執行轉錄（Diarization + STT） ────────────────────
    print(f"\n[step 3] 執行轉錄（speaker diarization + {stt_provider} STT）...")
    t_start = time.monotonic()

    transcript_result = vt.transcribe(
        audio_path=str(input_audio),
        provider=stt_provider,
        api_key=stt_api_key,
        model=stt_model,
        language=stt_language,
        base_url=base_url,
    )

    processing_time = time.monotonic() - t_start
    print(
        f"[step 3] 完成：{len(transcript_result.segments)} 個 segment，"
        f"{transcript_result.num_speakers} 位 speaker，"
        f"{processing_time:.1f}s"
    )

    # ── Step 4: 建構輸出 ─────────────────────────────────────────
    output: dict[str, Any] = {
        "input_audio": str(input_audio),
        "audio_duration": round(transcript_result.audio_duration, 3),
        "num_speakers": transcript_result.num_speakers,
        "processing_time": round(processing_time, 3),
        "stt_provider": stt_provider,
        "stt_model": stt_model,
        "device": device,
        "speakers_enrolled": list(vt.enrolled_speakers),
        "segments": [],
    }

    for seg in transcript_result.segments:
        segment: dict[str, Any] = {
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "duration": round(seg.end - seg.start, 3),
            "speaker": seg.speaker,
            "text": seg.text,
            "confidence": round(seg.confidence, 4) if seg.confidence else 0.0,
        }
        output["segments"].append(segment)

    # ── Step 5: 輸出結果 ─────────────────────────────────────────
    if output_json:
        out_path = Path(output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\n[step 5] 結果已儲存至：{out_path}")

    # 同時印到 stdout
    print(f"\n{'=' * 60}")
    print(f"完整結果 ({len(output['segments'])} segments)：")
    print(f"{'=' * 60}")
    print(json.dumps(output, indent=2, ensure_ascii=False))

    return output


def main():
    """CLI 入口."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Speech-to-Text：Speaker 辨識 + 語音轉文字 (voicetag + Breeze-ASR)"
    )
    parser.add_argument(
        "--config",
        "-c",
        default=str(Path(__file__).parent / "config.yaml"),
        help="YAML 設定檔路徑 (default: workflows/config.yaml)",
    )
    parser.add_argument("--input", "-i", default=None, help="覆蓋 input_audio")
    parser.add_argument("--output", "-o", default=None, help="覆蓋 output_json")
    parser.add_argument(
        "--device",
        default=None,
        choices=["auto", "cpu", "cuda:0", "cuda:1"],
        help="覆蓋運算裝置 (default: auto，自動偵測)",
    )
    parser.add_argument("--speaker-dir", default=None, help="覆蓋 speaker_ref_dir")
    parser.add_argument(
        "--base-url",
        default=None,
        help="覆蓋 STT endpoint (default: http://localhost:8750/v1)",
    )
    parser.add_argument("--hf-token", default=None, help="HuggingFace token")

    args = parser.parse_args()

    # 載入 config
    cfg = load_config(args.config)
    stt_cfg = cfg.get("speech_to_text", {}).get("stt", {})
    vt_cfg = cfg.get("speech_to_text", {}).get("voicetag", {})

    # 預設值
    input_audio = args.input or cfg.get("speech_to_text", {}).get(
        "input_audio", "test-audio/保修工程會議.wav"
    )
    speaker_ref_dir = args.speaker_dir or cfg.get("speech_to_text", {}).get(
        "speaker_ref_dir", "test-audio/speaker-ref"
    )
    output_json = args.output or cfg.get("speech_to_text", {}).get(
        "output_json", "output/speech_to_text_result.json"
    )

    run_pipeline(
        input_audio=input_audio,
        speaker_ref_dir=speaker_ref_dir,
        output_json=output_json,
        config_path=None,  # 已經手動合併了
        device=args.device or vt_cfg.get("device", "auto"),
        similarity_threshold=vt_cfg.get("similarity_threshold", 0.5),
        base_url=args.base_url or stt_cfg.get("base_url", "http://localhost:8750/v1"),
        stt_model=stt_cfg.get("model", "MediaTek-Research/Breeze-ASR-26"),
        stt_provider=stt_cfg.get("provider", "openai"),
        stt_language=stt_cfg.get("language", "zh"),
        stt_api_key=stt_cfg.get("api_key", "breeze-asr"),
        hf_token=args.hf_token,
    )


if __name__ == "__main__":
    main()
