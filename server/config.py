import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi.templating import Jinja2Templates

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"

# Initial environment load
load_dotenv(ENV_FILE, override=True)


def get_admin_username() -> str:
    """Read current admin username directly from .env."""
    load_dotenv(ENV_FILE, override=True)
    return (os.getenv("ADMIN_USERNAME") or "admin").strip()


def get_admin_password() -> str:
    """Read current admin password directly from .env."""
    load_dotenv(ENV_FILE, override=True)
    return (os.getenv("ADMIN_PASSWORD") or "tinypos_secret_2026").strip()


ADMIN_USERNAME = get_admin_username()
ADMIN_PASSWORD = get_admin_password()
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", 8100))

DB_PATH = BASE_DIR / "tinypos.db"
TEMPLATES_DIR = BASE_DIR / "UI"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
