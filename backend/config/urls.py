from django.urls import include, path, re_path

from core.views import serve_media

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"

urlpatterns = [
    path("api/", include("core.urls")),
    path("api/", include("videos.urls")),
    re_path(r"^media/(?P<path>.*)$", serve_media, name="media"),
]
