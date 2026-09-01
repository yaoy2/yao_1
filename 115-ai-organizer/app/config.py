from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
DATA_DIR = ROOT_DIR / "data"
LOG_DIR = ROOT_DIR / "logs"
DB_PATH = DATA_DIR / "115_index.sqlite"
LOG_PATH = LOG_DIR / "organizer.log"

DEFAULT_ALLOWED_ROOT = "/云下载"
DEFAULT_MOUNT_PATH = "/云下载"
DEFAULT_MAX_FILES = 50
DEFAULT_SCAN_DEPTH = 8


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key:
            values[key] = value
    return values


def load_dotenv(path: Path | None = None) -> None:
    for key, value in parse_env_file(path or ENV_PATH).items():
        if key not in os.environ:
            os.environ[key] = value


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _int(value: str | None, default: int) -> int:
    if value is None or value.strip() == "":
        return default
    return int(value)


def normalize_path(path: str | None) -> str:
    text = (path or "/").replace("\\", "/").strip()
    if not text.startswith("/"):
        text = "/" + text
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) > 1:
        text = text.rstrip("/")
    return text or "/"


@dataclass(frozen=True)
class Settings:
    openlist_base_url: str
    openlist_username: str
    openlist_password: str
    openlist_mount_path: str
    allowed_root: str
    write_mode: bool
    default_max_files: int
    default_scan_depth: int
    default_scan_dir: str
    db_path: Path
    log_path: Path

    @property
    def writes_enabled(self) -> bool:
        return False


def load_settings(env_path: Path | None = None) -> Settings:
    file_values = parse_env_file(env_path) if env_path else {}
    if not env_path:
        load_dotenv()

    def get(key: str, default: str = "") -> str:
        if key in file_values:
            return file_values[key]
        return os.environ.get(key, default)

    mount_path = normalize_path(get("OPENLIST_MOUNT_PATH", DEFAULT_MOUNT_PATH))
    allowed_root = normalize_path(get("ALLOWED_ROOT", DEFAULT_ALLOWED_ROOT))
    scan_dir = normalize_path(get("DEFAULT_SCAN_DIR", allowed_root))
    return Settings(
        openlist_base_url=get("OPENLIST_BASE_URL", "http://127.0.0.1:5244").rstrip("/"),
        openlist_username=get("OPENLIST_USERNAME", "organizer-readonly"),
        openlist_password=get("OPENLIST_PASSWORD", ""),
        openlist_mount_path=mount_path,
        allowed_root=allowed_root,
        write_mode=_bool(get("WRITE_MODE"), False),
        default_max_files=max(1, _int(get("DEFAULT_MAX_FILES"), DEFAULT_MAX_FILES)),
        default_scan_depth=max(0, _int(get("DEFAULT_SCAN_DEPTH"), DEFAULT_SCAN_DEPTH)),
        default_scan_dir=scan_dir,
        db_path=Path(get("DB_PATH", str(DB_PATH))),
        log_path=Path(get("LOG_PATH", str(LOG_PATH))),
    )
