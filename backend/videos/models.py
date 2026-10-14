import uuid

from django.db import models
from django.db.models import Q


class VideoStatus(models.TextChoices):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"


class RunStatus(models.TextChoices):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


ACTIVE_RUN_STATUSES = [RunStatus.QUEUED, RunStatus.RUNNING]


class StopReason(models.TextChoices):
    COMPLETED = "completed"
    MAX_ITERATIONS = "max_iterations"
    MAX_FRAMES = "max_frames"
    MAX_TOKENS = "max_tokens"
    MAX_COST = "max_cost"
    MAX_LLM_CALLS = "max_llm_calls"
    TIMEOUT = "timeout"
    ERROR = "error"


class Severity(models.TextChoices):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Node(models.TextChoices):
    SURVEY = "survey"
    PLAN = "plan"
    INSPECT = "inspect"
    VERIFY = "verify"
    REPORT = "report"


class StepStatus(models.TextChoices):
    OK = "ok"
    RETRIED = "retried"
    ERROR = "error"


class Video(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    original_name = models.CharField(max_length=255)
    file = models.FileField(upload_to="videos/")
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    duration_s = models.FloatField()
    width = models.PositiveIntegerField()
    height = models.PositiveIntegerField()
    fps = models.FloatField()
    status = models.CharField(
        max_length=20, choices=VideoStatus.choices, default=VideoStatus.UPLOADED
    )
    current_run = models.OneToOneField(
        "AnalysisRun", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.original_name} ({self.status})"


class AnalysisRun(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="runs")
    status = models.CharField(max_length=20, choices=RunStatus.choices, default=RunStatus.QUEUED)
    provider = models.CharField(max_length=50)
    model = models.CharField(max_length=100, blank=True)
    summary = models.TextField(blank=True)
    is_partial = models.BooleanField(default=False)
    stop_reason = models.CharField(max_length=20, choices=StopReason.choices, blank=True)
    error_message = models.TextField(blank=True)
    iterations = models.PositiveIntegerField(default=0)
    frames_analyzed = models.PositiveIntegerField(default=0)
    llm_calls = models.PositiveIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["video"],
                condition=Q(status__in=ACTIVE_RUN_STATUSES),
                name="one_active_run_per_video",
            )
        ]

    def __str__(self) -> str:
        return f"run {self.id} ({self.status})"


class Event(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="events")
    video = models.ForeignKey(Video, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=50, db_index=True)
    timestamp_s = models.FloatField()
    start_s = models.FloatField()
    end_s = models.FloatField()
    severity = models.CharField(max_length=10, choices=Severity.choices)
    confidence = models.FloatField()
    explanation = models.TextField()
    frame_ref = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp_s"]
        constraints = [
            models.CheckConstraint(
                condition=Q(confidence__gte=0) & Q(confidence__lte=1),
                name="event_confidence_0_1",
            )
        ]

    def __str__(self) -> str:
        return f"{self.event_type} @ {self.timestamp_s:.1f}s"


class AgentStep(models.Model):
    run = models.ForeignKey(AnalysisRun, on_delete=models.CASCADE, related_name="steps")
    index = models.PositiveIntegerField()
    node = models.CharField(max_length=20, choices=Node.choices)
    iteration = models.PositiveIntegerField(default=0)
    input_summary = models.TextField(blank=True)
    decision = models.TextField(blank=True)
    tool_calls = models.JSONField(default=list, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=4, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=10, choices=StepStatus.choices, default=StepStatus.OK)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["run", "index"], name="agent_step_unique_index")
        ]

    def __str__(self) -> str:
        return f"step {self.index} {self.node}"
