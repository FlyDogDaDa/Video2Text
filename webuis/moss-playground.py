#!/usr/bin/env python3
"""MOSS-Transcribe-Diarize Playground — 單頁 Gradio 體驗

頁面流程（由上而下）：
    1. 清空全部（最上方，重置整頁）
    2. 上傳音訊（上傳成功即自動送 vLLM 處理，無獨立處理按鈕）
    3. （選填）熱詞 → 請求的 prompt = model card default prompt＋「熱詞提示：…」
    4. 輸出（原文）：模型原始簡體文字（含 [start][Sxx]…[end] 標記）
    5. 最終輸出（僅在有原文輸出時顯示）：OpenCC s2t 繁體＋regex 解析的 segments JSON
    6. 狀態資訊
    7. 下載 JSON（最尾端，處理完成後下載 segments JSON）

啟動：
    uv run --project webuis webuis/moss-playground.py

環境變數：
    MOSS_VLLM_URL          預設 http://10.46.219.5:8750
    MOSS_PLAYGROUND_PORT   預設 7862

注意：vLLM build 有併發回應錯位風險（日誌 77），所有請求經 SERIAL_LOCK 串行。
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import gradio as gr
import httpx
import opencc

# ── 伺服器與模型 ──
VLLM_BASE_URL = os.environ.get("MOSS_VLLM_URL", "http://10.46.219.5:8750")
MODEL_ID = "OpenMOSS-Team/MOSS-Transcribe-Diarize"
TRANSCRIBE_URL = f"{VLLM_BASE_URL}/v1/audio/transcriptions"
REQUEST_TIMEOUT_S = 600.0
SERIAL_LOCK = threading.Lock()

# 下載用 JSON 存放於系統 temp 目錄（Gradio 允許回傳 tempdir 下的檔案路徑）
DOWNLOAD_DIR = Path(tempfile.gettempdir()) / "moss_playground_downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# model card 的 default prompt（全文）；熱詞走官方 recipe：default＋「熱詞提示：…」
DEFAULT_PROMPT = (
    "请将音频转写为文本，每一段需以起始时间戳和说话人编号（[S01]、[S02]、[S03]…）开头，"
    "正文为对应的语音内容，并在段末标注结束时间戳，以清晰标明该段语音范围。"
)

# MOSS canonical 輸出：[start][Sxx]text[end]，segments 串接、text 內可能含換行
SEGMENT_RE = re.compile(
    r"\[([0-9]+(?:\.[0-9]+)?)\]\[(S[0-9]+)\](.*?)\[([0-9]+(?:\.[0-9]+)?)\]",
    re.DOTALL,
)

# OpenCC s2t：逐字簡繁對照，不做常用詞（詞語層）轉換
_S2T = opencc.OpenCC("s2t")


def parse_segments(text: str) -> list[dict]:
    """以 regex 從 MOSS 原始輸出抽出 [start][Sxx]text[end] segments。"""
    return [
        {
            "start": float(start),
            "end": float(end),
            "speaker": speaker,
            "text": body.strip(),
        }
        for start, speaker, body, end in SEGMENT_RE.findall(text)
    ]


def build_prompt(hotwords: str | None) -> str | None:
    """有熱詞時回「default prompt＋熱詞提示」；否則不送 prompt（用 server 端 default）。

    hotwords 可能為 None（Gradio Textbox 空值），先擋掉再 split。
    """
    if not hotwords:
        return None
    words = [w.strip() for w in re.split(r"[,，]", hotwords) if w.strip()]
    if not words:
        return None
    return f"{DEFAULT_PROMPT}热词提示：{', '.join(words)}"


def transcribe(audio_path: str, hotwords: str = "") -> tuple[str, dict | None, float]:
    """POST 音訊給 vLLM，回傳 (text, usage, 秒數)。"""
    data: dict[str, str] = {"model": MODEL_ID, "response_format": "json"}
    prompt = build_prompt(hotwords)
    if prompt is not None:
        data["prompt"] = prompt

    name = Path(audio_path).name
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    t0 = time.time()
    with SERIAL_LOCK:
        with open(audio_path, "rb") as f:
            resp = httpx.post(
                TRANSCRIBE_URL,
                data=data,
                files={"file": (name, f, mime)},
                timeout=REQUEST_TIMEOUT_S,
            )
    elapsed = time.time() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"vLLM 回傳 {resp.status_code}：{resp.text[:500]}")
    body = resp.json()
    return body.get("text", ""), body.get("usage"), elapsed


def process(audio_path: str, hotwords: str = "") -> dict:
    """轉錄 → regex 解析 → OpenCC s2t。回傳供 UI 使用的 dict。"""
    raw_text, usage, elapsed = transcribe(audio_path, hotwords)
    segments = parse_segments(raw_text)
    tw_segments = [{**seg, "text": _S2T.convert(seg["text"])} for seg in segments]
    meta = f"⏱ {elapsed:.1f}s ｜ segments {len(segments)} ｜ usage {json.dumps(usage, ensure_ascii=False) if usage else 'n/a'}"
    return {
        "raw_text": raw_text,
        "tw_text": _S2T.convert(raw_text),
        "json_text": json.dumps(
            {"segments": tw_segments}, ensure_ascii=False, indent=2
        ),
        "meta": meta,
        "warning": ""
        if segments
        else "⚠ 未在文字中找到 [start][Sxx]…[end] 區段，JSON 為空",
    }


# ====================================================================
#  UI
# ====================================================================


def make_ui() -> gr.Blocks:
    with gr.Blocks(title="MOSS-TD Playground") as ui:
        gr.Markdown(
            "# 🎙️ MOSS-Transcribe-Diarize Playground\n\n"
            "單頁體驗：上傳音訊（上傳後自動處理）→ 輸出（原文）→ 最終輸出（繁體＋JSON）→ 下載 JSON\n\n"
            f"> 模型 `{MODEL_ID}` ｜ 伺服器 `{VLLM_BASE_URL}/v1`"
        )

        clear_all_btn = gr.Button("🧹 清空全部")

        audio_input = gr.File(label="上傳音訊", file_types=["audio"], type="filepath")

        with gr.Accordion("進階：熱詞（選填）", open=False):
            gr.Markdown(
                "提供時，請求的 prompt = model card default prompt＋「熱詞提示：…」"
                "（官方 recipe；`hotwords` form 欄位勿用）。"
            )
            hotwords_input = gr.Textbox(
                label="熱詞", placeholder="以逗號分隔，例如：潔心, 杰星"
            )

        raw_output = gr.Textbox(
            label="輸出（原文・簡體）",
            interactive=False,
            lines=15,
            max_lines=30,
        )

        final_group = gr.Group(visible=False)
        with final_group:
            gr.Markdown("## 最終輸出")
            tw_output = gr.Textbox(
                label="繁體文字（OpenCC s2t，不轉換常用詞）",
                interactive=False,
                lines=15,
                max_lines=30,
            )
            json_output = gr.Textbox(
                label="JSON（regex 解析 segments）",
                interactive=False,
                lines=15,
                max_lines=30,
            )

        status_md = gr.Markdown()

        download_btn = gr.DownloadButton(
            label="💾 下載 JSON",
            value=None,
            interactive=False,
        )

        def _audio_path(audio) -> str | None:
            if not audio:
                return None
            path = audio.path if hasattr(audio, "path") else audio
            return path if path and Path(path).is_file() else None

        def on_run(audio, hotwords):
            path = _audio_path(audio)
            if not path:
                yield (
                    "",
                    gr.update(visible=False),
                    "",
                    "",
                    gr.update(interactive=False),
                    "❌ 請先上傳音訊檔案",
                )
                return
            yield (
                "⏳ 處理中…",
                gr.update(visible=False),
                "",
                "",
                gr.update(interactive=False),
                f"⏳ 送 vLLM 中：{Path(path).name}",
            )
            try:
                r = process(path, hotwords or "")
                status = r["meta"] + (f"\n{r['warning']}" if r["warning"] else "")
                # 寫出 JSON 到 tempdir，供 DownloadButton 下載
                filename = f"moss_{time.strftime('%Y%m%d_%H%M%S')}.json"
                json_path = DOWNLOAD_DIR / filename
                json_path.write_text(r["json_text"], encoding="utf-8")
                yield (
                    r["raw_text"],
                    gr.update(visible=True),
                    r["tw_text"],
                    r["json_text"],
                    gr.update(value=str(json_path), interactive=True),
                    status,
                )
            except Exception as e:
                yield (
                    "",
                    gr.update(visible=False),
                    "",
                    "",
                    gr.update(interactive=False),
                    f"❌ 處理失敗：{e}",
                )

        def on_clear_all():
            return (
                None,
                "",
                "",
                gr.update(visible=False),
                "",
                "",
                gr.update(value=None, interactive=False),
                "✅ 已清空",
            )

        audio_input.upload(
            fn=on_run,
            inputs=[audio_input, hotwords_input],
            outputs=[
                raw_output,
                final_group,
                tw_output,
                json_output,
                download_btn,
                status_md,
            ],
        )
        clear_all_btn.click(
            fn=on_clear_all,
            inputs=None,
            outputs=[
                audio_input,
                hotwords_input,
                raw_output,
                final_group,
                tw_output,
                json_output,
                download_btn,
                status_md,
            ],
        )

    return ui


def main() -> None:
    port = int(os.environ.get("MOSS_PLAYGROUND_PORT", "7862"))
    make_ui().launch(server_name="0.0.0.0", server_port=port)


if __name__ == "__main__":
    main()
