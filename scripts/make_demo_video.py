"""Generate fixtures/demo.mp4: 60s, 640x360, hard scene changes every
~10s with varying volume per segment (real signal for scene+energy logic).

Six 10s segments, alternating hues (testsrc2 hue shift) and sine volume,
concatenated with stream copy so cuts are hard.
Run:  python scripts/make_demo_video.py
"""
from __future__ import annotations

import os
import subprocess
import sys

sys.path.insert(0, "src")
from clipcut.ffmpeg import find_bin

FFMPEG = find_bin("ffmpeg") or "ffmpeg"
SEGS = 6
SEG_LEN = 10
WIDTH, HEIGHT = 640, 360
OUT = "fixtures/demo.mp4"
# volume per segment: alternating loud / quiet
VOLS = [0.5, 0.06, 0.4, 0.08, 0.45, 0.1]


def main() -> None:
    os.makedirs("fixtures", exist_ok=True)
    parts = []
    for i in range(SEGS):
        part = f"fixtures/_seg{i}.mp4"
        parts.append(part)
        hue = f"hue=h={i * 60}"
        f = 440 + i * 110
        subprocess.run(
            [FFMPEG, "-hide_banner", "-y",
             "-f", "lavfi", "-i",
             f"testsrc2=size={WIDTH}x{HEIGHT}:rate=30:duration={SEG_LEN}",
             "-f", "lavfi", "-i", f"sine=frequency={f}:duration={SEG_LEN}:sample_rate=44100",
             "-vf", hue, "-af", f"volume={VOLS[i]}",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
             "-c:a", "aac", "-shortest", part],
            check=True, capture_output=True, text=True,
        )
    lst = os.path.abspath("fixtures/_list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.basename(p)}'\n")
    subprocess.run(
        [FFMPEG, "-hide_banner", "-y", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", OUT],
        check=True, capture_output=True, text=True,
    )
    for p in parts + [lst]:
        os.remove(p)
    size = os.path.getsize(OUT)
    print(f"wrote {OUT} ({size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
