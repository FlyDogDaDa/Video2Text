import base64
import json
import re

import requests

# 設定引數
AUDIO_FILE = "intro_voice_cover.wav"
ASR_URL = "http://localhost:8750/v1/audio/transcriptions"
ALIGNER_URL = "http://localhost:8752/pooling"


def main():
    # -------------------------------------------------------------
    # 第一步：呼叫 Breeze-ASR-26 進行語音轉錄 (Port 8750)
    # -------------------------------------------------------------
    print("【第一步】正在進行語音轉錄 (Breeze-ASR-26)...")

    try:
        with open(AUDIO_FILE, "rb") as f:
            files = {"file": (AUDIO_FILE, f, "audio/wav")}
            data = {"model": "MediaTek-Research/Breeze-ASR-26"}
            asr_response = requests.post(ASR_URL, files=files, data=data)
    except FileNotFoundError:
        print(f"錯誤：在當前目錄找不到音檔 {AUDIO_FILE}")
        return
    except requests.exceptions.ConnectionError:
        print(f"錯誤：無法連線到 ASR 伺服器 ({ASR_URL})，請確認 Port 8750 服務已開啟。")
        return

    if asr_response.status_code != 200:
        print(
            f"轉錄失敗，狀態碼: {asr_response.status_code}，錯誤訊息: {asr_response.text}"
        )
        return

    # 取得轉錄出來的逐字稿
    transcribed_text = asr_response.json().get("text", "").strip()
    print(f"✨ 轉錄成功！內容為：\n「{transcribed_text}」\n")

    if not transcribed_text:
        print("轉錄結果為空，無法進行後續對齊。")
        return

    # -------------------------------------------------------------
    # 第二步：動態構建對齊用的 Prompt 格式
    # -------------------------------------------------------------
    print("【第二步】正在智慧切分文本並構建對齊 Prompt...")

    # 智慧拆分：英文單字保留（如 Craft, Panel）、中文按單字拆分（忽略空格）
    tokens = re.findall(r"[a-zA-Z0-9'-]+|[\u4e00-\u9fff]", transcribed_text)

    # 拼接格式：<|audio_start|><|audio_pad|><|audio_end|>字1<timestamp><timestamp>字2...
    prompt_body = "<timestamp><timestamp>".join(tokens) + "<timestamp><timestamp>"
    align_prompt = f"<|audio_start|><|audio_pad|><|audio_end|>{prompt_body}"

    # -------------------------------------------------------------
    # 第三步：將音檔轉為 Base64，並傳送至對齊模型 (Port 8752)
    # -------------------------------------------------------------
    print("【第三步】正在將音檔與 Prompt 送往對齊模型 (Qwen3-ForcedAligner)...")

    # 將音檔編碼為 Base64 字串
    with open(AUDIO_FILE, "rb") as f:
        audio_base64 = base64.b64encode(f.read()).decode("utf-8")

    # 組裝請求 Payload
    align_payload = {
        "model": "Qwen/Qwen3-ForcedAligner-0.6B",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "audio_url",
                        "audio_url": {"url": f"data:audio/wav;base64,{audio_base64}"},
                    },
                    {"type": "text", "text": align_prompt},
                ],
            }
        ],
    }

    try:
        headers = {"Content-Type": "application/json"}
        align_response = requests.post(ALIGNER_URL, headers=headers, json=align_payload)
    except requests.exceptions.ConnectionError:
        print(
            f"錯誤：無法連線到對齊伺服器 ({ALIGNER_URL})，請確認 Port 8752 服務已開啟。"
        )
        return

    if align_response.status_code != 200:
        print(
            f"對齊失敗，狀態碼: {align_response.status_code}，錯誤訊息: {align_response.text}"
        )
        return

    align_result = align_response.json()["data"][0]["data"]
    import numpy as np

    align_result = np.array(align_result)
    print("🎉 對齊服務呼叫成功！以下為模型回傳結果（Pooling 資料）：")
    print(align_result.argmax(axis=1))
    # print(json.dumps(len(align_result), indent=2, ensure_ascii=False))


# uv pip install qwen-asr torchaudio

if __name__ == "__main__":
    main()
