"""chapters.txt writer — timestamp labels only, no invented titles."""
from __future__ import annotations


def fmt_hms(sec: float) -> str:
    s = int(sec)
    return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


def chapter_lines(clips: list[dict]) -> list[str]:
    lines = []
    for i, c in enumerate(clips, 1):
        tag = "scene" if c.get("scene") else "auto"
        lines.append(f"{fmt_hms(c['start'])}  clip {i} start ({tag})")
    return lines


def write_chapters(path: str, clips: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(chapter_lines(clips)) + "\n")
