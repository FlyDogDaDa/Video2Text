"""Entry point — starts uvicorn server with pre-loaded model."""

import sys
from pathlib import Path

# Add project root to path so we can import ``voicetag_core``
_project_root = Path(__file__).resolve().parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

# Add server's api package to path
_server_dir = Path(__file__).resolve().parent
if str(_server_dir) not in sys.path:
    sys.path.insert(0, str(_server_dir))

import uvicorn


def main():
    uvicorn.run(
        "api.main:app", host="0.0.0.0", port=8001, reload=False, log_level="info"
    )


if __name__ == "__main__":
    main()
