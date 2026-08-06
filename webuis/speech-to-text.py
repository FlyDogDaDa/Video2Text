#!/usr/bin/env python3
"""Speech-to-Text Web UI — Gradio

簡易 WebUI 整合 workflows/speech-to-text.py 的完整流程：
- 上傳音訊檔案 → 執行 speaker diarization + STT → 下載 JSON 結果
- Speaker 參考檔案管理（上傳、改名、刪除）

Usage:
    uv run --directory serve/voicetag -- python -m webuis.speech_to_text
    # 或
    VIRTUAL_ENV=serve/voicetag/.venv \
    PYTHONPATH=$(pwd) \
    serve/voicetag/.venv/bin/python webuis/speech-to-text.py
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
import threading
from pathlib import Path

import gradio as gr

# ── Path 設定：讓 import workflows.speech_to_text 能找到 ──
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# ── voicetag circular import 修復 ──
_voicetag_pkg_dir = (
    _project_root
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

# ── 匯入主工作流程 ──
_s2t_module = importlib.util.spec_from_file_location(
    "speech_to_text",
    _project_root / "workflows" / "speech-to-text.py",
)
_s2t_mod = importlib.util.module_from_spec(_s2t_module)
_s2t_module.loader.exec_module(_s2t_mod)
discover_speakers = _s2t_mod.discover_speakers
run_pipeline = _s2t_mod.run_pipeline

# ── 設定 ──
DEFAULT_SPEAKER_REF_DIR = str(_project_root / "test-audio" / "speaker-ref")
DEFAULT_OUTPUT_DIR = str(_project_root / "output")


# ====================================================================
#  Tab 2: Speaker 管理
# ====================================================================


def list_speakers(speaker_ref_dir: str) -> tuple[list[list], str]:
    """列出所有 speaker 檔案."""
    ref_dir = Path(speaker_ref_dir)
    if not ref_dir.is_dir():
        return [["⚠ 資料夾不存在", "0", "-", "-"]], f"資料夾不存在：{ref_dir}"

    audio_exts = {".wav", ".mp3", ".flac", ".ogg"}
    rows = []
    for f in sorted(ref_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in audio_exts:
            size_kb = round(f.stat().st_size / 1024, 1)
            rows.append([f.stem, f.name, size_kb, f.as_posix()])

    info = f"共 {len(rows)} 位 speaker（資料夾：{ref_dir}）"
    return rows, info


def upload_speaker(speaker_ref_dir: str, files) -> tuple[list[list], str]:
    """上傳 speaker 參考音訊檔案."""
    if not files:
        return list_speakers(speaker_ref_dir)

    ref_dir = Path(speaker_ref_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)

    file_list = [files] if isinstance(files, str) else list(files)

    uploaded = []
    skipped = []
    for fpath in file_list:
        if not fpath or not Path(fpath).is_file():
            continue
        stem = Path(fpath).stem
        ext = Path(fpath).suffix

        dest = ref_dir / f"{stem}{ext}"
        if dest.exists():
            i = 1
            while (ref_dir / f"{stem}_{i}{ext}").exists():
                i += 1
            dest = ref_dir / f"{stem}_{i}{ext}"

        shutil.copy2(fpath, dest)
        uploaded.append(dest.name)

    rows, info = list_speakers(speaker_ref_dir)
    msg = (
        f"✅ 已上傳 {len(uploaded)} 個檔案：{', '.join(uploaded)}"
        if uploaded
        else "⚠ 沒有檔案可上傳"
    )
    if skipped:
        msg += f"\n⚠ 跳過（已存在）：{', '.join(skipped)}"
    return rows, msg


def delete_speaker(speaker_ref_dir: str, speaker_name: str) -> tuple[list[list], str]:
    """刪除 speaker 參考音訊檔案."""
    if not speaker_name:
        return list_speakers(speaker_ref_dir)

    ref_dir = Path(speaker_ref_dir)
    audio_exts = {".wav", ".mp3", ".flac", ".ogg"}
    deleted = []

    for f in sorted(ref_dir.iterdir()):
        if f.is_file() and f.stem == speaker_name and f.suffix.lower() in audio_exts:
            try:
                f.unlink()
                deleted.append(f.name)
            except Exception as e:
                return list_speakers(speaker_ref_dir), f"❌ 刪除失敗：{e}"

    rows, info = list_speakers(speaker_ref_dir)
    msg = (
        f"✅ 已刪除 {len(deleted)} 個檔案：{', '.join(deleted)}"
        if deleted
        else f"⚠ 找不到 speaker「{speaker_name}」的檔案"
    )
    return rows, msg


def rename_speaker(
    speaker_ref_dir: str, old_name: str, new_name: str
) -> tuple[list[list], str]:
    """改名 speaker 參考音訊檔案."""
    if not old_name or not new_name:
        return list_speakers(speaker_ref_dir)

    ref_dir = Path(speaker_ref_dir)
    audio_exts = {".wav", ".mp3", ".flac", ".ogg"}
    renamed = []

    for f in sorted(ref_dir.iterdir()):
        if f.is_file() and f.stem == old_name and f.suffix.lower() in audio_exts:
            new_file = ref_dir / f"{new_name}{f.suffix}"
            if new_file.exists():
                return list_speakers(
                    speaker_ref_dir
                ), f"❌ 目標名稱已存在：{new_file.name}"
            try:
                f.rename(new_file)
                renamed.append(f"{f.name} → {new_file.name}")
            except Exception as e:
                return list_speakers(speaker_ref_dir), f"❌ 改名失敗：{e}"

    rows, info = list_speakers(speaker_ref_dir)
    msg = (
        f"✅ 已改名 {len(renamed)} 個檔案"
        if renamed
        else f"⚠ 找不到 speaker「{old_name}」的檔案"
    )
    return rows, msg


# ====================================================================
#  UI 組件
# ====================================================================


def make_ui():
    """建立 Gradio UI."""
    with gr.Blocks(title="Speech-to-Text") as ui:
        gr.Markdown(
            """
