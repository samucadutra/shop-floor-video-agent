import uuid

from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers

from videos.models import ACTIVE_RUN_STATUSES, AgentStep, AnalysisRun, Event, RunStatus, Video
from videos.validators import ValidatedUpload, validate_upload


class VideoUploadSerializer(serializers.Serializer):
    file = serializers.FileField(write_only=True)

    def validate_file(self, uploaded: UploadedFile) -> UploadedFile:
        self._validated_upload: ValidatedUpload = validate_upload(uploaded)
        return uploaded

    def create(self, validated_data: dict) -> Video:
        uploaded: UploadedFile = validated_data["file"]
        checked = self._validated_upload
        video_id = uuid.uuid4()
        video = Video(
            id=video_id,
            original_name=(uploaded.name or "video")[:255],
            size_bytes=uploaded.size,
            sha256=checked.sha256,
            duration_s=checked.meta.duration_s,
            width=checked.meta.width,
            height=checked.meta.height,
            fps=checked.meta.fps,
        )
        # Saved under a generated name, never the user's file name.
        video.file.save(f"{video_id}{checked.extension}", uploaded, save=False)
        video.save()
        return video


class VideoListSerializer(serializers.ModelSerializer):
    event_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Video
        fields = ["id", "original_name", "status", "duration_s", "event_count", "created_at"]


class RunSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = AnalysisRun
        fields = [
            "id",
            "status",
            "provider",
            "model",
            "summary",
            "is_partial",
            "stop_reason",
            "error_message",
            "iterations",
            "frames_analyzed",
            "llm_calls",
            "input_tokens",
            "output_tokens",
            "estimated_cost_usd",
            "duration_ms",
            "started_at",
            "finished_at",
        ]


class VideoDetailSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    current_run = RunSummarySerializer(read_only=True)
    active_run_id = serializers.SerializerMethodField()
    error_message = serializers.SerializerMethodField()

    class Meta:
        model = Video
        fields = [
            "id",
            "original_name",
            "status",
            "duration_s",
            "width",
            "height",
            "fps",
            "size_bytes",
            "file_url",
            "current_run",
            "active_run_id",
            "error_message",
            "created_at",
        ]

    def get_file_url(self, video: Video) -> str:
        request = self.context.get("request")
        url = video.file.url
        return request.build_absolute_uri(url) if request else url

    def get_active_run_id(self, video: Video) -> str | None:
        run = video.runs.filter(status__in=ACTIVE_RUN_STATUSES).only("id").first()
        return str(run.id) if run else None

    def get_error_message(self, video: Video) -> str | None:
        latest = video.runs.order_by("-created_at").only("status", "error_message").first()
        if latest and latest.status == RunStatus.FAILED:
            return latest.error_message or "Analysis failed."
        return None


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "event_type",
            "timestamp_s",
            "start_s",
            "end_s",
            "severity",
            "confidence",
            "explanation",
            "frame_ref",
        ]


class AgentStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentStep
        exclude = ["run"]


class RunTraceSerializer(serializers.ModelSerializer):
    run_id = serializers.UUIDField(source="id", read_only=True)
    steps = AgentStepSerializer(many=True, read_only=True)

    class Meta:
        model = AnalysisRun
        fields = ["run_id", "status", "is_partial", "stop_reason", "steps"]
