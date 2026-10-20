from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("keywords.urls")),
    path("api/", include("content_gen.urls")),
    path("api/", include("flow3.urls")),
]

# 开发环境（DEBUG）下由 Django 直接托管 media；生产由 nginx 的 /media/ 反代到静态文件。
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

