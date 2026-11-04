from rest_framework.routers import DefaultRouter

from .views import AdsPowerProfileViewSet, ProxyConfigViewSet, UploadTaskViewSet

router = DefaultRouter()
router.register("adspower-profiles", AdsPowerProfileViewSet, basename="adspower-profiles")
router.register("adspower-proxies", ProxyConfigViewSet, basename="adspower-proxies")
router.register("upload-tasks", UploadTaskViewSet, basename="upload-tasks")

urlpatterns = router.urls
