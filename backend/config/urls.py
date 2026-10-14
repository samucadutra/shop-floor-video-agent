from django.urls import include, path, re_path

from core.views import serve_media

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/", include("videos.urls")),
    re_path(r"^media/(?P<path>.*)$", serve_media, name="media"),
]
