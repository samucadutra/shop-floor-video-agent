"""Thin wrappers around ffprobe / ffmpeg (docs/spec.md S9).

Every call uses an argument list (never a shell) and a timeout.
"""

import json
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
