import secrets
import shutil
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings. Override with VERIFYAI_* environment variables or backend/.env."""

    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", env_prefix="VERIFYAI_", extra="ignore")

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'verifyai.db'}"
    storage_dir: Path = BACKEND_DIR / "storage"
    demo_data_dir: Path = BACKEND_DIR / "demo_data"
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"
    secret_key: str = ""
    token_hours: int = 12
    # Pause between pre-scrutiny steps so the progress screen is readable. 0 in tests.
    step_delay: float = 0.6
    # Enables the "load synthetic demo documents" shortcut endpoint.
    demo_mode: bool = True
    tesseract_cmd: str = ""
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()


def secret_key() -> str:
    """Use the configured key, else a random key persisted next to the database."""
    if settings.secret_key:
        return settings.secret_key
    key_file = BACKEND_DIR / "data" / "secret.key"
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if not key_file.exists():
        key_file.write_text(secrets.token_urlsafe(48))
    return key_file.read_text().strip()


def tesseract_cmd() -> str | None:
    if settings.tesseract_cmd:
        return settings.tesseract_cmd
    found = shutil.which("tesseract")
    if found:
        return found
    local = Path.home() / ".local" / "bin" / "tesseract"
    return str(local) if local.exists() else None
