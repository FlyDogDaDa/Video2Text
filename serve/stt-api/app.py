"""STT 長音訊轉錄 API 服務（GB10）。

把 09-16~09-20 驗證過的超長音訊管線包成 HTTP API：
上傳會議音訊（不限長度） → 迭代切分轉錄（MOSS-Transcribe-Diarize @ vLLM）
→ τ 平臺期掃描（自適應語者合併門檻） → speaker_unify_v31 全域語者統一
→ 回傳 JSON 逐字稿。

設計重點：
- 一次性檔案不長存：每個 job 用獨立工作目錄，完成後立即刪除，
  僅把結果 JSON 留在記憶體（TTL 內可重複讀取）。
- 單一 worker 依序處理（GPU 的 ASR 是瓶頸），上傳即回 202 可輪詢。
- 管線指令碼逐 job 複製（指令碼以自身位置推導工作目錄），服務本身無狀態。

環境變數：
- STT_ASR_URL      MOSS TD ASR endpoint（預設 http://127.0.0.1:8750/v1/audio/transcriptions）
- STT_PORT         本服務 port（預設 8760）
- STT_JOBS_DIR     工作目錄根（預設 ./jobs）
- STT_RESULT_TTL_H 結果保留時數（預設 24）
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid
import wave
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from opencc import OpenCC

# ── 設定 ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
JOBS_DIR = Path(os.environ.get("STT_JOBS_DIR", str(BASE_DIR / "jobs")))
PIPELINE_SCRIPTS = BASE_DIR / "pipeline_scripts"
MODEL_ONNX = Path(
    os.environ.get(
        "STT_MODEL_ONNX",
        str(BASE_DIR / "models" / "speech_campplus_sv_zh_en_16k-common_advanced.onnx"),
    )
)
ASR_URL = os.environ.get("STT_ASR_URL", "http://127.0.0.1:8750/v1/audio/transcriptions")
ASR_ROOT = ASR_URL.split("/v1/")[0]
RESULT_TTL_H = float(os.environ.get("STT_RESULT_TTL_H", "24"))
TZ = timezone(timedelta(hours=8))

CC_S2TWP = OpenCC("s2twp")
PIPELINE_VERSION = (
    "pipeline 2026-09-16/20（transcribe_iterative + tau_sweep + speaker_unify_v3.1）"
)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    JOBS_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker_loop, daemon=True, name="stt-worker").start()
    threading.Thread(target=sweeper_loop, daemon=True, name="stt-sweeper").start()
    log(f"服務啟動：ASR={ASR_URL}，jobs={JOBS_DIR}")
    yield


app = FastAPI(
    title="STT Long-Audio Transcription API", version="0.1.0", lifespan=lifespan
)


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ── Job 狀態 ────────────────────────────────────────────────────────────
@dataclass
class Job:
    job_id: str
    source_name: str
    source_suffix: str
    traditional: bool = True
    tau: Optional[float] = None  # 使用者指定則跳過掃描
    status: str = "queued"  # queued / processing / done / error
    stage: str = ""
    detail: str = ""
    error: str = ""
    audio_duration_s: Optional[float] = None
    tau_used: Optional[float] = None
    tau_auto: Optional[float] = None
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    result: Optional[dict] = None
    submitted_at: str = ""
    started_at: str = ""
    finished_at: Optional[str] = None
    workspace: Optional[Path] = None
    progress_frozen: dict[str, Any] = field(default_factory=dict)


JOBS: dict[str, Job] = {}
QUEUE: "queue.Queue[Job]" = queue.Queue()
JOBS_LOCK = threading.Lock()


def put_job(job: Job) -> None:
    with JOBS_LOCK:
        JOBS[job.job_id] = job


def get_job(job_id: str) -> Job:
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job 不存在：{job_id}")
    return job


# ── 小工具 ──────────────────────────────────────────────────────────────
def log_tail(path: Path, n: int = 40) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-n:])
    except OSError:
        return ""


def run_cmd(cmd: list[str], cwd: Path, log_path: Path, env: dict[str, str]) -> None:
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, stdout=fh, stderr=subprocess.STDOUT
        )
    if proc.returncode != 0:
        raise RuntimeError(
            f"指令失敗（rc={proc.returncode}）：{' '.join(cmd[1:2])}\n{log_tail(log_path)}"
        )


def ffmpeg_convert(src: Path, dst: Path, ws: Path) -> None:
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(dst),
    ]
    log_path = ws / "ffmpeg.log"
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(f"ffmpeg 轉檔失敗：{log_tail(log_path, 15)}")


def read_duration(full: Path) -> float:
    with wave.open(str(full), "rb") as w:
        assert (
            w.getnchannels() == 1
            and w.getsampwidth() == 2
            and w.getframerate() == 16000
        ), "audio_full.wav 應為 16k/s16le/mono"
        return w.getnframes() / w.getframerate()


def cleanup_workspace(job: Job) -> None:
    if job.workspace and job.workspace.exists():
        shutil.rmtree(job.workspace, ignore_errors=True)
    job.workspace = None


def fail_job(job: Job, exc: Exception) -> None:
    job.status = "error"
    job.error = str(exc)
    job.finished_at = now_iso()
    cleanup_workspace(job)
    log(f"[{job.job_id}] 失敗：{exc}")


def compute_progress(job: Job) -> dict[str, Any]:
    """從工作目錄的 audio_parts.json 估算進度（ASR 階段才有意義）。"""
    if job.workspace is None:
        return job.progress_frozen
    meta_path = job.workspace / "audio_parts.json"
    if not meta_path.exists():
        return {"stage": job.stage}
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"stage": job.stage}
    parts = meta.get("parts", [])
    total = meta.get("total_duration_s") or 0
    cut = max((float(p.get("end_cut_abs_s", 0)) for p in parts), default=0.0)
    info: dict[str, Any] = {
        "stage": job.stage,
        "parts_done": len(parts),
        "processed_s": round(cut, 1),
        "total_s": round(total, 1),
    }
    if total > 0:
        info["fraction"] = round(min(cut / total, 1.0), 3)
    return info


# ── 結果組裝 ────────────────────────────────────────────────────────────
def build_result(
    job: Job,
    combined: dict,
    tau_used: Optional[float],
    tau_auto: Optional[float],
    timings: dict[str, float],
) -> dict:
    segments = []
    for s in combined["segments"]:
        text = s["text"]
        if job.traditional:
            text = CC_S2TWP.convert(text)
        segments.append(
            {
                "start": round(s["start"], 3),
                "end": round(s["end"], 3),
                "duration": round(s["end"] - s["start"], 3),
                "speaker": s.get("speaker_global") or s.get("speaker", "UNKNOWN"),
                "text": text,
            }
        )
    speakers = sorted({seg["speaker"] for seg in segments})
    return {
        "job_id": job.job_id,
        "status": "done",
        "source_name": job.source_name,
        "audio_duration_s": job.audio_duration_s,
        "n_segments": len(segments),
        "n_speakers": len(speakers),
        "speakers": speakers,
        "tau_used": tau_used,
        "tau_auto": tau_auto,
        "traditional_applied": job.traditional,
        "warnings": job.warnings,
        "processing": {
            "submitted_at": job.submitted_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            **{k: round(v, 1) for k, v in timings.items()},
        },
        "pipeline": {
            "asr_url": ASR_URL,
            "speaker_backend": "campplus",
            "embedding_model": MODEL_ONNX.name,
            "version": PIPELINE_VERSION,
        },
        "segments": segments,
    }


def collect_warnings(ws: Path) -> list[str]:
    """從 audio_parts.json 收集管線自記的異常（盲切、空輸出前進等）。"""
    warnings: list[str] = []
    try:
        meta = json.loads((ws / "audio_parts.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return warnings
    parts = meta.get("parts", [])
    n_blind = sum(1 for p in parts if p.get("status") == "fallback-blind-cut")
    n_empty = sum(1 for p in parts if p.get("status") == "empty-advance")
    if n_blind:
        warnings.append(
            f"{n_blind} 個分段回掃無候選句，採 fallback 盲切（句子可能腰斬）"
        )
    if n_empty:
        warnings.append(f"{n_empty} 個分段無轉錄輸出（長沉默或純音樂），直接前進")
    return warnings


# ── Worker ──────────────────────────────────────────────────────────────
def process(job: Job) -> None:
    t0 = time.monotonic()
    job.status = "processing"
    job.started_at = now_iso()
    ws = JOBS_DIR / job.job_id
    job.workspace = ws
    ws.mkdir(parents=True, exist_ok=True)

    full = ws / "audio_full.wav"
    job.stage = "convert"
    ffmpeg_convert(ws / f"upload{job.source_suffix}", full, ws)
    job.audio_duration_s = round(read_duration(full), 3)
    log(f"[{job.job_id}] 音訊 {job.audio_duration_s}s（{job.source_name}）")

    # 逐 job 複製管線指令碼（指令碼以自身位置推導工作目錄）
    js = ws / "scripts"
    js.mkdir(exist_ok=True)
    for name in ("transcribe_iterative.py", "tau_sweep.py", "speaker_unify_v31.py"):
        shutil.copy2(PIPELINE_SCRIPTS / name, js / name)

    env = dict(os.environ)
    env.update(
        EK7_ASR_URL=ASR_URL,
        EK7_VIDEO_ID=job.job_id,
        EK7_SOURCE=job.source_name,
        PYTHONUNBUFFERED="1",
    )

    job.stage = "transcribe"
    t1 = time.monotonic()
    run_cmd(
        [sys.executable, str(js / "transcribe_iterative.py")],
        ws,
        ws / "transcribe.log",
        env,
    )
    timings = {"transcribe_s": time.monotonic() - t1}
    job.warnings = collect_warnings(ws)

    combined = json.loads((ws / "transcript_combined.json").read_text(encoding="utf-8"))
    if not combined["segments"]:
        timings["total_s"] = time.monotonic() - t0
        job.finished_at = now_iso()
        job.tau_used = job.tau_auto = None
        job.result = build_result(job, combined, None, None, timings)
        job.status, job.stage = "done", "done"
        job.finished_at = now_iso()
        job.progress_frozen = {"stage": "done", "note": "音訊中未偵測到語音"}
        cleanup_workspace(job)
        log(f"[{job.job_id}] 完成（無語音內容）")
        return

    # τ 決定：使用者指定 > 平臺期掃描 > speaker_unify_v31 預設值
    tau_cmd: list[str] = []
    if job.tau is not None:
        job.tau_used = job.tau
        tau_cmd = ["--tau", str(job.tau)]
        log(f"[{job.job_id}] 使用指定 τ={job.tau}")
    else:
        job.stage = "tau_sweep"
        t2 = time.monotonic()
        run_cmd(
            [
                sys.executable,
                str(js / "tau_sweep.py"),
                str(ws),
                "--model",
                str(MODEL_ONNX),
            ],
            ws,
            ws / "tau_sweep.log",
            env,
        )
        timings["tau_sweep_s"] = time.monotonic() - t2
        sweep = json.loads((ws / "tau_sweep_report.json").read_text(encoding="utf-8"))
        job.tau_auto = sweep.get("auto_tau")
        if job.tau_auto is not None:
            job.tau_used = job.tau_auto
            tau_cmd = ["--tau", str(job.tau_auto)]
            log(f"[{job.job_id}] auto_tau={job.tau_auto}")
        else:
            log(f"[{job.job_id}] 無穩定平臺期 → 用 speaker_unify_v31 預設 τ")

    job.stage = "speaker_unify"
    t3 = time.monotonic()
    run_cmd(
        [
            sys.executable,
            str(js / "speaker_unify_v31.py"),
            str(ws),
            "--model",
            str(MODEL_ONNX),
            *tau_cmd,
        ],
        ws,
        ws / "unify.log",
        env,
    )
    timings["speaker_unify_s"] = time.monotonic() - t3

    combined = json.loads((ws / "transcript_combined.json").read_text(encoding="utf-8"))
    job.stage = "build_result"
    timings["total_s"] = time.monotonic() - t0
    job.finished_at = now_iso()
    job.result = build_result(job, combined, job.tau_used, job.tau_auto, timings)
    job.status, job.stage = "done", "done"
    job.progress_frozen = {"stage": "done"}
    cleanup_workspace(job)
    log(
        f"[{job.job_id}] 完成：{len(job.result['segments'])} segments／"
        f"{job.result['n_speakers']} 語者／τ={job.tau_used}／耗時 {timings['total_s']:.0f}s"
    )


def worker_loop() -> None:
    while True:
        job = QUEUE.get()
        try:
            process(job)
        except Exception as exc:  # noqa: BLE001
            fail_job(job, exc)


def sweeper_loop() -> None:
    """定期清掉超過 TTL 的已完成結果（記憶體）與殘留工作目錄。"""
    while True:
        time.sleep(600)
        deadline = datetime.now(TZ) - timedelta(hours=RESULT_TTL_H)
        stale: list[str] = []
        with JOBS_LOCK:
            for jid, job in JOBS.items():
                if job.status in ("done", "error") and job.finished_at:
                    try:
                        if datetime.fromisoformat(job.finished_at) < deadline:
                            stale.append(jid)
                    except ValueError:
                        pass
        for jid in stale:
            with JOBS_LOCK:
                job = JOBS.pop(jid, None)
            if job:
                cleanup_workspace(job)
                log(f"[{jid}] TTL 到期，已移除")


# ── 啟動 ─────────────────────────────────────────────────────────────
# worker 與 sweeper 執行緒在 lifespan（見檔案上方）啟動。


# ── API ─────────────────────────────────────────────────────────────────
@app.get("/")
def index() -> dict:
    return {
        "service": "STT Long-Audio Transcription API",
        "version": "0.1.0",
        "endpoints": {
            "POST /transcribe": "上傳音訊建立轉錄任務（multipart：file、traditional、tau）",
            "GET /jobs": "列出所有任務",
            "GET /jobs/{job_id}": "查詢任務狀態與進度",
            "GET /jobs/{job_id}/result": "取得轉錄結果 JSON（done 後可用）",
            "DELETE /jobs/{job_id}": "刪除任務與結果",
            "GET /health": "服務與 ASR 後端健康檢查",
        },
        "docs": "/docs",
    }


@app.post("/transcribe", status_code=202)
async def transcribe(
    file: UploadFile = File(...),
    traditional: bool = Form(True),
    tau: Optional[float] = Form(None),
) -> dict:
    job_id = uuid.uuid4().hex[:12]
    suffix = re.sub(r"[^a-z0-9.]", "", (Path(file.filename or "audio").suffix.lower()))[
        :10
    ]
    if not suffix.startswith("."):
        suffix = ".audio"
    job = Job(
        job_id=job_id,
        source_name=file.filename or "audio",
        source_suffix=suffix,
        traditional=traditional,
        tau=tau,
        submitted_at=now_iso(),
    )

    ws = JOBS_DIR / job_id
    ws.mkdir(parents=True, exist_ok=True)
    job.workspace = ws
    up = ws / f"upload{suffix}"
    try:
        with up.open("wb") as f:
            while chunk := await file.read(1 << 20):
                f.write(chunk)
    except OSError as exc:
        shutil.rmtree(ws, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"上傳檔案寫入失敗：{exc}") from exc

    put_job(job)
    QUEUE.put(job)
    log(
        f"[{job_id}] 收到上傳：{job.source_name}（traditional={traditional}, tau={tau}）"
    )
    return {
        "job_id": job_id,
        "status": "queued",
        "poll_url": f"/jobs/{job_id}",
        "result_url": f"/jobs/{job_id}/result",
    }


@app.get("/jobs")
def list_jobs() -> list[dict]:
    with JOBS_LOCK:
        return [
            {
                "job_id": j.job_id,
                "source_name": j.source_name,
                "status": j.status,
                "stage": j.stage,
                "submitted_at": j.submitted_at,
            }
            for j in JOBS.values()
        ]


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = get_job(job_id)
    info: dict[str, Any] = {
        "job_id": job.job_id,
        "source_name": job.source_name,
        "status": job.status,
        "stage": job.stage,
        "submitted_at": job.submitted_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "audio_duration_s": job.audio_duration_s,
        "tau_used": job.tau_used,
        "result_url": f"/jobs/{job_id}/result",
    }
    if job.status == "processing":
        info["progress"] = compute_progress(job)
    if job.warnings:
        info["warnings"] = job.warnings
    if job.error:
        info["error"] = job.error
    return info


@app.get("/jobs/{job_id}/result")
def job_result(job_id: str) -> dict:
    job = get_job(job_id)
    if job.status == "error":
        raise HTTPException(status_code=500, detail=f"任務失敗：{job.error}")
    if job.status != "done" or job.result is None:
        raise HTTPException(
            status_code=409, detail=f"任務尚未完成（status={job.status}）"
        )
    return job.result


@app.delete("/jobs/{job_id}")
def job_delete(job_id: str) -> dict:
    get_job(job_id)
    with JOBS_LOCK:
        job = JOBS.pop(job_id)
    cleanup_workspace(job)
    return {"job_id": job_id, "deleted": True}


@app.get("/health")
def health() -> dict:
    asr: dict[str, Any] = {"url": ASR_URL, "ready": False}
    try:
        r = httpx.get(f"{ASR_ROOT}/v1/models", timeout=3.0)
        if r.status_code == 200:
            data = r.json().get("data", [])
            asr["ready"] = bool(data)
            asr["model"] = data[0]["id"] if data else None
    except Exception as exc:  # noqa: BLE001
        asr["error"] = str(exc)
    with JOBS_LOCK:
        counts: dict[str, int] = {}
        for j in JOBS.values():
            counts[j.status] = counts.get(j.status, 0) + 1
    return {
        "service": "stt-api",
        "status": "ok",
        "asr": asr,
        "jobs": counts,
        "pipeline_scripts": sorted(p.name for p in PIPELINE_SCRIPTS.glob("*.py")),
        "model_onnx": MODEL_ONNX.exists(),
    }


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("STT_PORT", "8760")))


if __name__ == "__main__":
    main()
