"""Thin wrappers around ffprobe / ffmpeg (docs/spec.md S9).

Every call uses an argument list (never a shell) and a timeout.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PROBE_TIMEOUT_S = 30


class InvalidVideo(Exception):
    """The file is not a readable video."""


@dataclass(frozen=True)
class VideoMeta:
    duration_s: float
    width: int
    height: int
    fps: float
    format_name: str


def _parse_rate(rate: str) -> float:
    """Parse an ffprobe frame rate such as "30000/1001" or "25"."""
    num, _, den = rate.partition("/")
    try:
        value = float(num) / float(den or 1)
    except (ValueError, ZeroDivisionError):
        return 0.0
    return round(value, 3)


def probe(path: Path | str) -> VideoMeta:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]
    try:
        result = subprocess.run(
            cmd, check=True, capture_output=True, text=True, timeout=PROBE_TIMEOUT_S
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise InvalidVideo("The file could not be read as a video.") from exc

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise InvalidVideo("The file has no video stream.")

    fmt = data.get("format", {})
    try:
        duration = float(fmt.get("duration") or video.get("duration"))
    except (TypeError, ValueError) as exc:
        raise InvalidVideo("The video duration could not be read.") from exc

    return VideoMeta(
        duration_s=round(duration, 3),
        width=int(video.get("width", 0)),
        height=int(video.get("height", 0)),
        fps=_parse_rate(video.get("avg_frame_rate") or video.get("r_frame_rate") or "0"),
        format_name=fmt.get("format_name", ""),
    )


# Frame extraction ---------------------------------------------------------------------------

FFMPEG_TIMEOUT_S = 120
DEFAULT_MAX_SIDE = 768

# Keeps the long side <= max_side, never upscales, keeps an even short side.
SCALE = "scale='if(gt(iw,ih),min(iw,{M}),-2)':'if(gt(iw,ih),-2,min(ih,{M}))'"

PTS_TIME = re.compile(r"pts_time:([0-9.]+)")


class FFmpegError(Exception):
    """ffmpeg failed or timed out while extracting frames."""


@dataclass(frozen=True)
class ExtractedFrame:
    timestamp_s: float
    path: Path


# ffmpeg exits with an error when a filter selects no frame (e.g. a clip with no scene change).
NOTHING_WRITTEN = "Nothing was written into output file"


def _run_ffmpeg(args: list[str], *, allow_no_output: bool = False) -> str:
    """Run ffmpeg with an argument list and return its stderr."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-hide_banner", "-y", *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=FFMPEG_TIMEOUT_S,
        )
    except subprocess.CalledProcessError as exc:
        if allow_no_output and NOTHING_WRITTEN in (exc.stderr or ""):
            return exc.stderr
        raise FFmpegError(f"ffmpeg exited with code {exc.returncode}.") from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegError("ffmpeg timed out.") from exc
    return result.stderr


def _scale(max_side: int) -> str:
    return SCALE.format(M=max_side)


def _outputs(out_dir: Path, pattern: str) -> list[Path]:
    return sorted(out_dir.glob(pattern))


def extract_survey(
    video: Path, out_dir: Path, interval_s: float, *, max_side: int = DEFAULT_MAX_SIDE
) -> list[ExtractedFrame]:
    """One frame every `interval_s` seconds; frame n (1-based) is at (n - 1) * interval_s."""
    out_dir.mkdir(parents=True, exist_ok=True)
    _run_ffmpeg(
        [
            "-loglevel",
            "error",
            "-i",
            str(video),
            "-vf",
            f"fps=1/{interval_s},{_scale(max_side)}",
            "-q:v",
            "4",
            str(out_dir / "survey_%04d.jpg"),
        ]
    )
    paths = _outputs(out_dir, "survey_*.jpg")
    return [ExtractedFrame(round(i * interval_s, 3), path) for i, path in enumerate(paths)]


def extract_scenes(
    video: Path, out_dir: Path, threshold: float, *, max_side: int = DEFAULT_MAX_SIDE
) -> list[ExtractedFrame]:
    """Frames whose scene change score is above `threshold`, timed from showinfo's pts_time."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stderr = _run_ffmpeg(
        [
            "-i",
            str(video),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo,{_scale(max_side)}",
            "-fps_mode",
            "vfr",
            "-q:v",
            "4",
            str(out_dir / "scene_%04d.jpg"),
        ],
        allow_no_output=True,
    )
    times = [round(float(t), 3) for t in PTS_TIME.findall(stderr)]
    paths = _outputs(out_dir, "scene_*.jpg")
    return [ExtractedFrame(t, path) for t, path in zip(times, paths, strict=False)]


def extract_window(
    video: Path,
    out_dir: Path,
    start: float,
    end: float,
    fps: float,
    *,
    max_side: int = DEFAULT_MAX_SIDE,
) -> list[ExtractedFrame]:
    """Frames at `fps` between `start` and `end`; frame n is at start + (n - 1) / fps."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"win_{start:07.2f}_{end:07.2f}"  # unique per window, so frames are never reused
    _run_ffmpeg(
        [
            "-loglevel",
            "error",
            "-ss",
            str(start),
            "-to",
            str(end),
            "-i",
            str(video),
            "-vf",
            f"fps={fps},{_scale(max_side)}",
            "-q:v",
            "4",
            str(out_dir / f"{prefix}_%04d.jpg"),
        ]
    )
    paths = _outputs(out_dir, f"{prefix}_*.jpg")
    return [ExtractedFrame(round(start + i / fps, 3), path) for i, path in enumerate(paths)]
