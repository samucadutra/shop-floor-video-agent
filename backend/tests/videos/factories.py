"""Small helpers to create database rows in tests (no upload, no ffmpeg)."""

from django.core.files.base import ContentFile

from videos.models import AgentStep, AnalysisRun, Event, RunStatus, Video


def create_video(name: str = "clip.mp4", **fields) -> Video:
    video = Video(
        original_name=name,
        size_bytes=4,
        sha256="0" * 64,
        duration_s=10.0,
        width=320,
        height=240,
        fps=25.0,
        **fields,
    )
    video.file.save(f"{video.id}.mp4", ContentFile(b"fake"), save=False)
    video.save()
    return video


def create_run(video: Video, status: str = RunStatus.SUCCEEDED, **fields) -> AnalysisRun:
    return AnalysisRun.objects.create(video=video, status=status, provider="mock", **fields)


def create_event(run: AnalysisRun, timestamp_s: float = 1.0, **fields) -> Event:
    values = {
        "event_type": "missing_ppe",
        "start_s": max(timestamp_s - 1, 0),
        "end_s": timestamp_s + 1,
        "severity": "medium",
        "confidence": 0.8,
        "explanation": "No hard hat.",
    } | fields
    return Event.objects.create(run=run, video=run.video, timestamp_s=timestamp_s, **values)


def create_step(run: AnalysisRun, index: int, node: str = "survey") -> AgentStep:
    return AgentStep.objects.create(run=run, index=index, node=node, decision=f"decision {index}")
