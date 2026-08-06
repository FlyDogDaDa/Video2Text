"""Load .env into environment variables."""

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass
