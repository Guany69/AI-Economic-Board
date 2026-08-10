"""Artifact store: large model/data files stay on disk; only metadata
(path, sha256, size) is persisted in PostgreSQL (HLD invariant 10)."""

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ArtifactInfo:
    name: str
    path: Path
    sha256: str
    size_bytes: int


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def describe(path: Path, name: str | None = None) -> ArtifactInfo:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Artifact file not found: {path}")
    return ArtifactInfo(
        name=name or path.name,
        path=path.resolve(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def archive(src: Path, dest_dir: Path, name: str | None = None) -> ArtifactInfo:
    """Copy an artifact into a permanent location and describe the copy."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / (name or Path(src).name)
    shutil.copy2(src, dest)
    return describe(dest, name)
