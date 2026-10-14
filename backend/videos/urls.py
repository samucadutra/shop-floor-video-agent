from django.urls import path
from rest_framework.routers import DefaultRouter

from videos.views import RunTraceView, VideoViewSet

router = DefaultRouter(trailing_slash=True)
router.register("videos", VideoViewSet, basename="video")

urlpatterns = [
    path("runs/<uuid:pk>/trace/", RunTraceView.as_view(), name="run-trace"),
    *router.urls,
]
