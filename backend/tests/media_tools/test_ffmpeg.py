import subprocess
from pathlib import Path

import pytest

from media_tools.ffmpeg import FFmpegError, extract_scenes, extract_survey, extract_window


def _frame_size(path: Path) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=width,height", "-of", "csv=p=0", path],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    width, height = out.strip().split(",")
    return int(width), int(height)


def _make_scene_change_video(tmp_path: Path) -> Path:
    """3 s of testsrc followed by 3 s of plain red: one scene change at 3 s."""
    path = tmp_path / "scenes.mp4"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=3:size=320x240:rate=25",
            "-f", "lavfi", "-i", "color=c=red:size=320x240:rate=25:duration=3",
            "-filter_complex", "[0:v][1:v]concat=n=2:v=1[v]",
            "-map", "[v]", "-pix_fmt", "yuv420p", str(path),
        ],
        check=True,
        timeout=60,
    )  # fmt: skip
    return path


def test_survey_frames_every_interval(make_test_video, tmp_path: Path) -> None:
    frames = extract_survey(make_test_video(seconds=10), tmp_path / "out", 2)

    assert [f.timestamp_s for f in frames] == [0, 2, 4, 6, 8]
    assert all(f.path.is_file() and f.path.name.startswith("survey_") for f in frames)


def test_window_frames_at_fps(make_test_video, tmp_path: Path) -> None:
    frames = extract_window(make_test_video(seconds=10), tmp_path / "out", 2, 6, 2)

    assert [f.timestamp_s for f in frames] == [2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5]
    assert frames[0].path.name == "win_0002.00_0001.jpg"


def test_scene_change_is_found(tmp_path: Path) -> None:
    frames = extract_scenes(_make_scene_change_video(tmp_path), tmp_path / "out", 0.4)

    assert len(frames) == 1
    assert frames[0].timestamp_s == pytest.approx(3, abs=0.1)
    assert frames[0].path.is_file()


@pytest.mark.parametrize(
    ("size", "max_side", "expected"),
    [
        ("1280x720", 768, (768, 432)),  # landscape: width limited
        ("720x1280", 768, (432, 768)),  # portrait: height limited
        ("320x240", 768, (320, 240)),  # small: never upscaled
    ],
)
def test_frames_never_larger_than_max_side(
    make_test_video, tmp_path: Path, size: str, max_side: int, expected: tuple[int, int]
) -> None:
    video = make_test_video(seconds=2, size=size)

    survey = extract_survey(video, tmp_path / "survey", 1, max_side=max_side)
    window = extract_window(video, tmp_path / "window", 0, 1, 2, max_side=max_side)

    assert {_frame_size(f.path) for f in survey + window} == {expected}


def test_unreadable_input_raises(tmp_path: Path) -> None:
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"not a video")

    with pytest.raises(FFmpegError):
        extract_survey(fake, tmp_path / "out", 2)
