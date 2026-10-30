from rest_framework.routers import DefaultRouter

from .views import AdsPowerProfileViewSet, UploadTaskViewSet

router = DefaultRouter()
router.register("adspower-profiles", AdsPowerProfileViewSet, basename="adspower-profiles")
router.register("upload-tasks", UploadTaskViewSet, basename="upload-tasks")

urlpatterns = router.urls
