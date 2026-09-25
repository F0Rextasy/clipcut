"""Cut clips with ffmpeg: fast seek + crop-to-aspect + x264/aac."""
from __future__ import annotations

import os
import re
import subprocess

_ASPECT_RE = re.compile(r"^(\d+):(\d+)$")


def parse_aspect(spec: str) -> tuple[int, int]:
    m = _ASPECT_RE.match(spec.strip())
    if not m or int(m.group(2)) == 0:
        raise ValueError(f"bad --aspect {spec!r}, want W:H like 9:16")
    return int(m.group(1)), int(m.group(2))


def _even(x: float) -> int:
    return max(2, int(x) // 2 * 2)


def crop_filter(w: int, h: int, spec: str) -> str:
    """Crop the wide side to the target ratio, then scale (max side 1920).

    Landscape input + 9:16 target -> center crop ih*9/16:ih.
    Portrait input (landscape-crop guard) -> crop the wide side instead,
    so an already-vertical video stays vertical.
    """
    a, b = parse_aspect(spec)
    r = a / b
    if abs(w / h - r) < 0.02:
        cw, ch = _even(w), _even(h)
    elif w / h > r:  # too wide: crop width
        ch, cw = _even(h), _even(h * r)
    else:  # too tall: crop height
        cw, ch = _even(w), _even(w / r)
    if r >= 1.0:
        sw, sh = 1920, _even(1920 / r)
    else:
        sh, sw = 1920, _even(1920 * r)
    return f"crop={cw}:{ch},scale={sw}:{sh}"


def cut_clip(ffmpeg: str, src: str, start: float, dur: float,
             vf: str, dst: str) -> int:
    """Cut one clip; returns file size in bytes."""
    p = subprocess.run(
        [ffmpeg, "-hide_banner", "-y", "-ss", f"{start:.3f}", "-i", src,
         "-t", f"{dur:.3f}", "-vf", vf, "-c:v", "libx264",
         "-preset", "veryfast", "-crf", "23", "-c:a", "aac",
         "-movflags", "+faststart", dst],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise RuntimeError(f"ffmpeg cut failed: {p.stderr.strip()[-300:]}")
    return os.path.getsize(dst)
