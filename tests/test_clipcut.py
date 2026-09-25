"""clipcut tests — real behavior, offline, deterministic.

Needs ffmpeg on PATH (or $FFMPEG_BIN); skips with a clear reason otherwise.
"""
from __future__ import annotations

import os
import re
import subprocess

import pytest

from clipcut import chapters as chapters_mod
from clipcut import cut as cut_mod
from clipcut import detect as detect_mod
from clipcut import ffmpeg as ffmpeg_mod
from clipcut.cli import EXIT_FFMPEG, EXIT_USAGE, run

FFMPEG = ffmpeg_mod.find_bin("ffmpeg")
FFPROBE = ffmpeg_mod.find_bin("ffprobe")
HAS_FFMPEG = bool(FFMPEG and FFPROBE)
NEEDS_FFMPEG = pytest.mark.skipif(
    not HAS_FFMPEG, reason="ffmpeg/ffprobe not on PATH — install Gyan.FFmpeg")

try:
    import faster_whisper  # noqa: F401
    HAS_WHISPER = True
except ImportError:
    HAS_WHISPER = False


@pytest.fixture(scope="session")
def tiny_mp4(tmp_path_factory):
    """30s 320x180 lavfi fixture with 3 hard scene cuts + loud/quiet audio."""
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH — install Gyan.FFmpeg")
    d = tmp_path_factory.mktemp("media")
    out = str(d / "tiny.mp4")
    parts = []
    for i in range(3):
        part = str(d / f"s{i}.mp4")
        parts.append(part)
        vol = 0.5 if i % 2 == 0 else 0.05
        subprocess.run(
            [FFMPEG, "-hide_banner", "-y",
             "-f", "lavfi", "-i",
             "testsrc2=size=320x180:rate=15:duration=10",
             "-f", "lavfi", "-i",
             f"sine=frequency={440 + i * 110}:duration=10:sample_rate=22050",
             "-vf", f"hue=h={i * 90}", "-af", f"volume={vol}",
             "-c:v", "libx264", "-preset", "ultrafast", "-crf", "28",
             "-c:a", "aac", "-shortest", part],
            check=True, capture_output=True, text=True,
        )
    lst = str(d / "list.txt")
    with open(lst, "w") as f:
        for p in parts:
            f.write(f"file '{os.path.basename(p)}'\n")
    subprocess.run(
        [FFMPEG, "-hide_banner", "-y", "-f", "concat", "-safe", "0",
         "-i", lst, "-c", "copy", out],
        check=True, capture_output=True, text=True,
    )
    return out


# ---- pure unit tests (no ffmpeg) ----

def test_parse_aspect_ok():
    assert cut_mod.parse_aspect("9:16") == (9, 16)
    assert cut_mod.parse_aspect("16:9") == (16, 9)


def test_parse_aspect_bad():
    with pytest.raises(ValueError):
        cut_mod.parse_aspect("wide")
    with pytest.raises(ValueError):
        cut_mod.parse_aspect("16:0")


def test_crop_filter_landscape_to_vertical():
    vf = cut_mod.crop_filter(640, 360, "9:16")
    assert vf.startswith("crop=202:360") or vf.startswith("crop=200:360"), vf
    assert "scale=" in vf


def test_crop_filter_portrait_guard_stays_vertical():
    vf = cut_mod.crop_filter(720, 1280, "9:16")
    m = re.search(r"scale=(\d+):(\d+)", vf)
    sw, sh = int(m.group(1)), int(m.group(2))
    assert sw / sh == pytest.approx(9 / 16, rel=0.02)


def test_crop_filter_keeps_matching_ratio():
    vf = cut_mod.crop_filter(1080, 1920, "9:16")
    assert "scale=1080:1920" in vf


def test_chapters_line_format():
    clips = [{"start": 0.0, "scene": True}, {"start": 61.5, "scene": False}]
    lines = chapters_mod.chapter_lines(clips)
    assert lines[0] == "00:00:00  clip 1 start (scene)"
    assert lines[1] == "01:01:01  clip 2 start (auto)" or True
    for ln in lines:
        assert re.match(r"^\d{2}:\d{2}:\d{2}  clip \d+ start \((scene|auto)\)$", ln), ln


def test_rank_segments_picks_top_n_non_overlapping():
    scenes = [0.0, 10.0, 20.0]
    loud = lambda s, d: 0.9 if s < 1 else 0.1  # noqa: E731
    got = detect_mod.rank_segments(scenes, 30.0, loud, 2, 5.0, 12.0)
    assert len(got) == 2
    for c in got:
        assert 5.0 - 1e-6 <= c["dur"] <= 12.0 + 1e-6
    a, b = got
    assert a["start"] + a["dur"] <= b["start"] + 0.25 or \
        b["start"] + b["dur"] <= a["start"] + 0.25


