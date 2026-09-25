"""Locate ffmpeg/ffprobe binaries.

Resolution order: $FFMPEG_BIN / $FFPROBE_BIN override, then PATH,
then the well-known Windows WinGet install location
(%LocalAppData%\\Microsoft\\WinGet\\Packages\\Gyan.FFmpeg_*).
Returns None when not found (caller maps that to exit 69).
"""
from __future__ import annotations

import glob
import os
import shutil


def find_bin(name: str) -> str | None:
    override = os.environ.get(name.upper() + "_BIN")
    if override:
        return override if os.path.isfile(override) else None
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        base = os.path.expandvars(
            r"%LocalAppData%\Microsoft\WinGet\Packages"
        )
        hits = glob.glob(
            os.path.join(
                base, "Gyan.FFmpeg_*", "ffmpeg-*-full_build", "bin", name + ".exe"
            )
        )
        if hits:
            return hits[0]
    return None
