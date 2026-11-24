"""Submission bundles, the client's side: packing a submission folder, and the static checks the
service applies before it queues anything.

A bundle is a gzipped tar of the submission folder, with regular files only. The service unpacks
it safely (service/bundle.py) and refuses one over the limits below.
"""

from __future__ import annotations

import io
import os
import re
import tarfile
from pathlib import Path, PurePosixPath

from harness.manifest import REQUIRED_FILES, Manifest
from harness.manifest import load as load_manifest

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
MAX_BUNDLE_BYTES = 20 * 2**20  # the upload, compressed
MAX_UNPACKED_BYTES = 50 * 2**20
MAX_FILES = 200
SKIP = {"__pycache__", ".git", ".ipynb_checkpoints"}  # left out of every bundle
SECRET_NAME = re.compile(r"(KEY|TOKEN|SECRET)$", re.IGNORECASE)  # environment variables that hold one
SHORTEST_SECRET = 16  # shorter values are placeholders, not keys
LOOKS_LIKE_KEY = re.compile(rb"\b(sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{35})")


def static_check(folder: Path, team: str | None, targets) -> tuple[Manifest | None, list[str]]:
    """The manifest, or None and the problems: what the service refuses before queueing anything.
    team is the token's team (None: not checked); targets are the tracks open at the event."""
    manifest, problems = load_manifest(folder)
    problems += [f"{name} is missing" for name in REQUIRED_FILES if not (folder / name).is_file()]
    if manifest is None:
        return None, problems
    if team is not None and manifest.team != team:
        problems.append(f"manifest.yaml says team {manifest.team!r}, but this token is {team!r}'s")
    if not NAME.match(manifest.name):
        problems.append("manifest.yaml: name must be 1-64 letters, digits, '.', '_' or '-'")
    if manifest.target not in targets:
        problems.append(f"target {manifest.target!r} is not open at this event (open: {sorted(targets)})")
    return (None, problems) if problems else (manifest, [])


def files(folder: Path) -> list[Path]:
    """The files a bundle of the folder holds: no links, nothing under SKIP."""
    out = []
    for path in sorted(Path(folder).rglob("*")):
        rel = path.relative_to(folder)
        if SKIP & set(rel.parts) or path.is_symlink() or not path.is_file():
            continue
        out.append(path)
    return out


def pack(folder: Path) -> bytes:
    """A bundle of a submission folder, as `hack submit` sends it."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for path in files(folder):
            rel = path.relative_to(folder)
            tar.add(path, arcname=str(PurePosixPath(Path(folder).name) / rel.as_posix()), recursive=False)
    return buf.getvalue()


def size_problems(folder: Path) -> list[str]:
    """The limits a bundle of the folder would break."""
    listed = files(folder)
    problems = []
    if len(listed) > MAX_FILES:
        problems.append(f"the folder holds {len(listed)} files; a bundle may hold at most {MAX_FILES}")
    unpacked = sum(p.stat().st_size for p in listed)
    if unpacked > MAX_UNPACKED_BYTES:
        problems.append(f"the files add up to {unpacked / 2**20:.1f} MB; at most {MAX_UNPACKED_BYTES // 2**20} MB")
    packed = len(pack(folder))
    if packed > MAX_BUNDLE_BYTES:
        problems.append(f"the bundle is {packed / 2**20:.1f} MB compressed; at most {MAX_BUNDLE_BYTES // 2**20} MB")
    return problems


def secret_problems(folder: Path, environ=None) -> list[str]:
    """The files a bundle of the folder would carry a key or token in: the value of an environment
    variable named like one (SECRET_NAME), or a string shaped like an API key. The messages name the
    variable, never the value."""
    env = os.environ if environ is None else environ
    values = {var: value.strip().encode() for var, value in sorted(env.items())
              if SECRET_NAME.search(var) and len(value.strip()) >= SHORTEST_SECRET}
    problems = []
    for path in files(folder):
        data = path.read_bytes()
        rel = path.relative_to(folder).as_posix()
        found = [f"${var}" for var, value in values.items() if value in data]
        if found:
            problems.append(f"{rel} holds the value of {' and '.join(found)}: keep keys and tokens out of "
                            f"the submission")
        elif LOOKS_LIKE_KEY.search(data):
            problems.append(f"{rel} holds what looks like an API key: keep keys out of the submission")
    return problems
