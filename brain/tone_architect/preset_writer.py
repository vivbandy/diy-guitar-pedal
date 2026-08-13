"""Atomic preset writing.

The plugin may be watching the preset file. A half-written JSON file would be observed as a
corrupt patch, so writes go to a temp file in the same directory and are then renamed —
os.replace is atomic within a filesystem.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .models import Patch


def write_patch(patch: Patch | dict, path: str | Path) -> Path:
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)

    data = patch.model_dump(mode="json", exclude_none=True) if isinstance(patch, Patch) else patch
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"

    fd, tmp = tempfile.mkstemp(dir=str(out.parent), prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, out)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return out
