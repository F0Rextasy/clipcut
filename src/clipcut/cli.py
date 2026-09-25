"""clipcut CLI."""
from __future__ import annotations

import argparse
import os
import sys

from clipcut import __version__
from clipcut import chapters as chapters_mod
from clipcut import cut as cut_mod
from clipcut import detect as detect_mod
from clipcut import ffmpeg as ffmpeg_mod

EXIT_USAGE = 65       # missing input / bad args
EXIT_NO_CAPTIONS = 66  # faster-whisper not installed
EXIT_FFMPEG = 69       # ffmpeg/ffprobe unavailable


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="clipcut",
        description=("Long MP4 in, viral clips + chapters + captions out "
                     "— CPU-only, no editor, no GPU."),
    )
    p.add_argument("input", nargs="?", help="input MP4 file")
    p.add_argument("--clips", type=int, default=3,
                   help="number of clips to cut (0 = chapters-only with --chapters)")
    p.add_argument("--min-sec", type=float, default=15)
    p.add_argument("--max-sec", type=float, default=60)
    p.add_argument("--aspect", default="9:16")
    p.add_argument("--chapters", action="store_true")
    p.add_argument("--captions", action="store_true")
    p.add_argument("--out", default="out/")
    p.add_argument("--scene-threshold", type=float, default=0.35)
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def eprint(*a) -> None:
    print(*a, file=sys.stderr)


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.clips < 0 or args.min_sec <= 0 or args.max_sec < args.min_sec:
        eprint("error: bad --clips/--min-sec/--max-sec combination")
        return EXIT_USAGE
    if not args.input or not os.path.isfile(args.input):
        eprint(f"error: input not found: {args.input or '(none)'}")
        return EXIT_USAGE
    ffmpeg = ffmpeg_mod.find_bin("ffmpeg")
    ffprobe = ffmpeg_mod.find_bin("ffprobe")
    if not ffmpeg or not ffprobe:
        eprint("error: ffmpeg/ffprobe not found on PATH "
              "(install: winget install Gyan.FFmpeg / sudo apt-get install -y ffmpeg)")
        return EXIT_FFMPEG
    try:
        cut_mod.parse_aspect(args.aspect)
    except ValueError as e:
        eprint(f"error: {e}")
        return EXIT_USAGE

    chapters_only = args.clips == 0
    if chapters_only and not args.chapters:
        eprint("error: --clips 0 requires --chapters (chapters-only mode)")
        return EXIT_USAGE

    try:
        total = detect_mod.probe_duration(ffprobe, args.input)
        w, h = detect_mod.probe_dims(ffprobe, args.input)
    except ValueError as e:
        eprint(f"error: {e}")
        return EXIT_USAGE

    scenes = detect_mod.scene_times(ffmpeg, args.input, args.scene_threshold)

    def loud(s: float, d: float) -> float:
        return detect_mod.segment_loudness(ffmpeg, args.input, s, d)

    clips = detect_mod.rank_segments(scenes, total, loud, args.clips,
                                     args.min_sec, args.max_sec)
    os.makedirs(args.out, exist_ok=True)
    vf = cut_mod.crop_filter(w, h, args.aspect)

    rows: list[tuple[int, float, float, int, float]] = []
    if chapters_only:
        chapters_mod.write_chapters(os.path.join(args.out, "chapters.txt"), clips)
        for i, c in enumerate(clips, 1):
            rows.append((i, c["start"], c["dur"], 0, c["score"]))
    else:
        for i, c in enumerate(clips, 1):
            dst = os.path.join(args.out, f"clip{i}.mp4")
            try:
                size = cut_mod.cut_clip(ffmpeg, args.input, c["start"], c["dur"], vf, dst)
            except RuntimeError as e:
                eprint(f"error: {e}")
                return EXIT_FFMPEG
            c["path"] = dst
            rows.append((i, c["start"], c["dur"], size, c["score"]))
        if args.chapters:
            chapters_mod.write_chapters(os.path.join(args.out, "chapters.txt"), clips)

    if args.captions:
        try:
            from clipcut import captions as cap_mod
            model = cap_mod.load_model()
        except ImportError:
            from clipcut import captions as cap_mod
            eprint(f"error: faster-whisper not installed — {cap_mod.CAPTIONS_HINT}")
            return EXIT_NO_CAPTIONS
        targets = clips if not chapters_only else []
        for i, c in zip(range(1, len(clips) + 1), targets):
            srt = cap_mod.transcribe_clip(
                model, os.path.join(args.out, f"clip{i}.mp4"))
            with open(os.path.join(args.out, f"clip{i}.srt"),
                      "w", encoding="utf-8") as f:
                f.write(srt)

    print(f"{'clip':<6}{'start':<10}{'dur':<9}{'size':<12}{'scene-score'}")
    for i, s, d, size, score in rows:
        print(f"{i:<6}{s:<10.1f}{d:<9.1f}{size:<12}{score:.2f}")
    return 0


def main() -> None:
    sys.exit(run())


if __name__ == "__main__":
    main()
