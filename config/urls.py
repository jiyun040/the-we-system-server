from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    # The current Flutter client calls absolute paths such as /approvals/dashboard.
    path("", include("core.compat_urls")),
]