# 🎙️ Speech-to-Text Web UI

Speaker 辨識 + 語音轉文字整合介面

> 整合 VoiceTag (Diarization) + Breeze-ASR-26 (STT)
            """
        )

        with gr.Tabs():
            # ──── Tab 1: 轉錄 ────
            with gr.Tab("轉錄"):
                audio_input = gr.File(
                    label="上傳音訊檔案",
                    file_types=["audio/"],
                    type="filepath",
                )

                run_btn = gr.Button("🚀 開始處理", variant="primary", size="lg")

                with gr.Row():
                    with gr.Column(scale=4):
                        log_output = gr.Textbox(
                            label="處理歷程",
                            lines=15,
                            max_lines=30,
                            interactive=False,
                        )
                    with gr.Column(scale=1):
                        download_btn = gr.DownloadButton(
                            label="下載 JSON 結果",
                            interactive=False,
                            visible=True,
                        )

            # ──── Tab 2: Speaker 管理 ────
            with gr.Tab("Speaker 管理"):
                gr.Markdown(
                    """
管理 speaker 參考音訊檔案。檔案名稱即為 speaker 名稱，副檔名支援 `.wav`, `.mp3`, `.flac`, `.ogg`。

> 💡 **提醒：**乾淨音色參考建議 3~5 秒（5 秒以上更佳）
                    """
                )

                with gr.Row():
                    speaker_ref_dir_input = gr.Textbox(
                        label="Speaker 參考資料夾路徑",
                        value=DEFAULT_SPEAKER_REF_DIR,
                    )
                    refresh_btn = gr.Button("🔄 重新整理")

                speaker_table = gr.Dataframe(
                    label="Speaker 檔案列表",
                    headers=["Speaker 名稱", "檔案名稱", "大小 (KB)", "完整路徑"],
                    interactive=False,
                )
                speaker_info = gr.Markdown()

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### 📤 上傳檔案")
                        upload_input = gr.File(
                            label="選擇音訊檔案",
                            file_types=["audio/"],
                            type="filepath",
                            file_count="multiple",
                        )
                        upload_btn = gr.Button(
                            "上傳到 Speaker 資料夾", variant="primary"
                        )
                    with gr.Column():
                        gr.Markdown("### ✏️ 改名")
                        rename_old = gr.Textbox(label="原名稱", placeholder="例如：黃")
                        rename_new = gr.Textbox(
                            label="新名稱", placeholder="例如：黃醫師"
                        )
                        rename_btn = gr.Button("改名", variant="secondary")
                    with gr.Column():
                        gr.Markdown("### 🗑️ 刪除")
                        delete_name = gr.Textbox(
                            label="Speaker 名稱", placeholder="例如：黃"
                        )
                        delete_btn = gr.Button("刪除", variant="stop")

                action_output = gr.Markdown()

        # ── 事件綁定 ──

        # Tab 1: 轉錄
        def on_run(audio_path):
            """處理按鈕點擊 — 觸發 pipeline 並回傳 UI 更新."""
            if not audio_path or not Path(audio_path).exists():
                yield "❌ 請先上傳音訊檔案", None
                return

            output_dir = Path(DEFAULT_OUTPUT_DIR)
            audio_name = Path(audio_path).stem
            output_json = str(output_dir / f"{audio_name}_stt.json")

            if Path(output_json).exists():
                Path(output_json).unlink()

            log_buf: list[str] = []
            done_event = threading.Event()

            def run_in_thread():
                try:
                    import builtins

                    old_print = builtins.print

                    def capture(*args, **kwargs):
                        msg = " ".join(str(a) for a in args) if args else ""
                        log_buf.append(msg)
                        if msg:
                            old_print(msg, **kwargs)

                    builtins.print = capture

                    result = run_pipeline(
                        input_audio=audio_path,
                        speaker_ref_dir=DEFAULT_SPEAKER_REF_DIR,
                        output_json=output_json,
                    )

                    log_buf.append(f"\n✅ 處理完成！輸出檔案：{output_json}")
                    log_buf.append(f"   Segments: {len(result.get('segments', []))}")
                    log_buf.append(f"   Speakers: {result.get('num_speakers', '?')}")
                except Exception as e:
                    log_buf.append(f"\n❌ 處理失敗：{e}")
                    import traceback

                    log_buf.append(traceback.format_exc())
                finally:
                    done_event.set()

            t = threading.Thread(target=run_in_thread, daemon=True)
            t.start()

            while not done_event.is_set():
                current_log = "\n".join(log_buf)
                yield current_log or "⏳ 正在初始化...", output_json
                import time

                time.sleep(0.5)

            final_log = "\n".join(log_buf)
            yield final_log, output_json

        run_btn.click(
            fn=on_run,
            inputs=[audio_input],
            outputs=[log_output, download_btn],
            show_progress=True,
        )

        # 偵聽 log 輸出中的成功訊息，自動啟用下載按鈕
        def check_download(log_text):
            if log_text and "✅ 處理完成" in log_text:
                for line in log_text.split("\n"):
                    if "輸出檔案：" in line:
                        path = line.split("輸出檔案：")[-1].strip()
                        if Path(path).exists():
                            return gr.update(value=path, interactive=True)
            return gr.update(interactive=False)

        log_output.change(
            fn=check_download,
            inputs=[log_output],
            outputs=[download_btn],
        )

        # Tab 2: Speaker 管理
        def on_refresh(dir_path):
            rows, info = list_speakers(dir_path)
            return rows, info, gr.update()

        def on_upload(dir_path, files):
            rows, msg = upload_speaker(dir_path, files)
            return rows, msg, gr.update()

        def on_delete(dir_path, name):
            rows, msg = delete_speaker(dir_path, name)
            return rows, msg

        def on_rename(dir_path, old, new):
            rows, msg = rename_speaker(dir_path, old, new)
            return rows, msg

        refresh_btn.click(
            fn=on_refresh,
            inputs=[speaker_ref_dir_input],
            outputs=[speaker_table, speaker_info, action_output],
        )

        upload_btn.click(
            fn=on_upload,
            inputs=[speaker_ref_dir_input, upload_input],
            outputs=[speaker_table, action_output, speaker_info],
        )

        delete_btn.click(
            fn=on_delete,
            inputs=[speaker_ref_dir_input, delete_name],
            outputs=[speaker_table, action_output],
        )

        rename_btn.click(
            fn=on_rename,
            inputs=[speaker_ref_dir_input, rename_old, rename_new],
            outputs=[speaker_table, action_output],
        )

        # 初始載入 speaker 列表
        ui.load(
            fn=on_refresh,
            inputs=[speaker_ref_dir_input],
            outputs=[speaker_table, speaker_info, action_output],
        )

    return ui


# ====================================================================
#  Entry Point
# ====================================================================


def main():
    ui = make_ui()
    ui.launch(
        server_name="0.0.0.0",
        server_port=7861,
        share=False,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
