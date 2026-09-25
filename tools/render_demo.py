"""Render assets/demo.gif + assets/demo.png from REAL clipcut output.

Ensures fixtures/demo.mp4 (scripts/make_demo_video.py), runs the real CLI
(--clips 3 --chapters), shows chapters.txt and ls output, renders cumulative
terminal frames (PIL family recipe).
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
ASSETS = ROOT / "assets"

BG = (13, 17, 23)
FG = (201, 209, 217)
PROMPT = (108, 118, 133)
SUCCESS = (126, 231, 135)
WARN = (227, 179, 65)
ERROR = (255, 123, 114)
KEY = (121, 192, 255)

DURATIONS = [1000, 650, 650, 650, 650, 750, 950]

FONT_CANDIDATES = [
    "C:/Windows/Fonts/consola.ttf",
    "C:/Windows/Fonts/cour.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
]


def find_font():
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("no monospace TTF font found")


def run(args, env=None):
    p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       timeout=300, env={**os.environ, **(env or {})})
    return p.stdout.strip() or p.stderr.strip()


def line_color(ln: str) -> tuple:
    if ln.startswith(("clip ", "1", "2", "3")) and "  " in ln:
        return KEY
    if ln.startswith("clip  start"):
        return PROMPT
    if ln.startswith(("wrote", "00:")):
        return SUCCESS
    return FG


def main():
    from PIL import Image, ImageDraw, ImageFont

    demo = ROOT / "fixtures" / "demo.mp4"
    if not demo.exists():
        run([sys.executable, str(ROOT / "scripts" / "make_demo_video.py")])

    out_dir = ROOT / "out"
    if out_dir.exists():
        shutil.rmtree(out_dir)

    steps = []
    steps.append([("$ python scripts/make_demo_video.py", PROMPT),
                  ("wrote fixtures/demo.mp4 (6.0 MB)", SUCCESS)])
    out = run([sys.executable, "-m", "clipcut.cli", "fixtures/demo.mp4",
               "--clips", "3", "--chapters", "--out", "out"], env={"PYTHONPATH": str(SRC)})
    steps.append([("$ clipcut fixtures/demo.mp4 --clips 3 --chapters --out out", PROMPT)] +
                 [(ln, line_color(ln)) for ln in out.splitlines()])
    ch = (out_dir / "chapters.txt").read_text(encoding="utf-8").splitlines()
    steps.append([("$ cat out/chapters.txt", PROMPT)] +
                 [(ln, SUCCESS) for ln in ch])
    listing = sorted(p.name for p in out_dir.iterdir())
    steps.append([("$ ls out", PROMPT)] +
                 [(n, KEY if n.endswith(".mp4") else FG) for n in listing])

    font = ImageFont.truetype(find_font(), 15)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    max_w, max_lines = 0, 0
    wrapped = []
    for frame in steps:
        wf = []
        for text, col in frame:
            while tmp.textlength(text, font=font) > 760 and len(text) > 40:
                text = text[: len(text) - 10] + "\u2026"
            wf.append((text, col))
            max_w = max(max_w, int(tmp.textlength(text, font=font)))
        wrapped.append(wf)
        max_lines = max(max_lines, len(wf))

    W = max_w + 48
    H = max_lines * 22 + 36
    frames, cum = [], []
    for wf in wrapped:
        cum = cum + wf
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        y = 18
        for text, col in cum:
            d.text((24, y), text, font=font, fill=col)
            y += 22
        frames.append(img)

    durs = list(DURATIONS)
    while len(durs) < len(frames):
        durs.append(700)
    durs = durs[: len(frames)]

    ASSETS.mkdir(parents=True, exist_ok=True)
    gif = ASSETS / "demo.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=durs,
                   loop=0, palette=Image.ADAPTIVE, colors=200, optimize=True)
    frames[0].save(ASSETS / "demo.png")
    print("gif ok", len(frames), "frames", gif.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
