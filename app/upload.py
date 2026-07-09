import re
import uuid
from pathlib import Path

_SANITIZE_RE = re.compile(r"[^a-z0-9.-]+")


def _sanitize_filename(filename: str) -> str:
    """Lowercase, space-to-dash, and strip any char outside [a-z0-9.-] to prevent path traversal."""
    name = filename.lower().replace(" ", "-")
    name = _SANITIZE_RE.sub("", name)
    return name.lstrip(".")


def save_upload(file_bytes: bytes, filename: str, upload_dir: str) -> str:
    """Write file_bytes to upload_dir under a random-prefixed, sanitized name; return the saved path."""
    directory = Path(upload_dir)
    directory.mkdir(parents=True, exist_ok=True)

    safe_name = _sanitize_filename(filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    destination = directory / unique_name

    destination.write_bytes(file_bytes)

    return str(destination.resolve())
