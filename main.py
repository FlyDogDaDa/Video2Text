"""Video2Text — structured video understanding powered by SGLang."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).parent / ".env")


def main():
    print("Hello from video2text!")


if __name__ == "__main__":
    main()
