from django.db.models import Count, QuerySet
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveAPIView
from rest_framework.request import Request
from rest_framework.response import Response

from videos.models import AnalysisRun, Event, Video
from videos.serializers import (
    EventSerializer,
    RunTraceSerializer,
    VideoDetailSerializer,
    VideoListSerializer,
    VideoUploadSerializer,
)
from videos.services import RunAlreadyActive, mark_stale_runs, start_analysis


class VideoViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    def get_queryset(self) -> QuerySet[Video]:
        # Aggregation drops Meta.ordering, so the order is explicit (stable pagination).
        return (
            Video.objects.select_related("current_run")
            .annotate(event_count=Count("current_run__events"))
            .order_by("-created_at")
        )

    def get_serializer_class(self):
        if self.action == "create":
            return VideoUploadSerializer
        if self.action == "list":
            return VideoListSerializer
        return VideoDetailSerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        upload = VideoUploadSerializer(data=request.data)
        upload.is_valid(raise_exception=True)
        video = upload.save()
        body = VideoDetailSerializer(video, context=self.get_serializer_context()).data
        return Response(body, status=status.HTTP_201_CREATED)

    def retrieve(self, request: Request, *args, **kwargs) -> Response:
        video = self.get_object()
        mark_stale_runs(video)  # refreshes video.status when a run is failed
        return Response(self.get_serializer(video).data)

    @action(detail=True, methods=["post"])
    def analyze(self, request: Request, pk: str | None = None) -> Response:
        video = self.get_object()
        try:
            run = start_analysis(video)
        except RunAlreadyActive:
            return Response(
                {"detail": "An analysis is already running for this video."},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {"run_id": str(run.id), "status": run.status}, status=status.HTTP_202_ACCEPTED
        )

    @action(detail=True, methods=["get"])
    def events(self, request: Request, pk: str | None = None) -> Response:
        video = self.get_object()
        events = Event.objects.filter(run_id=video.current_run_id) if video.current_run_id else []
        return Response(EventSerializer(events, many=True).data)


class RunTraceView(RetrieveAPIView):
    queryset = AnalysisRun.objects.prefetch_related("steps")
    serializer_class = RunTraceSerializer
