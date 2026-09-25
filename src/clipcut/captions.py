"""Per-clip captions via faster-whisper (optional extra).

Writes out/clipN.srt files with timestamps relative to each clip
(per-clip SRT, synced to the clip timeline — not a merged timeline).
"""
from __future__ import annotations

import os

CAPTIONS_HINT = "pip install clipcut[captions]"


def fmt_srt_ts(sec: float) -> str:
    ms = max(0, int(round(sec * 1000)))
    return (f"{ms // 3600000:02d}:{(ms % 3600000) // 60000:02d}:"
            f"{(ms % 60000) // 1000:02d},{ms % 1000:03d}")


def segments_to_srt(segments) -> str:
    """Serialize (start, end, text) segments to SRT format."""
    out = []
    for i, (s, e, text) in enumerate(segments, 1):
        out.append(f"{i}\n{fmt_srt_ts(s)} --> {fmt_srt_ts(e)}\n{text.strip()}\n")
    return "\n".join(out) + ("\n" if out else "")


def load_model():
    if os.environ.get("CLIPCUT_BLOCK_FASTER_WHISPER"):
        raise ImportError("blocked for testing")
    from faster_whisper import WhisperModel
    return WhisperModel("tiny")


def transcribe_clip(model, clip_path: str) -> str:
    segments, _info = model.transcribe(clip_path)
    triples = [(s.start, s.end, s.text) for s in segments]
    return segments_to_srt(triples)
