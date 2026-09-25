"""CPU-only, offline detection: scene cuts + audio energy + ranking."""
from __future__ import annotations

import json
import re
import subprocess

PTS_RE = re.compile(r"pts_time:([0-9.]+)")
MEAN_RE = re.compile(r"mean_volume:\s*(-?[0-9.]+|n/a|-inf)\s*dB")

EDGE_SEC = 2.0  # clips touching the first/last 2s get a score penalty


def probe_duration(ffprobe: str, path: str) -> float:
    p = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration",
         "-of", "json", path],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise ValueError(f"ffprobe failed: {p.stderr.strip()[:200]}")
    return float(json.loads(p.stdout)["format"]["duration"])


def probe_dims(ffprobe: str, path: str) -> tuple[int, int]:
    p = subprocess.run(
        [ffprobe, "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "json", path],
        capture_output=True, text=True,
    )
    if p.returncode != 0:
        raise ValueError(f"ffprobe failed: {p.stderr.strip()[:200]}")
    s = json.loads(p.stdout)["streams"][0]
    return int(s["width"]), int(s["height"])


def scene_times(ffmpeg: str, path: str, threshold: float) -> list[float]:
    """Scene-cut timestamps via select='gt(scene,t)',showinfo (pure CPU)."""
    p = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", path, "-vf",
         f"select='gt(scene,{threshold})',showinfo",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    return sorted({float(m.group(1)) for m in PTS_RE.finditer(p.stderr)})


def segment_loudness(ffmpeg: str, path: str, start: float, dur: float) -> float:
    """Loudness score in [0, 1] from volumedetect mean_volume (dB)."""
    p = subprocess.run(
        [ffmpeg, "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}",
         "-i", path, "-af", "volumedetect", "-vn", "-sn", "-dn",
         "-f", "null", "-"],
        capture_output=True, text=True,
    )
    m = MEAN_RE.search(p.stderr)
    if not m or m.group(1) in ("n/a", "-inf"):
        return 0.0
    db = float(m.group(1))
    return max(0.0, min(1.0, (db + 60.0) / 60.0))


def _target_duration(total: float, n: int, min_sec: float, max_sec: float) -> float:
    if total <= min_sec:
        return total
    if n <= 0:  # chapters-only mode: one chapter per ~sixth of the video
        return max(min_sec, min(max_sec, total / 6.0))
    return max(min_sec, min(max_sec, total / (n + 1)))


def rank_segments(
    scenes: list[float],
    total: float,
    loudness_of,
    n: int,
    min_sec: float,
    max_sec: float,
) -> list[dict]:
    """Pick top-N non-overlapping [min-sec, max-sec] segments.

    Score = scene-boundary term + loudness + middle-position bonus
            - edge penalty (clip touches first/last 2s).
    """
    target = _target_duration(total, n, min_sec, max_sec)
    starts = sorted({0.0} | {t for t in scenes if 0.0 <= t <= total})
    # Fallback: evenly spaced starts so --clips N stays reachable when scene
    # detection finds nothing (static footage, color-only cuts, silent video).
    spacing = max(min_sec, target)
    k = 1
    while k * spacing <= total - min_sec + 1e-9:
        starts.append(k * spacing)
        k += 1
    starts = sorted(set(starts))
    if not starts:
        starts = [0.0]

    cands: list[dict] = []
    for s in starts:
        remain = total - s
        d = min(target, remain)
        if d < min_sec - 1e-6:
            continue
        is_scene = any(abs(s - t) <= 0.75 for t in scenes) or s == 0.0
        loud = loudness_of(s, d)
        mid = (s + d / 2.0) / total if total > 0 else 0.5
        score = (1.0 if is_scene else 0.35) + loud + 0.2 * (1.0 - abs(mid - 0.45))
        if s < EDGE_SEC or (total - (s + d)) < EDGE_SEC:
            score -= 0.3
        cands.append({"start": s, "dur": d, "scene": is_scene,
                      "loud": loud, "score": score})
    if not cands:  # video shorter than min-sec: take the whole thing
        cands.append({"start": 0.0, "dur": total, "scene": False,
                      "loud": loudness_of(0.0, total), "score": 0.0})

    cands.sort(key=lambda c: -c["score"])
    want = n if n > 0 else 999
    chosen: list[dict] = []
    for c in cands:
        if len(chosen) >= want:
            break
        if all(c["start"] + 0.25 >= o["start"] + o["dur"]
               or o["start"] + 0.25 >= c["start"] + c["dur"] for o in chosen):
            chosen.append(c)
    chosen.sort(key=lambda c: c["start"])
    return chosen