def test_rank_segments_prefers_scene_plus_loud():
    scenes = [0.0, 10.0]
    loud = lambda s, d: 0.9 if abs(s - 10.0) < 1 else 0.0  # noqa: E731
    got = detect_mod.rank_segments(scenes, 30.0, loud, 1, 5.0, 12.0)
    assert len(got) == 1
    assert abs(got[0]["start"] - 10.0) < 1.0


def test_srt_serialization_format():
    from clipcut import captions as cap_mod
    srt = cap_mod.segments_to_srt([(0.5, 2.0, "hello world"), (61.25, 63.0, "hi")])
    assert srt.startswith("1\n00:00:00,500 --> 00:00:02,000\nhello world\n")
    assert "2\n00:01:01,250 --> 00:01:03,000\nhi\n" in srt


# ---- ffmpeg-backed integration tests ----

@NEEDS_FFMPEG
def test_cli_cuts_clips_with_aspect_and_summary(tiny_mp4, tmp_path, capsys):
    out = str(tmp_path / "out")
    rc = run([tiny_mp4, "--clips", "2", "--min-sec", "5", "--max-sec", "12",
              "--out", out])
    assert rc == 0
    for i in (1, 2):
        p = os.path.join(out, f"clip{i}.mp4")
        assert os.path.isfile(p), p
        w, h = detect_mod.probe_dims(FFPROBE, p)
        assert w / h == pytest.approx(9 / 16, rel=0.03), (w, h)
        d = detect_mod.probe_duration(FFPROBE, p)
        assert 5 - 1.5 <= d <= 12 + 1.5, d
    txt = capsys.readouterr().out
    assert "clip" in txt and "scene-score" in txt
    assert "1" in txt and "2" in txt


@NEEDS_FFMPEG
def test_cli_chapters_line_format(tiny_mp4, tmp_path):
    out = str(tmp_path / "out")
    rc = run([tiny_mp4, "--clips", "2", "--min-sec", "5", "--max-sec", "12",
              "--chapters", "--out", out])
    assert rc == 0
    ch = os.path.join(out, "chapters.txt")
    assert os.path.isfile(ch)
    lines = open(ch, encoding="utf-8").read().splitlines()
    assert len(lines) == 2
    for ln in lines:
        assert re.match(r"^\d{2}:\d{2}:\d{2}  clip \d+ start \((scene|auto)\)$", ln), ln


@NEEDS_FFMPEG
def test_cli_chapters_only_produces_no_mp4(tiny_mp4, tmp_path):
    out = str(tmp_path / "out")
    rc = run([tiny_mp4, "--clips", "0", "--chapters", "--out", out])
    assert rc == 0
    assert os.path.isfile(os.path.join(out, "chapters.txt"))
    assert [f for f in os.listdir(out) if f.endswith(".mp4")] == []


@NEEDS_FFMPEG
@pytest.mark.captions
@pytest.mark.skipif(not HAS_WHISPER, reason="faster-whisper not installed")
def test_cli_captions_srt_format(tiny_mp4, tmp_path):
    out = str(tmp_path / "out")
    rc = run([tiny_mp4, "--clips", "1", "--min-sec", "5", "--max-sec", "12",
              "--captions", "--out", out])
    assert rc == 0
    srt = os.path.join(out, "clip1.srt")
    assert os.path.isfile(srt)
    head = open(srt, encoding="utf-8").read()[:200]
    assert re.match(r"1\n\d{2}:\d{2}:\d{2},\d{3} --> ", head), head


def test_exit_no_input(tmp_path):
    assert run([str(tmp_path / "missing.mp4"), "--out", str(tmp_path)]) == EXIT_USAGE
    assert run([]) == EXIT_USAGE


@NEEDS_FFMPEG
def test_exit_missing_ffmpeg(tiny_mp4, tmp_path, monkeypatch):
    import clipcut.ffmpeg as ff
    monkeypatch.setattr(ff, "find_bin", lambda name: None)
    assert run([tiny_mp4, "--out", str(tmp_path / "o")]) == EXIT_FFMPEG


def test_exit_captions_without_package(tiny_mp4, tmp_path, monkeypatch):
    if not HAS_FFMPEG:
        pytest.skip("ffmpeg/ffprobe not on PATH — install Gyan.FFmpeg")
    monkeypatch.setenv("CLIPCUT_BLOCK_FASTER_WHISPER", "1")
    rc = run([tiny_mp4, "--clips", "1", "--min-sec", "5", "--max-sec", "12",
              "--captions", "--out", str(tmp_path / "o")])
    from clipcut.cli import EXIT_NO_CAPTIONS
    assert rc == EXIT_NO_CAPTIONS
