#!/usr/bin/env python3
"""QuarkAudio-UniSE TSE 推理流程"""

import sys
from pathlib import Path

# 專案根目錄 (Video2Text/)
PROJECT_ROOT = Path(__file__).parent.parent

# 加入 quark_audio API 路徑
sys.path.insert(0, str(PROJECT_ROOT / "serve" / "quark-audio"))

from quark_audio.api import extract_target_speaker


def main():
    # 使用相對於專案根的路徑
    mix_path = PROJECT_ROOT / "test-audio" / "2026_07_21_test_30s.mp3"
    enroll_path = PROJECT_ROOT / "test-audio" / "speech-reference.mp3"
    output_path = PROJECT_ROOT / "output" / "tse_result.wav"

    print("=" * 60)
    print("QuarkAudio-UniSE TSE 推理")
    print("=" * 60)
    print(f"專案根目錄: {PROJECT_ROOT}")
    print(f"混合音訊：{mix_path}")
    print(f"參考音訊：{enroll_path}")
    print(f"輸出路徑：{output_path}")
    print("=" * 60)

    # 建立輸出目錄
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 執行 TSE
    result = extract_target_speaker(str(mix_path), str(enroll_path), str(output_path))

    print("=" * 60)
    print(f"推理完成！輸出：{result}")
    print("=" * 60)


if __name__ == "__main__":
    main()
