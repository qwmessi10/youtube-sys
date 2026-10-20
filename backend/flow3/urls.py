from rest_framework.routers import DefaultRouter

from .views import Flow3AgentViewSet, Flow3MaterialViewSet, Flow3RunViewSet

router = DefaultRouter()
router.register("flow3-agents", Flow3AgentViewSet, basename="flow3-agents")
router.register("flow3-materials", Flow3MaterialViewSet, basename="flow3-materials")
router.register("flow3-runs", Flow3RunViewSet, basename="flow3-runs")

urlpatterns = router.urls
