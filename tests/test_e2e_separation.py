#!/usr/bin/env python3
"""End-to-end test: Client → Server → SAM-Audio separation."""

import json
import subprocess
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path("/home/b11223209/workspace/ProgramDevelopment/Video2Text")
SERVER_DIR = PROJECT_ROOT / "serve" / "sam-audio"

# Use short 40s WAV (16kHz mono) to avoid OOM on 16GB GPU
AUDIO_PATH = Path("/tmp/test_short.wav")
ANCHORS = [["+", 5.0, 15.0]]  # 10-second span in the middle

print("=" * 60)
print("SAM-Audio Client-Server Integration Test")
print("=" * 60)

# Step 1: Start server
print("\n[1/5] Starting SAM-Audio server...")
env = {
    **dict(__import__("os").environ),
    "PYTHONPATH": str(PROJECT_ROOT) + ":" + str(SERVER_DIR),
    "VIRTUAL_ENV": str(SERVER_DIR / ".venv"),
}
proc = subprocess.Popen(
    [str(SERVER_DIR / ".venv" / "bin" / "python"), str(SERVER_DIR / "server.py")],
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

print("  Waiting for server startup...")
deadline = time.monotonic() + 20
server_ready = False
while time.monotonic() < deadline:
    try:
        resp = httpx.get("http://localhost:8000/health", timeout=5)
        if resp.status_code == 200:
            health = resp.json()
            print(
                f"  ✅ Server ready - GPU: {health['gpu_available']}, Count: {health['gpu_count']}"
            )
            server_ready = True
            break
    except httpx.RequestError:
        pass
    time.sleep(1)

if not server_ready:
    proc.kill()
    print("  ❌ Server failed to start")
    sys.exit(1)

# Step 2: Check audio file
print("\n[2/5] Checking audio file...")
print(f"  Path: {AUDIO_PATH}")
print(f"  Exists: {AUDIO_PATH.exists()}")
try:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(AUDIO_PATH),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    print(f"  Duration: {result.stdout.strip()} seconds")
except Exception as e:
    print(f"  ⚠️  ffprobe error: {e}")

# Step 3: Test via raw HTTP (bypass client)
print("\n[3/5] Testing /separate endpoint directly...")
separate_payload = {
    "audio_path": str(AUDIO_PATH),
    "anchors": ANCHORS,
    "description": "single speaker",
}
print(f"  Payload: {json.dumps(separate_payload, indent=2)}")

try:
    print("  🔄 Sending request (this may take 1-3 minutes)...")
    resp = httpx.post(
        "http://localhost:8000/separate",
        json=separate_payload,
        timeout=600,  # 10 minutes max
    )
    print(f"  ✅ Response status: {resp.status_code}")
    if resp.status_code == 200:
        body = resp.json()
        print(f"  Speaker output: {body['speaker']}")
        print(f"  Residual output: {body['residual']}")
        print(f"  Status: {body['status']}")

        # Verify files exist
        spk_path = Path(body["speaker"])
        res_path = Path(body["residual"])
        print(
            f"\n  Speaker file exists: {spk_path.exists()} ({spk_path.stat().st_size if spk_path.exists() else 0} bytes)"
        )
        print(
            f"  Residual file exists: {res_path.exists()} ({res_path.stat().st_size if res_path.exists() else 0} bytes)"
        )
    else:
        print(f"  Error response: {resp.text[:500]}")
except httpx.ReadTimeout:
    print("  ❌ Request timed out after 10 minutes")
except Exception as e:
    print(f"  ❌ Request failed: {type(e).__name__}: {e}")

# Step 4: Test via Python client
print("\n[4/5] Testing via Python client...")
sys.path.insert(0, str(PROJECT_ROOT))
from modules.sam_audio import SeparationResult, separate_by_anchor

try:
    anchors = [["+", 5.0, 15.0]]
    print(f"  Calling separate_by_anchor(anchors={anchors})...")
    result = separate_by_anchor(
        AUDIO_PATH,
        anchors,
        "single speaker",
        server_url="http://localhost:8000",
    )
    print(f"  ✅ Client received result:")
    print(f"    Type: {type(result)}")
    print(f"    Speaker: {result.speaker}")
    print(f"    Residual: {result.residual}")
    print(f"    Speaker exists: {result.speaker.exists()}")
    print(f"    Residual exists: {result.residual.exists()}")
except Exception as e:
    print(f"  ❌ Client call failed: {type(e).__name__}: {e}")

# Cleanup
print("\n[5/5] Stopping server...")
proc.terminate()
try:
    proc.wait(timeout=5)
    print("  ✅ Server stopped cleanly")
except subprocess.TimeoutExpired:
    proc.kill()
    proc.wait()
    print("  ⚠️  Server killed forcefully")

print("\n" + "=" * 60)
print("Test complete!")
print("=" * 60)
