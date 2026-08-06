from rest_framework.routers import DefaultRouter

from .views import ContentAgentViewSet, ContentItemViewSet, ContentRunViewSet

router = DefaultRouter()
router.register("content-agents", ContentAgentViewSet, basename="content-agents")
router.register("content-runs", ContentRunViewSet, basename="content-runs")
router.register("content-items", ContentItemViewSet, basename="content-items")

urlpatterns = router.urls
