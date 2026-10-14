import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def media_root(settings, tmp_path: Path) -> Path:
    """Every test writes uploads and frames to its own temporary MEDIA_ROOT."""
    root = tmp_path / "media"
    root.mkdir()
    settings.MEDIA_ROOT = root
    return root


@pytest.fixture
def make_test_video(tmp_path: Path) -> Callable[..., Path]:
    """Return a factory that creates a small test clip with ffmpeg's testsrc."""

    def _make(seconds: float = 3, name: str = "clip.mp4", size: str = "320x240") -> Path:
        path = tmp_path / name
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                f"testsrc=duration={seconds}:size={size}:rate=25",
                "-pix_fmt",
                "yuv420p",
                str(path),
            ],
            check=True,
            timeout=60,
        )
        return path

    return _make
